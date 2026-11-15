"""Tests for src/llm.py with a mocked HTTP transport (no network, no API key needed)."""

import json
import random
import time
from concurrent.futures import ThreadPoolExecutor

import httpx2  # HTTP library of the openai SDK (v3)
import openai
import pytest
from pydantic import BaseModel

from src import llm

MODELS = {"generator": "prov/gen", "judge": "prov/judge", "simulator": "prov/sim", "embedder": "local/emb"}
JSON_SCHEMA_CAPS = {"structured_outputs", "response_format"}


class Verdict(BaseModel):
    label: str
    confidence: float


def chat(content: str, prompt_tokens: int = 10, completion_tokens: int = 5, cost: float = 0.001) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "gen-1",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost": cost,
            },
        },
    )


class Server:
    """Mock OpenRouter: replies come from a queue (or a function of the request); records request bodies."""

    def __init__(self, replies=None, fn=None):
        self.replies, self.fn, self.bodies = list(replies or []), fn, []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        return self.fn(body) if self.fn else self.replies.pop(0)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Returns a function that wires llm to a mock server; sleeps are recorded instead of waited."""
    sleeps: list[float] = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_sleep", sleeps.append)

    def _setup(server: Server, caps=None, models=None) -> list[float]:
        settings = llm.Settings(
            base_url="https://openrouter.ai/api/v1",
            timeout_s=5,
            max_attempts=4,
            cache_dir=tmp_path / "cache",
            log_path=tmp_path / "logs" / "llm_calls.jsonl",
            models_cache=tmp_path / "models.json",
            models=models or MODELS,
            temperature={"generator": 0.0, "judge": 0.0, "simulator": 0.7},
        )
        capabilities = {m: set(caps if caps is not None else JSON_SCHEMA_CAPS) for m in MODELS.values()}
        llm.configure(
            settings=settings,
            http_client=httpx2.Client(transport=httpx2.MockTransport(server)),
            capabilities=capabilities,
            tracing=False,
        )
        return sleeps

    yield _setup
    llm.configure()


def log_lines(tmp_path) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "logs" / "llm_calls.jsonl").read_text().splitlines()]


USER = [{"role": "user", "content": "Classify: Spark crashes on join"}]


def test_cache_hit_makes_no_second_request(setup, tmp_path):
    server = Server([chat("bug")])
    setup(server)
    assert llm.complete(USER, role="generator", component="c1") == "bug"
    assert llm.complete(USER, role="generator", component="c1") == "bug"
    assert len(server.bodies) == 1
    first, second = log_lines(tmp_path)
    assert (first["cached"], second["cached"]) == (False, True)
    assert first["cost"] == 0.001 and second["cost"] == 0.0 and second["prompt_tokens"] == 10


def test_retries_429_and_503_with_backoff(setup):
    server = Server(
        [
            httpx2.Response(429, headers={"Retry-After": "3"}, json={"error": {"message": "rate limit"}}),
            httpx2.Response(503, json={"error": {"message": "unavailable"}}),
            chat("ok"),
        ]
    )
    sleeps = setup(server)
    assert llm.complete(USER, role="generator", component="c1") == "ok"
    assert len(server.bodies) == 3
    assert sleeps[0] == 3.0 and 2.0 <= sleeps[1] <= 2.5  # Retry-After honoured, then 2**1 + jitter


def test_provider_error_in_200_body_is_retried(setup, tmp_path):
    server = Server(
        [
            httpx2.Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "m",
                    "choices": [],
                    "error": {"message": "upstream timeout"},
                },
            ),
            chat("ok"),
        ]
    )
    setup(server)
    assert llm.complete(USER, role="generator", component="c1") == "ok"
    assert log_lines(tmp_path)[0]["attempts"] == 2


def test_400_is_not_retried(setup, tmp_path):
    server = Server([httpx2.Response(400, json={"error": {"message": "bad request"}})])
    setup(server)
    with pytest.raises(openai.BadRequestError):
        llm.complete(USER, role="generator", component="c1")
    assert len(server.bodies) == 1
    assert log_lines(tmp_path)[0]["status"] == "error"


def test_gives_up_after_max_attempts(setup):
    server = Server(fn=lambda body: httpx2.Response(502, json={"error": {"message": "bad gateway"}}))
    setup(server)
    with pytest.raises(llm.LLMError, match="after 4 attempts"):
        llm.complete(USER, role="generator", component="c1")
    assert len(server.bodies) == 4


def test_json_schema_mode_returns_validated_object(setup):
    server = Server([chat('{"label": "bug", "confidence": 0.9}')])
    setup(server)
    out = llm.complete(USER, role="generator", component="c1", schema=Verdict)
    assert out == Verdict(label="bug", confidence=0.9)
    rf = server.bodies[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["name"] == "Verdict"
    assert rf["json_schema"]["schema"]["required"] == ["label", "confidence"]


def test_repair_retry_fixes_invalid_output(setup, tmp_path):
    server = Server([chat('{"label": "bug"}'), chat('{"label": "bug", "confidence": 0.7}')])
    setup(server)
    out = llm.complete(USER, role="generator", component="c1", schema=Verdict)
    assert out.confidence == 0.7
    repair_messages = server.bodies[1]["messages"]
    assert repair_messages[-2] == {"role": "assistant", "content": '{"label": "bug"}'}
    assert "confidence" in repair_messages[-1]["content"]  # the validation error is passed back
    assert [r["repair"] for r in log_lines(tmp_path)] == [False, True]


def test_repair_failure_raises_output_error(setup):
    server = Server([chat("not json"), chat("still not json")])
    setup(server)
    with pytest.raises(llm.LLMOutputError) as info:
        llm.complete(USER, role="generator", component="c1", schema=Verdict)
    assert info.value.raw == "still not json"


@pytest.mark.parametrize("caps, response_format", [(set(), None), ({"response_format"}, {"type": "json_object"})])
def test_json_in_prompt_mode_without_structured_outputs(setup, tmp_path, caps, response_format):
    server = Server([chat('Here you go:\n```json\n{"label": "idea", "confidence": 0.5}\n```')])
    setup(server, caps=caps)
    out = llm.complete(
        [{"role": "system", "content": "You classify tickets."}, *USER],
        role="generator",
        component="c1",
        schema=Verdict,
    )
    assert out.label == "idea"
    body = server.bodies[0]
    assert body.get("response_format") == response_format
    assert (
        body["messages"][0]["content"].startswith("You classify tickets.")
        and "JSON schema" in body["messages"][0]["content"]
    )
    assert log_lines(tmp_path)[0]["mode"] == ("prompt" if not caps else "json_object")


def test_placeholder_model_raises_config_error(setup):
    server = Server([])
    setup(server, models={**MODELS, "judge": llm.PLACEHOLDER})
    with pytest.raises(llm.LLMConfigError, match="models.judge"):
        llm.complete(USER, role="judge", component="judge_c1")
    assert server.bodies == []


def test_temperature_defaults_and_judge_forced_to_zero(setup):
    server = Server(fn=lambda body: chat("x"))
    setup(server)
    llm.complete(USER, role="judge", component="j", temperature=0.9)
    llm.complete(USER, role="simulator", component="s")
    llm.complete(USER, role="generator", component="g", temperature=0.3)
    assert [b["temperature"] for b in server.bodies] == [0.0, 0.7, 0.3]


def test_max_tokens_is_sent_and_part_of_cache_key(setup):
    server = Server(fn=lambda body: chat("x"))
    setup(server)
    llm.complete(USER, role="generator", component="c1", max_tokens=50)
    llm.complete(USER, role="generator", component="c1", max_tokens=100)
    llm.complete(USER, role="generator", component="c1", max_tokens=50)  # cache hit
    assert [b.get("max_tokens") for b in server.bodies] == [50, 100]


def test_log_line_has_all_fields(setup, tmp_path):
    setup(Server([chat("x")]))
    llm.complete(USER, role="generator", component="c1", session_id="s-42")
    (line,) = log_lines(tmp_path)
    assert set(line) == set(llm.LOG_FIELDS)
    assert line["component"] == "c1" and line["session_id"] == "s-42" and line["model"] == "prov/gen"
    assert line["mode"] == "text" and line["status"] == "ok" and line["latency_ms"] >= 0


def test_concurrent_calls_are_thread_safe(setup, tmp_path):
    def reply(body):
        time.sleep(random.uniform(0, 0.02))
        return chat("answer " + body["messages"][-1]["content"])

    server = Server(fn=reply)
    setup(server)
    prompts = [f"q{i}" for i in range(20)]

    def call(p):
        return llm.complete([{"role": "user", "content": p}], role="generator", component="c1")

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(call, prompts)) == [f"answer {p}" for p in prompts]
    lines = log_lines(tmp_path)  # every line must parse
    assert len(lines) == 20 and all(set(r) == set(llm.LOG_FIELDS) and not r["cached"] for r in lines)
    files = list((tmp_path / "cache").rglob("*"))
    assert len([f for f in files if f.is_file()]) == 20 and not [f for f in files if f.name.startswith(".tmp-")]
    assert all(json.loads(f.read_text())["text"].startswith("answer") for f in files if f.is_file())

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(call, prompts))
    assert len(server.bodies) == 20 and sum(r["cached"] for r in log_lines(tmp_path)) == 20


def test_model_override_bypasses_role_model(setup, tmp_path):
    server = Server([chat("x")])
    setup(server, models={**MODELS, "generator": llm.PLACEHOLDER})
    llm.complete(USER, role="generator", component="bakeoff", model="other/model-1")
    assert server.bodies[0]["model"] == "other/model-1"
    assert log_lines(tmp_path)[0]["model"] == "other/model-1"


def test_reasoning_is_sent_in_body_and_changes_cache_key(setup):
    server = Server(fn=lambda body: chat("x"))
    setup(server)
    llm.complete(USER, role="generator", component="c1")
    llm.complete(USER, role="generator", component="c1", reasoning={"effort": "none"})
    llm.complete(USER, role="generator", component="c1", reasoning={"effort": "none"})  # cache hit
    assert len(server.bodies) == 2
    assert "reasoning" not in server.bodies[0] and server.bodies[1]["reasoning"] == {"effort": "none"}
    assert server.bodies[1]["usage"] == {"include": True}


def test_reasoning_tokens_are_logged(setup, tmp_path):
    response = chat("x")
    payload = json.loads(response.content)
    payload["usage"]["completion_tokens_details"] = {"reasoning_tokens": 321}
    setup(Server([httpx2.Response(200, json=payload)]))
    llm.complete(USER, role="generator", component="c1")
    assert log_lines(tmp_path)[0]["reasoning_tokens"] == 321
