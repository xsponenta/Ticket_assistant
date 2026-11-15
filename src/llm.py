"""Shared LLM client: the ONLY way this project calls LLMs (see AGENTS.md).

    from src.llm import complete
    text = complete(messages, role="generator", component="classifier")
    obj = complete(messages, role="judge", component="judge_c1", schema=MyModel)   # validated pydantic object

- Models per role come from config.yaml; requests go to OpenRouter through the openai SDK.
- Disk cache keyed by the full request (model, messages, temperature, max_tokens, response format / schema).
- Exponential backoff on 429 / 5xx / timeouts / connection errors (Retry-After honoured).
- Structured output: json_schema when the model supports it, otherwise JSON-in-prompt; always validated with
  pydantic, with one repair retry.
- Every call (including cache hits and failures) is logged to logs/llm_calls.jsonl.
- Optional Langfuse tracing when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.
- Thread-safe: one shared client, atomic cache writes, locked log appends.

CLI:
    python -m src.llm --ping     # one uncached call per role
    python -m src.llm --stats    # summary of logs/llm_calls.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
import tempfile
import threading
import time
import warnings
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openai
import requests
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
ROLES = ("generator", "judge", "simulator")
PLACEHOLDER = "CHOOSE_ME"
MODELS_URL = "https://openrouter.ai/api/v1/models"
CAPABILITIES_TTL_S = 24 * 3600
LOG_FIELDS = (
    "ts",
    "component",
    "session_id",
    "role",
    "model",
    "cached",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cost",
    "attempts",
    "mode",
    "repair",
    "status",
    "error",
)
SCHEMA_INSTRUCTION = (
    "Respond with a single JSON object that conforms to the JSON schema below. "
    "Output only the JSON object: no prose, no code fences.\n\nJSON schema:\n{schema}"
)
REPAIR_INSTRUCTION = (
    "Your previous reply could not be parsed or did not match the required JSON schema.\n"
    "Error: {error}\nReturn only the corrected JSON object, nothing else."
)


class LLMError(Exception):
    """A call failed (after retries)."""


class LLMConfigError(LLMError):
    """Missing API key or model not configured."""


class LLMOutputError(LLMError):
    """The model output could not be validated against the schema, even after one repair."""

    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw


class _ProviderError(Exception):
    """OpenRouter returned 200 but without choices / with an error object (upstream provider failure)."""


@dataclass(frozen=True)
class Settings:
    base_url: str
    timeout_s: float
    max_attempts: int
    cache_dir: Path
    log_path: Path
    models_cache: Path
    models: dict[str, str]
    temperature: dict[str, float]
    reasoning: dict[str, dict[str, Any] | None] = field(default_factory=dict)  # per-role OpenRouter setting


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    cfg = yaml.safe_load(path.read_text())
    llm = cfg["llm"]
    return Settings(
        base_url=llm["base_url"],
        timeout_s=float(llm["timeout_s"]),
        max_attempts=int(llm["max_attempts"]),
        cache_dir=ROOT / llm["cache_dir"],
        log_path=ROOT / llm["log_path"],
        models_cache=ROOT / llm["models_cache"],
        models=dict(cfg["models"]),
        temperature={k: float(v) for k, v in cfg["temperature"].items()},
        reasoning=dict(cfg.get("reasoning") or {}),
    )


# ---------------------------------------------------------------- shared state (lazy, thread-safe singletons)

_lock = threading.RLock()  # guards _state
_log_lock = threading.Lock()  # serialises log appends
_state: dict[str, Any] = {}
_sleep = time.sleep  # patched in tests


def configure(
    *,
    settings: Settings | None = None,
    http_client: Any = None,
    capabilities: dict[str, set[str]] | None = None,
    tracing: bool | None = None,
) -> None:
    """Reset the shared state. Used by tests (inject settings, a mock HTTP client, model capabilities)."""
    with _lock:
        _state.clear()
        if settings is not None:
            _state["settings"] = settings
        if http_client is not None:
            _state["http_client"] = http_client
        if capabilities is not None:
            _state["capabilities"] = capabilities
        if tracing is False:
            _state["langfuse"] = None


def _settings() -> Settings:
    with _lock:
        if "settings" not in _state:
            _state["settings"] = load_settings()
        return _state["settings"]


def _client() -> openai.OpenAI:
    with _lock:
        if "client" not in _state:
            load_dotenv(ROOT / ".env")
            key = os.environ.get("OPENROUTER_API_KEY")
            if not key:
                raise LLMConfigError("OPENROUTER_API_KEY is not set: copy .env.example to .env and add your key.")
            s = _settings()
            _state["client"] = openai.OpenAI(
                base_url=s.base_url,
                api_key=key,
                max_retries=0,
                timeout=s.timeout_s,
                http_client=_state.get("http_client"),
            )
        return _state["client"]


def _capabilities(model: str) -> set[str]:
    with _lock:
        if "capabilities" not in _state:
            _state["capabilities"] = _load_capabilities(_settings().models_cache)
        return _state["capabilities"].get(model, set())


def _load_capabilities(path: Path) -> dict[str, set[str]]:
    """model id -> supported_parameters, from OpenRouter /models (cached on disk for 24 h)."""
    data: dict[str, list[str]] | None = None
    if path.exists() and time.time() - path.stat().st_mtime < CAPABILITIES_TTL_S:
        data = json.loads(path.read_text())
    else:
        try:
            resp = requests.get(MODELS_URL, timeout=30)
            resp.raise_for_status()
            data = {m["id"]: m.get("supported_parameters") or [] for m in resp.json()["data"]}
            _atomic_write_json(path, data)
        except (requests.RequestException, KeyError, ValueError) as exc:
            warnings.warn(f"Could not fetch model capabilities ({exc}); using JSON-in-prompt mode.", stacklevel=2)
            data = json.loads(path.read_text()) if path.exists() else {}
    return {model: set(params) for model, params in data.items()}


def _langfuse() -> Any:
    with _lock:
        if "langfuse" not in _state:
            _state["langfuse"] = None
            load_dotenv(ROOT / ".env")
            if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
                try:
                    from langfuse import Langfuse  # optional dependency

                    _state["langfuse"] = Langfuse()
                except Exception as exc:  # noqa: BLE001 - tracing must never break the client
                    warnings.warn(f"Langfuse keys are set but tracing is unavailable: {exc}", stacklevel=2)
        return _state["langfuse"]


# ---------------------------------------------------------------- cache and log


def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write to a temp file in the same directory, then os.replace: readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def cache_key(params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _cache_path(key: str) -> Path:
    return _settings().cache_dir / key[:2] / f"{key}.json"


def _cache_get(key: str) -> dict[str, Any] | None:
    try:
        return json.loads(_cache_path(key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _log(record: dict[str, Any]) -> None:
    path = _settings().log_path
    line = json.dumps({f: record.get(f) for f in LOG_FIELDS}, ensure_ascii=False) + "\n"
    with _log_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


def _trace(record: dict[str, Any], messages: list[dict[str, Any]], output: str | None) -> None:
    """Langfuse generation per call (only when keys are set). Supports langfuse 3.x and 2.x; never raises."""
    lf = _langfuse()
    if lf is None:
        return
    usage = {"input": record["prompt_tokens"] or 0, "output": record["completion_tokens"] or 0}
    meta = {k: record[k] for k in ("role", "cached", "attempts", "mode", "repair", "latency_ms")}
    try:
        if hasattr(lf, "start_generation"):  # langfuse 3.x
            gen = lf.start_generation(name=record["component"], model=record["model"], input=messages, metadata=meta)
            if record["session_id"]:
                gen.update_trace(session_id=record["session_id"])
            gen.update(
                output=output,
                usage_details=usage,
                level="ERROR" if record["error"] else "DEFAULT",
                status_message=record["error"],
            )
            gen.end()
        else:  # langfuse 2.x
            trace = lf.trace(name=record["component"], session_id=record["session_id"])
            trace.generation(
                name=record["component"],
                model=record["model"],
                input=messages,
                output=output,
                usage=usage,
                metadata=meta,
            )
    except Exception as exc:  # noqa: BLE001 - tracing must never break the client
        warnings.warn(f"Langfuse tracing failed: {exc}", stacklevel=2)


# ---------------------------------------------------------------- API call with retries


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    value = response.headers.get("retry-after") if response is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _call_api(params: dict[str, Any]) -> tuple[str, dict[str, Any], int]:
    """One chat completion with exponential backoff. Returns (text, usage, attempts)."""
    client, s = _client(), _settings()
    for attempt in range(1, s.max_attempts + 1):
        try:
            request = {k: v for k, v in params.items() if k != "extra_body"}
            extra_body = {**params.get("extra_body", {}), "usage": {"include": True}}
            resp = client.chat.completions.create(**request, extra_body=extra_body)
            if not resp.choices or getattr(resp, "error", None):
                raise _ProviderError(str(getattr(resp, "error", None) or "response without choices"))
            usage = resp.usage
            return (
                resp.choices[0].message.content or "",
                {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "reasoning_tokens": getattr(
                        getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None
                    ),
                    "cost": getattr(usage, "cost", None),
                },
                attempt,
            )
        except (openai.APIConnectionError, _ProviderError) as exc:  # incl. APITimeoutError
            error: Exception = exc
        except openai.APIStatusError as exc:
            if exc.status_code != 429 and exc.status_code < 500:
                raise
            error = exc
        if attempt == s.max_attempts:
            raise LLMError(f"LLM call failed after {attempt} attempts: {error}") from error
        delay = _retry_after(error)
        _sleep(delay if delay is not None else min(2 ** (attempt - 1), 30) + random.uniform(0, 0.5))
    raise AssertionError("unreachable")


def _request(params: dict[str, Any], *, ctx: dict[str, Any], repair: bool, use_cache: bool) -> str:
    """Cached API call + log line + optional trace."""
    key = cache_key(params)
    start = time.perf_counter()
    entry = _cache_get(key) if use_cache else None
    cached, attempts, error = entry is not None, 0, None
    try:
        if entry is None:
            text, usage, attempts = _call_api(params)
            entry = {
                "text": text,
                "usage": usage,
                "request": params,
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            if use_cache:
                _atomic_write_json(_cache_path(key), entry)
        return entry["text"]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        usage = (entry or {}).get("usage") or {}
        record = {
            **ctx,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "model": params["model"],
            "cached": cached,
            "latency_ms": round(1000 * (time.perf_counter() - start), 1),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": usage.get("reasoning_tokens"),
            "cost": 0.0 if cached else usage.get("cost"),
            "attempts": attempts,
            "repair": repair,
            "status": "error" if error else "ok",
            "error": error,
        }
        _log(record)
        _trace(record, params["messages"], (entry or {}).get("text"))


# ---------------------------------------------------------------- structured output


def _mode(model: str, schema: type[BaseModel] | None) -> str:
    if schema is None:
        return "text"
    caps = _capabilities(model)
    if "structured_outputs" in caps:
        return "json_schema"
    return "json_object" if "response_format" in caps else "prompt"


def _with_schema_instruction(messages: list[dict[str, Any]], schema: type[BaseModel]) -> list[dict[str, Any]]:
    instruction = SCHEMA_INSTRUCTION.format(schema=json.dumps(schema.model_json_schema(), ensure_ascii=False))
    if messages and messages[0]["role"] == "system":
        return [{"role": "system", "content": f"{messages[0]['content']}\n\n{instruction}"}, *messages[1:]]
    return [{"role": "system", "content": instruction}, *messages]


def _parse(text: str, schema: type[BaseModel]) -> BaseModel:
    """Find the JSON object in the reply and validate it.

    Candidates, in order: the whole reply; the reply minus ONE surrounding ```json fence; the span from the first
    '{' to the last '}'. The first candidate that is valid JSON is validated against the schema (its schema error is
    raised as is). Fences are never searched inside the reply, because JSON string values often contain code blocks.
    """
    body = text.strip()
    candidates = [body]
    fenced = re.fullmatch(r"```(?:json)?\s*(.*)\s*```", body, re.S)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start, end = body.find("{"), body.rfind("}")
    if start != -1 and end > start:
        candidates.append(body[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return schema.model_validate(data)
    return schema.model_validate_json(body)  # raises the JSON error of the whole reply


# ---------------------------------------------------------------- public API

_judge_warning_shown = False


def _model_for(role: str, override: str | None) -> str:
    global _judge_warning_shown
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    if override:
        return override
    models = _settings().models
    model = models.get(role)
    if not model or model == PLACEHOLDER:
        raise LLMConfigError(f"models.{role} is not set in config.yaml; pick one with `python scripts/list_models.py`.")
    if models.get("judge") == models.get("generator") and not _judge_warning_shown:
        _judge_warning_shown = True
        warnings.warn("models.judge equals models.generator; AGENTS.md requires different models.", stacklevel=3)
    return model


def complete(
    messages: list[dict[str, Any]],
    *,
    role: str,
    component: str,
    session_id: str | None = None,
    schema: type[BaseModel] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    use_cache: bool = True,
    model: str | None = None,
    reasoning: dict[str, Any] | None = None,
) -> str | BaseModel:
    """Call the model configured for `role`. Returns text, or a validated `schema` instance.

    temperature=None uses the role default from config.yaml; the judge always runs at temperature 0.
    model: override of the role's model, for EXPERIMENT SCRIPTS ONLY (components always use roles).
    reasoning: OpenRouter reasoning setting, e.g. {"effort": "none"} or {"enabled": False}. None = the role default
    from config.yaml (`reasoning.<role>`), except with a `model` override: experiments then control reasoning
    themselves and no role default is applied.
    Model and reasoning are part of the request and therefore of the cache key.
    """
    if reasoning is None and model is None:
        reasoning = _settings().reasoning.get(role)
    model = _model_for(role, model)
    if role == "judge":
        temp = 0.0
    else:
        temp = _settings().temperature.get(role, 0.0) if temperature is None else float(temperature)
    mode = _mode(model, schema)
    msgs = _with_schema_instruction(messages, schema) if mode in ("json_object", "prompt") else list(messages)

    params: dict[str, Any] = {"model": model, "messages": msgs, "temperature": temp}
    if max_tokens is not None:
        params["max_tokens"] = max_tokens
    if reasoning is not None:
        params["extra_body"] = {"reasoning": reasoning}
    if mode == "json_schema":
        params["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": False},
        }
    elif mode == "json_object":
        params["response_format"] = {"type": "json_object"}

    ctx = {"component": component, "session_id": session_id, "role": role, "mode": mode}
    text = _request(params, ctx=ctx, repair=False, use_cache=use_cache)
    if schema is None:
        return text
    try:
        return _parse(text, schema)
    except (ValueError, ValidationError) as exc:
        repair_msgs = [
            *msgs,
            {"role": "assistant", "content": text},
            {"role": "user", "content": REPAIR_INSTRUCTION.format(error=str(exc)[:1500])},
        ]
        text = _request({**params, "messages": repair_msgs}, ctx=ctx, repair=True, use_cache=use_cache)
        try:
            return _parse(text, schema)
        except (ValueError, ValidationError) as exc2:
            raise LLMOutputError(f"{schema.__name__} validation failed after one repair: {exc2}", raw=text) from exc2


# ---------------------------------------------------------------- CLI


def _read_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def log_offset() -> int:
    """Current size of the call log; pass it to session_calls() to read only the calls made after this point."""
    path = _settings().log_path
    return path.stat().st_size if path.exists() else 0


def session_calls(session_id: str, offset: int = 0) -> list[dict[str, Any]]:
    """Logged calls (incl. cache hits and failures) of one session, written after `offset` (for the app's trace)."""
    path = _settings().log_path
    if not path.exists():
        return []
    with _log_lock, path.open(encoding="utf-8") as f:
        f.seek(offset)
        rows = [json.loads(line) for line in f if line.strip()]
    return [r for r in rows if r.get("session_id") == session_id]


def ping() -> int:
    s, failures = _settings(), 0
    print(f"{'role':<10} {'model':<45} {'status':<7} {'latency_ms':>10} {'tokens in/out':>14} {'cost $':>10}  reply")
    for role in ROLES:
        try:
            reply = complete(
                [{"role": "user", "content": "Reply with exactly one word: pong"}],
                role=role,
                component="ping",
                use_cache=False,
            )
            status = "ok"
        except LLMError as exc:
            reply, status, failures = str(exc), "FAIL", failures + 1
        last = _read_log(s.log_path)[-1] if status == "ok" else {}
        tokens = f"{last.get('prompt_tokens')}/{last.get('completion_tokens')}" if last else "-"
        cost = f"{last['cost']:.6f}" if last.get("cost") is not None else "-"
        model = s.models.get(role, "")
        print(
            f"{role:<10} {model:<45} {status:<7} {last.get('latency_ms', '-'):>10} {tokens:>14} {cost:>10}  "
            f"{str(reply).strip()[:60]}"
        )
    return 1 if failures else 0


def stats() -> int:
    rows = _read_log(_settings().log_path)
    if not rows:
        print("No calls logged yet.")
        return 0
    cached = sum(r["cached"] for r in rows)
    latencies = sorted(r["latency_ms"] for r in rows if not r["cached"] and r["status"] == "ok")
    print(
        f"calls: {len(rows)}  cache hits: {cached} ({100 * cached / len(rows):.1f}%)  "
        f"errors: {sum(r['status'] == 'error' for r in rows)}  repairs: {sum(bool(r['repair']) for r in rows)}"
    )
    print(
        f"tokens: prompt {sum(r['prompt_tokens'] or 0 for r in rows if not r['cached']):,}  "
        f"completion {sum(r['completion_tokens'] or 0 for r in rows if not r['cached']):,}  (uncached calls)"
    )
    print(f"cost: ${sum(r['cost'] or 0 for r in rows):.4f}")
    if latencies:
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        print(f"latency (uncached): p50 {statistics.median(latencies):.0f} ms, p95 {p95:.0f} ms")
    for column in ("role", "component", "model"):
        counts = Counter(r[column] for r in rows)
        print(f"by {column}: " + ", ".join(f"{k} {n}" for k, n in counts.most_common()))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Shared LLM client utilities.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ping", action="store_true", help="one uncached call per role")
    group.add_argument("--stats", action="store_true", help="summary of logs/llm_calls.jsonl")
    args = parser.parse_args()
    sys.exit(ping() if args.ping else stats())


if __name__ == "__main__":
    main()
