"""Model bake-off on VAL data only (never test): classification, bug-field extraction, simulated-user check.

Every call goes through src/llm.py (model override, role-based temperature, cache, log). Metrics are computed
from the first uncached log line of each call, so a rerun is served from the cache and reproduces the numbers.

Usage:
    python scripts/model_bakeoff.py --models a,b,a@reasoning-min --limit 1     # smoke run + projected full cost
    python scripts/model_bakeoff.py --models a,b,a@reasoning-min --budget 1.0  # full run
    python scripts/model_bakeoff.py --report eval/results/model_bakeoff_<ts>.json  # re-render the report only

A config is an OpenRouter model id, optionally with "@reasoning-min": reasoning off where possible, otherwise the
lowest supported effort.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src" / "data"), str(Path(__file__).resolve().parent)]

from build_eval import BUG_SIGNAL_RES, bug_signals, n_words  # noqa: E402
from list_models import fetch_models, per_million  # noqa: E402

from src import llm  # noqa: E402
from src.prompting import Prompt, load_prompt  # noqa: E402

SEED = 42
CLASSES = ["bug", "feature", "task", "idea"]
N_PER_CLASS, N_EXTRACT, N_SIMULATOR = 10, 10, 5
CLS_DESC_CHARS, EXTRACT_DESC_CHARS = 1500, 6000
GROUNDING_MIN_SHARE = 0.6
WORKERS = 6
RESULTS_DIR = ROOT / "eval" / "results"
REPORT_PATH = ROOT / "reports" / "model_selection.md"
SEP = "|"  # session id separator (model ids contain "/" and sometimes ":")

# ---------------------------------------------------------------- schemas


class Classification(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    rationale: str
    label: Literal["bug", "feature", "task", "idea"] = Field(alias="class")


class FieldValue(BaseModel):
    value: str | None
    status: Literal["confirmed", "missing"]

    @model_validator(mode="after")
    def consistent(self) -> FieldValue:
        if self.status == "confirmed" and not (self.value or "").strip():
            raise ValueError("status 'confirmed' needs a non-empty value")
        if self.status == "missing" and self.value is not None:
            raise ValueError("status 'missing' needs value null")
        return self


class BugExtraction(BaseModel):
    summary: FieldValue
    steps_to_reproduce: FieldValue
    expected_behavior: FieldValue
    actual_behavior: FieldValue
    environment: FieldValue


EXTRACTION_FIELDS = list(BugExtraction.model_fields)

# ---------------------------------------------------------------- prompts


def questions(prompt: Prompt) -> list[str]:
    return [
        re.sub(r"^\d+\.\s*", "", line).strip() for line in prompt.sections["questions"].splitlines() if line.strip()
    ]


# ---------------------------------------------------------------- data (VAL only)

SPARK_VERSION_RE = re.compile(r"\b(?:spark|pyspark)\s*(?:version\s*)?[:=]?\s*v?[1-4]\.\d", re.I)
ABSENT_INFO_RE = re.compile(
    r"\b\d+\s*(?:nodes?|workers?|executors?|machines?)\b|executor[ ._-]?memory|num[-_]executors|"
    r"spark\.executor\.instances",
    re.I,
)


def simulator_eligible(text: str) -> bool:
    """Spark version, expected and actual behaviour are in the ticket; cluster size / executor memory are NOT."""
    signals = bug_signals(text)
    return (
        bool(SPARK_VERSION_RE.search(text))
        and signals["expected"]
        and signals["actual"]
        and not ABSENT_INFO_RE.search(text)
    )


def load_val() -> tuple[pd.DataFrame, set[str]]:
    df = pd.read_parquet(ROOT / "data" / "processed" / "issues.parquet")
    splits = json.loads((ROOT / "data" / "processed" / "splits.json").read_text())
    return df[df.key.isin(set(splits["val"]))].reset_index(drop=True), set(splits["test"])


def select_items(val: pd.DataFrame, test_keys: set[str], limit: int | None = None) -> dict[str, list[str]]:
    rng = random.Random(SEED)
    per_class = min(N_PER_CLASS, limit) if limit else N_PER_CLASS
    classification: list[str] = []
    for cls in CLASSES:
        keys = sorted(val[val.target_class == cls].key)
        classification += sorted(rng.sample(keys, min(per_class, len(keys))))

    bugs = val[(val.target_class == "bug") & val.has_description].copy()
    bugs["n_signals"] = bugs.description_md.map(lambda d: sum(bug_signals(d).values()))
    bugs["n_words"] = bugs.description_md.map(n_words)
    ranked = bugs.sort_values(["n_signals", "n_words", "key"], ascending=[False, False, True])
    extraction = list(ranked.key[: min(N_EXTRACT, limit) if limit else N_EXTRACT])
    eligible = [
        k
        for k, s, d in zip(ranked.key, ranked.summary, ranked.description_md, strict=True)
        if simulator_eligible(f"{s}\n{d}")
    ]
    simulator = eligible[: min(N_SIMULATOR, limit) if limit else N_SIMULATOR]

    chosen = set(classification) | set(extraction) | set(simulator)
    assert chosen <= set(val.key), "bake-off items must come from the val split"
    assert not chosen & test_keys, "bake-off must never touch the test split"
    return {"classification": classification, "extraction": extraction, "simulator": simulator}


# ---------------------------------------------------------------- configs


@dataclass(frozen=True)
class Config:
    name: str
    model: str
    reasoning: dict[str, Any] | None
    price_in: float | None
    price_out: float | None
    reasoning_default: str

    @property
    def provider(self) -> str:
        return self.model.split("/")[0]


def minimal_reasoning(meta: dict[str, Any]) -> dict[str, Any] | None:
    """Reasoning off where possible, otherwise the lowest supported effort; None if it cannot be reduced."""
    info = meta.get("reasoning") or {}
    efforts = info.get("supported_efforts") or []
    for effort in ("none", "minimal", "low"):
        if effort in efforts and not (effort == "none" and info.get("mandatory")):
            return {"effort": effort}
    return None if info.get("mandatory") else {"enabled": False}


def parse_configs(spec: str, models_meta: dict[str, dict[str, Any]]) -> list[Config]:
    configs = []
    for name in (s.strip() for s in spec.split(",") if s.strip()):
        model, _, variant = name.partition("@")
        meta = models_meta.get(model)
        if meta is None:
            raise SystemExit(f"Unknown OpenRouter model: {model}")
        reasoning = None
        if variant == "reasoning-min":
            reasoning = minimal_reasoning(meta)
            if reasoning is None:
                raise SystemExit(f"{model}: reasoning is mandatory and has no lower effort to select")
        elif variant:
            raise SystemExit(f"Unknown variant @{variant} (supported: @reasoning-min)")
        info = meta.get("reasoning") or {}
        default = "mandatory" if info.get("mandatory") else "default-on" if info.get("default_enabled") else "off"
        if default == "mandatory" and info.get("default_effort"):
            default += f" ({info['default_effort']})"
        elif default == "default-on" and info.get("default_effort"):
            default += f" ({info['default_effort']})"
        configs.append(
            Config(
                name,
                model,
                reasoning,
                per_million(meta["pricing"].get("prompt")),
                per_million(meta["pricing"].get("completion")),
                default,
            )
        )
    return configs


# ---------------------------------------------------------------- calls


def session_id(prompt: Prompt, cfg: Config, task: str, key: str, turn: int | None = None) -> str:
    return SEP.join(["bakeoff", prompt.version, cfg.name, task, key, *([f"t{turn}"] if turn else [])])


def classification_messages(prompt: Prompt, row: Any) -> list[dict[str, str]]:
    description = row.description_md[:CLS_DESC_CHARS] or "(no description)"
    return [
        {"role": "system", "content": prompt.sections["system"]},
        {"role": "user", "content": prompt.render("user", summary=row.summary, description=description)},
    ]


def extraction_input(row: Any) -> tuple[str, str]:
    return row.summary, row.description_md[:EXTRACT_DESC_CHARS]


def run_item(cfg: Config, task: str, row: Any, prompts: dict[str, Prompt]) -> dict[str, Any]:
    prompt = prompts[task]
    common = {"model": cfg.model, "reasoning": cfg.reasoning}
    result: dict[str, Any] = {"config": cfg.name, "task": task, "key": row.key, "error": None}
    if task == "classification":
        result["gold"] = row.target_class  # recorded before the call: a failed call counts as a wrong prediction
    try:
        if task == "classification":
            out = llm.complete(
                classification_messages(prompt, row),
                role="generator",
                component="bakeoff_classification",
                session_id=session_id(prompt, cfg, task, row.key),
                schema=Classification,
                temperature=0,
                **common,
            )
            result.update(pred=out.label, rationale=out.rationale)
        elif task == "extraction":
            summary, description = extraction_input(row)
            messages = [
                {"role": "system", "content": prompt.sections["system"]},
                {"role": "user", "content": prompt.render("user", summary=summary, description=description)},
            ]
            out = llm.complete(
                messages,
                role="generator",
                component="bakeoff_extraction",
                session_id=session_id(prompt, cfg, task, row.key),
                schema=BugExtraction,
                temperature=0,
                **common,
            )
            result["output"] = out.model_dump()
        else:  # simulator: a 3-turn dialogue
            summary, description = extraction_input(row)
            messages = [
                {"role": "system", "content": prompt.render("system", summary=summary, description=description)}
            ]
            result["transcript"] = []
            for turn, question in enumerate(questions(prompt), 1):
                messages.append({"role": "user", "content": question})
                reply = llm.complete(
                    messages,
                    role="simulator",
                    component="bakeoff_simulator",
                    session_id=session_id(prompt, cfg, task, row.key, turn),
                    **common,
                )
                messages.append({"role": "assistant", "content": reply})
                result["transcript"].append({"question": question, "reply": reply})
    except Exception as exc:  # one failing item must not stop the bake-off
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return result


class Budget:
    """Spend of this run, read from the LLM log (lines appended after the run started)."""

    def __init__(self, limit: float, log_path: Path) -> None:
        self.limit, self.log_path = limit, log_path
        self.offset = log_path.stat().st_size if log_path.exists() else 0

    def spent(self) -> float:
        if not self.log_path.exists():
            return 0.0
        total = 0.0
        with self.log_path.open(encoding="utf-8") as f:
            f.seek(self.offset)
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:  # a line being written right now
                    continue
                if (row.get("session_id") or "").startswith("bakeoff") and not row["cached"]:
                    total += row.get("cost") or 0.0
        return total

    def run_rows(self) -> list[dict[str, Any]]:
        """Log lines written since the run started."""
        if not self.log_path.exists():
            return []
        with self.log_path.open(encoding="utf-8") as f:
            f.seek(self.offset)
            return [json.loads(line) for line in f if line.strip()]

    def exceeded(self) -> bool:
        return self.spent() > self.limit


def run(
    configs: list[Config], items: dict[str, list[str]], val: pd.DataFrame, prompts: dict[str, Prompt], budget: Budget
) -> list[dict[str, Any]]:
    rows = {r.key: r for r in val.itertuples()}
    results: list[dict[str, Any]] = []
    for cfg in configs:
        jobs = [(task, key) for task in ("classification", "extraction", "simulator") for key in items[task]]

        def work(job: tuple[str, str], cfg: Config = cfg) -> dict[str, Any]:
            task, key = job
            if budget.exceeded():
                return {"config": cfg.name, "task": task, "key": key, "error": "skipped: budget exceeded"}
            return run_item(cfg, task, rows[key], prompts)

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results += list(pool.map(work, jobs))
        errors = sum(1 for r in results if r["config"] == cfg.name and r["error"])
        print(f"  {cfg.name:<48} done ({len(jobs)} items, {errors} errors); spent so far ${budget.spent():.4f}")
    return results


# ---------------------------------------------------------------- metrics (deterministic)


def macro_f1(gold: list[str], pred: list[str | None], labels: list[str] = CLASSES) -> float:
    f1s = []
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, pred, strict=True))
        fp = sum(g != label and p == label for g, p in zip(gold, pred, strict=True))
        fn = sum(g == label and p != label for g, p in zip(gold, pred, strict=True))
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1s) / len(f1s)


def bootstrap_ci(gold: list[str], pred: list[str | None], metric, n: int = 1000) -> tuple[float, float]:
    rng = random.Random(SEED)
    idx = range(len(gold))
    values = sorted(
        metric([gold[i] for i in sample], [pred[i] for i in sample])
        for sample in ([rng.choice(idx) for _ in idx] for _ in range(n))
    )
    return values[int(0.025 * n)], values[int(0.975 * n) - 1]


def accuracy(gold: list[str], pred: list[str | None]) -> float:
    return sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold) if gold else 0.0


STOPWORDS = set(
    """a an the and or but if of to in on at by for with from into is are was were be been being it its this that these
    those as not no can could should would will we you they i he she our your their there here which who what when where
    how do does did have has had also just only all any some such than too very via per so then when while""".split()
)
TOKEN_RE = re.compile(r"[a-z0-9_]+")
VERSION_ENV_RE = BUG_SIGNAL_RES["version_env"][0][1]


def content_words(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def grounding(extraction: dict[str, Any], input_text: str) -> list[dict[str, Any]]:
    """For every confirmed field: share of its content words found in the input; flag possibly invented values."""
    vocab = set(TOKEN_RE.findall(input_text.lower()))
    has_env = bool(VERSION_ENV_RE.search(input_text))
    out = []
    for field in EXTRACTION_FIELDS:
        item = extraction.get(field) or {}
        if item.get("status") != "confirmed":
            continue
        words = content_words(item.get("value") or "")
        share = sum(w in vocab for w in words) / len(words) if words else 1.0
        reasons = []
        if share < GROUNDING_MIN_SHARE:
            reasons.append(f"only {share:.0%} of its words are in the input")
        if field == "environment" and not has_env:
            reasons.append("no version/environment mention in the input")
        out.append({"field": field, "share": round(share, 3), "flagged": bool(reasons), "reason": "; ".join(reasons)})
    return out


AI_RE = re.compile(r"\bas an ai\b|\bi am an ai\b|\bi'm an ai\b|language model|\bchatbot\b|\bsimulat(?:ion|ed)\b", re.I)
FIRST_PERSON_RE = re.compile(r"\b(?:i|i'm|i've|i'd|my|me|we|our|us)\b", re.I)
# Simulator checks v2 (revised after reading the v1 transcripts, see CHECKS_NOTE):
# - Q1 "volunteered" = environment details other than the Spark version (a regression report's expected
#   behaviour legitimately names Spark versions);
# - Q3 honest = no invented number AND (admits not knowing OR answers only with ticket-grounded facts such as
#   "I run it locally / in one Docker container" when the ticket says so).
CHECKS_VERSION = "v2"
CHECKS_NOTE = (
    "Simulator checks v2, revised after reading the v1 transcripts and before choosing models: (1) the Q1 "
    "'volunteered' check no longer counts Spark versions, because in 3 of the 5 tickets the expected behaviour "
    "itself is a version regression (every model failed v1 on those 3); (2) Q3 honesty also accepts phrasings like "
    '"I don\'t have those details" and answers grounded in the ticket (local run, single node, Docker, spark-shell).'
)
VOLUNTEER_RE = re.compile(
    r"\b(?:python|java|jdk|scala)\s*v?\d+(?:\.\d+)+|\b(?:yarn|kubernetes|k8s|emr|databricks|dataproc|mesos)\b", re.I
)
UNKNOWN_RE = re.compile(
    r"not sure|don't know|do not know|no idea|unsure|not certain|can't (?:say|recall|remember)|"
    r"cannot (?:say|recall|remember)|i'd have to check|haven't checked|not something i|"
    r"don't have (?:any |the |those |that |this |exact |specific |precise |a |my )*"
    r"(?:information|details|info|numbers?|figures?|settings?|data|count)|"
    r"not (?:mentioned|specified|documented|recorded) in my|didn't (?:note|record|document|check)",
    re.I,
)
LOCAL_RE = re.compile(r"\blocal(?:ly)?\b|local\[|single[- ]node|\bone node\b|\bdocker\b|spark-shell|\blaptop\b", re.I)
INVENTED_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:nodes?|workers?|machines?|executors?|gb|gib|mb|g|m)\b", re.I)


def shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    words = TOKEN_RE.findall(text.lower())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def ticket_containment(reply: str, ticket: str) -> float:
    """Share of the ticket's 5-word sequences that reappear in the reply (1.0 = the ticket was pasted)."""
    ticket_sh = shingles(ticket)
    return len(ticket_sh & shingles(reply)) / len(ticket_sh) if ticket_sh else 0.0


def check_reply(question_no: int, reply: str, ticket: str) -> dict[str, bool]:
    checks = {
        "no_ai_mention": not AI_RE.search(reply),
        "brief": n_words(reply) <= 80,
        "first_person": bool(FIRST_PERSON_RE.search(reply)),
        "no_ticket_dump": ticket_containment(reply, ticket) < 0.4,
    }
    if question_no == 1:
        checks["no_volunteered_env"] = not VOLUNTEER_RE.search(reply)
    if question_no == 3:
        grounded_local = bool(LOCAL_RE.search(reply) and LOCAL_RE.search(ticket))
        checks["honest_about_unknown"] = bool(UNKNOWN_RE.search(reply)) or grounded_local
        checks["no_invented_number"] = not INVENTED_RE.search(reply)
    return checks


def first_calls(log_rows: list[dict[str, Any]], config_name: str) -> dict[tuple[str, bool], dict[str, Any]]:
    """First uncached log line per (session, repair) of a config: the call that was actually paid for."""
    first: dict[tuple[str, bool], dict[str, Any]] = {}
    for row in log_rows:
        sid = row.get("session_id") or ""
        parts = sid.split(SEP)
        if len(parts) >= 5 and parts[0] == "bakeoff" and parts[2] == config_name and not row["cached"]:
            first.setdefault((sid, bool(row["repair"])), row)
    return first


def call_metrics(calls: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [c for c in calls if c["status"] == "ok"]
    latencies = sorted(c["latency_ms"] for c in ok)
    cost = sum(c.get("cost") or 0.0 for c in calls)
    return {
        "calls": len(calls),
        "call_errors": len(calls) - len(ok),
        "latency_p50_ms": round(statistics.median(latencies)) if latencies else None,
        "latency_p95_ms": round(latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]) if latencies else None,
        "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in calls),
        "completion_tokens": sum(c.get("completion_tokens") or 0 for c in calls),
        "reasoning_tokens": sum(c.get("reasoning_tokens") or 0 for c in calls),
        "cost": round(cost, 6),
        "cost_unknown_calls": sum(c.get("cost") is None for c in ok),
        "cost_per_100_calls": round(100 * cost / len(calls), 5) if calls else None,
    }


def config_metrics(
    cfg: Config,
    results: list[dict[str, Any]],
    log_rows: list[dict[str, Any]],
    run_rows: list[dict[str, Any]],
    inputs: dict[str, str],
) -> dict[str, Any]:
    """Validity and repairs come from THIS run's log lines (`run_rows`); latency, tokens and cost come from the
    first paid (uncached) call of each (session, repair) that this run used, wherever in the log it happened."""
    mine = [r for r in results if r["config"] == cfg.name]
    used = {
        (row["session_id"], bool(row["repair"]))
        for row in run_rows
        if (row.get("session_id") or "").split(SEP)[2:3] == [cfg.name]
    }
    first = {k: v for k, v in first_calls(log_rows, cfg.name).items() if k in used}
    repaired = {tuple(sid.split(SEP)[3:5]) for (sid, rep) in used if rep}  # (task, key)
    m: dict[str, Any] = {"overall": call_metrics(list(first.values()))}

    for task in ("classification", "extraction", "simulator"):
        task_calls = [c for (sid, _), c in first.items() if sid.split(SEP)[3] == task]
        m[task] = {"calls": call_metrics(task_calls)}

    cls = [r for r in mine if r["task"] == "classification" and not str(r["error"]).startswith("skipped")]
    if cls:
        gold = [r["gold"] for r in cls]
        pred = [r.get("pred") for r in cls]
        m["classification"].update(
            n=len(cls),
            accuracy=round(accuracy(gold, pred), 3),
            macro_f1=round(macro_f1(gold, pred), 3),
            macro_f1_ci=[round(x, 3) for x in bootstrap_ci(gold, pred, macro_f1)],
            first_try_valid=round(
                sum(not r["error"] and (r["task"], r["key"]) not in repaired for r in cls) / len(cls), 3
            ),
            repair_rate=round(sum((r["task"], r["key"]) in repaired for r in cls) / len(cls), 3),
            failures=sum(bool(r["error"]) for r in cls),
        )

    ext = [r for r in mine if r["task"] == "extraction" and not str(r["error"]).startswith("skipped")]
    if ext:
        flags, confirmed = [], 0
        for r in ext:
            if r.get("output"):
                g = grounding(r["output"], inputs[r["key"]])
                r["grounding"] = g
                confirmed += len(g)
                flags += [{"key": r["key"], **f} for f in g if f["flagged"]]
        m["extraction"].update(
            n=len(ext),
            first_try_valid=round(
                sum(not r["error"] and (r["task"], r["key"]) not in repaired for r in ext) / len(ext), 3
            ),
            repair_rate=round(sum((r["task"], r["key"]) in repaired for r in ext) / len(ext), 3),
            failures=sum(bool(r["error"]) for r in ext),
            confirmed_fields=confirmed,
            grounded_confirmed=round((confirmed - len(flags)) / confirmed, 3) if confirmed else None,
            possibly_invented=len(flags),
            flags=flags,
        )

    sim = [r for r in mine if r["task"] == "simulator" and not str(r["error"]).startswith("skipped")]
    if sim:
        replies, honest = [], 0
        for r in sim:
            for no, turn in enumerate(r.get("transcript") or [], 1):
                checks = check_reply(no, turn["reply"], inputs[r["key"]])
                turn["checks"] = checks
                replies.append(checks)
                if no == 3:
                    honest += checks["honest_about_unknown"] and checks["no_invented_number"]
        names = sorted({k for c in replies for k in c})
        m["simulator"].update(
            dialogues=len(sim),
            replies=len(replies),
            failures=sum(bool(r["error"]) for r in sim),
            pass_rate={
                n: round(sum(c[n] for c in replies if n in c) / max(1, sum(n in c for c in replies)), 3) for n in names
            },
            in_character=round(sum(all(c.values()) for c in replies) / len(replies), 3) if replies else None,
            q3_honest=honest,
        )
    return m


def propose(configs: list[Config], metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Rule-based proposal (rules are printed in the report)."""

    def get(name: str, task: str, key: str, default: float = 0.0) -> float:
        value = metrics[name].get(task, {}).get(key)
        return default if value is None else value

    cost = {c.name: metrics[c.name]["overall"]["cost_per_100_calls"] or 0.0 for c in configs}
    best_f1 = max(get(c.name, "classification", "macro_f1") for c in configs)
    gen_pool = [
        c
        for c in configs
        if get(c.name, "classification", "macro_f1") >= best_f1 - 0.05
        and get(c.name, "extraction", "first_try_valid") >= 0.9
        and get(c.name, "extraction", "possibly_invented", 99) <= 1
    ]
    generator = min(gen_pool, key=lambda c: (cost[c.name], c.name)) if gen_pool else None

    def strength(c: Config) -> tuple[float, float]:
        return get(c.name, "classification", "macro_f1"), get(c.name, "extraction", "first_try_valid")

    judge_pool = [c for c in configs if generator is None or c.provider != generator.provider]
    judge = max(judge_pool, key=lambda c: (*strength(c), -cost[c.name])) if judge_pool else None
    sim_pool = [
        c
        for c in configs
        if get(c.name, "simulator", "in_character") >= 0.9 and get(c.name, "simulator", "q3_honest") >= 4
    ]
    simulator = min(sim_pool, key=lambda c: (cost[c.name], c.name)) if sim_pool else None
    return {
        "generator": generator.name if generator else None,
        "judge": judge.name if judge else None,
        "simulator": simulator.name if simulator else None,
        "generator_pool": [c.name for c in gen_pool],
        "simulator_pool": [c.name for c in sim_pool],
    }


def project_full_cost(
    configs: list[Config], results: list[dict[str, Any]], log_rows: list[dict[str, Any]], full_counts: dict[str, int]
) -> dict[str, float]:
    """Smoke run → projected cost of the full run (measured cost per item × full item count)."""
    projection = {}
    for cfg in configs:
        first = first_calls(log_rows, cfg.name)
        total = 0.0
        for task, n_full in full_counts.items():
            keys = {r["key"] for r in results if r["config"] == cfg.name and r["task"] == task}
            spent = sum((c.get("cost") or 0.0) for (sid, _), c in first.items() if sid.split(SEP)[3] == task)
            total += spent / len(keys) * n_full if keys else 0.0
        projection[cfg.name] = round(total, 4)
    return projection


# ---------------------------------------------------------------- report


def fmt(value: Any, spec: str = "") -> str:
    if value is None:
        return "—"
    return format(value, spec) if spec else str(value)


def md_cell(text: Any, limit: int = 160) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    s = s if len(s) <= limit else s[: limit - 1] + "…"
    return s.replace("|", "\\|")


def render_report(data: dict[str, Any], review: str | None = None) -> str:
    configs = [Config(**c) for c in data["configs"]]
    metrics, proposal = data["metrics"], data["proposal"]
    names = [c.name for c in configs]
    total_cost = sum(metrics[n]["overall"]["cost"] for n in names)
    lines = [
        "# Model selection: bake-off on val data",
        "",
        f"_Run {data['created_at']} · git `{data['git_commit']}` · `scripts/model_bakeoff.py` · results "
        f"`{data['results_file']}` · total cost ${total_cost:.4f}. Val split only; no test item was used._",
        "",
        f"Prompts: {', '.join(f'`{v}`' for v in data['prompt_versions'].values())}. "
        f"Items: {len(data['items']['classification'])} classification "
        f"({N_PER_CLASS} per class, seed {SEED}), {len(data['items']['extraction'])} extraction "
        f"(richest val bugs), {len(data['items']['simulator'])} simulator dialogues × 3 questions.",
        "",
        "## Configurations",
        "",
        "| Config | Provider | $/1M in | $/1M out | Reasoning as served | Reasoning in this run |",
        "|---|---|---:|---:|---|---|",
    ]
    for c in configs:
        lines.append(
            f"| `{c.name}` | {c.provider} | {fmt(c.price_in, '.3f')} | {fmt(c.price_out, '.3f')} | "
            f"{c.reasoning_default} | {json.dumps(c.reasoning) if c.reasoning else 'as served'} |"
        )

    lines += [
        "",
        f"## Classification (n = {len(data['items']['classification'])}, 10 per class)",
        "",
        "| Config | Accuracy | Macro-F1 | 95% CI (bootstrap) | First-try valid | Repairs | Failures |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for n in names:
        m = metrics[n].get("classification", {})
        ci = m.get("macro_f1_ci")
        lines.append(
            f"| `{n}` | {fmt(m.get('accuracy'), '.3f')} | **{fmt(m.get('macro_f1'), '.3f')}** | "
            f"{f'{ci[0]:.2f}–{ci[1]:.2f}' if ci else '—'} | {fmt(m.get('first_try_valid'), '.0%')} | "
            f"{fmt(m.get('repair_rate'), '.0%')} | {fmt(m.get('failures'))} |"
        )

    lines += [
        "",
        f"## Bug-field extraction (n = {len(data['items']['extraction'])})",
        "",
        "Grounding check (no LLM): a confirmed field is *possibly invented* if < 60% of its content words occur "
        "in the input, or if `environment` is confirmed although the input has no version/environment mention "
        "(EDA `version_env` regex).",
        "",
        "| Config | First-try valid | Repairs | Failures | Confirmed fields | Grounded-confirmed | Possibly invented |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for n in names:
        m = metrics[n].get("extraction", {})
        lines.append(
            f"| `{n}` | {fmt(m.get('first_try_valid'), '.0%')} | {fmt(m.get('repair_rate'), '.0%')} | "
            f"{fmt(m.get('failures'))} | {fmt(m.get('confirmed_fields'))} | "
            f"{fmt(m.get('grounded_confirmed'), '.0%')} | "
            f"**{fmt(m.get('possibly_invented'))}** |"
        )

    check_names = [
        "no_ai_mention",
        "brief",
        "first_person",
        "no_ticket_dump",
        "no_volunteered_env",
        "honest_about_unknown",
        "no_invented_number",
    ]
    lines += [
        "",
        f"## Simulated user (n = {len(data['items']['simulator'])} dialogues × 3 questions)",
        "",
        "Q3 asks for information that is **not** in the hidden ticket (cluster size, executor memory). "
        "In character = a reply passes every check that applies to it. Q3 honest = admits not knowing (or answers "
        "only with ticket-grounded facts) and invents no number.",
        "",
        f"_{CHECKS_NOTE}_",
        "",
        "| Config | In character | Q3 honest | " + " | ".join(check_names) + " | Failures |",
        "|---|---:|---:|" + "---:|" * len(check_names) + "---:|",
    ]
    for n in names:
        m = metrics[n].get("simulator", {})
        pr = m.get("pass_rate", {})
        lines.append(
            f"| `{n}` | {fmt(m.get('in_character'), '.0%')} | {fmt(m.get('q3_honest'))}/{m.get('dialogues', 0)} | "
            + " | ".join(fmt(pr.get(c), ".0%") for c in check_names)
            + f" | {fmt(m.get('failures'))} |"
        )

    lines += [
        "",
        "## Latency and cost (calls actually paid for, incl. repairs)",
        "",
        "| Config | Calls | p50 ms | p95 ms | Completion tok | Reasoning tok | Total $ | $ / 100 calls |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for n in names:
        o = metrics[n]["overall"]
        lines.append(
            f"| `{n}` | {o['calls']} | {fmt(o['latency_p50_ms'])} | {fmt(o['latency_p95_ms'])} | "
            f"{o['completion_tokens']:,} | {o['reasoning_tokens']:,} | {o['cost']:.4f} | "
            f"{fmt(o['cost_per_100_calls'], '.4f')} |"
        )
    unknown = {
        n: metrics[n]["overall"]["cost_unknown_calls"] for n in names if metrics[n]["overall"]["cost_unknown_calls"]
    }
    if unknown:
        lines.append(f"\nCost not reported by OpenRouter for some calls: {unknown}.")

    by_model: dict[str, list[Config]] = {}
    for c in configs:
        by_model.setdefault(c.model, []).append(c)
    pairs = [v for v in by_model.values() if len(v) > 1]
    if pairs:
        lines += [
            "",
            "## Reasoning as served vs minimised",
            "",
            "| Config | Macro-F1 | Extraction first-try | Possibly invented | p50 ms | Reasoning tok | $ / 100 calls |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for group in pairs:
            for c in group:
                m = metrics[c.name]
                lines.append(
                    f"| `{c.name}` | {fmt(m.get('classification', {}).get('macro_f1'), '.3f')} | "
                    f"{fmt(m.get('extraction', {}).get('first_try_valid'), '.0%')} | "
                    f"{fmt(m.get('extraction', {}).get('possibly_invented'))} | "
                    f"{fmt(m['overall']['latency_p50_ms'])} | "
                    f"{m['overall']['reasoning_tokens']:,} | {fmt(m['overall']['cost_per_100_calls'], '.4f')} |"
                )

    lines += [
        "",
        "## Extraction examples (first 3 of the 10 bugs, side by side)",
        "",
        "✓ = confirmed, — = missing, ⚠ = possibly invented (grounding check). Values cut to 160 characters; "
        f"full outputs in `{data['results_file']}`.",
        "",
    ]
    results = data["results"]
    for key in data["items"]["extraction"][:3]:
        lines += [
            f"### {key}",
            "",
            "<details><summary>Input given to the models (first 800 characters)</summary>",
            "",
            "````text",  # 4 backticks: the excerpt itself may contain ``` code blocks
            data["inputs"][key][:800],
            "````",
            "",
            "</details>",
            "",
        ]
        for field in EXTRACTION_FIELDS:
            lines += [f"**{field}**", "", "| Config | Status | Value |", "|---|---|---|"]
            for n in names:
                r = next((x for x in results if x["config"] == n and x["task"] == "extraction" and x["key"] == key), {})
                if not r.get("output"):
                    lines.append(f"| `{n}` | error | {md_cell(r.get('error'))} |")
                    continue
                item = r["output"][field]
                flagged = any(g["field"] == field and g["flagged"] for g in r.get("grounding", []))
                mark = "⚠ ✓" if flagged else ("✓" if item["status"] == "confirmed" else "—")
                lines.append(f"| `{n}` | {mark} | {md_cell(item['value'])} |")
            lines.append("")

    lines += [
        "## Proposal (rule-based; final choice is yours)",
        "",
        "- **Generator:** among configs with macro-F1 ≥ best − 0.05, extraction first-try valid ≥ 90% and "
        "possibly invented ≤ 1, the cheapest per 100 calls.",
        "- **Judge:** the strongest config (macro-F1, then extraction first-try valid) from a *different provider* "
        "than the generator.",
        "- **Simulator:** the cheapest config with in-character ≥ 90% and Q3 honest ≥ 4/5.",
        "",
        "| Role | Proposed config | Pool that met the rule |",
        "|---|---|---|",
        f"| generator | `{proposal['generator']}` | {', '.join(f'`{x}`' for x in proposal['generator_pool']) or '—'} |",
        f"| judge | `{proposal['judge']}` | different provider than the generator |",
        f"| simulator | `{proposal['simulator']}` | {', '.join(f'`{x}`' for x in proposal['simulator_pool']) or '—'} |",
        "",
        *([review.strip(), ""] if review else []),
        "## Limitations",
        "",
        "- Small samples: 40 classification items (macro-F1 CIs are wide), 10 bugs, 5 dialogues. The bake-off "
        "ranks models for a first choice; it is not an evaluation of the final components.",
        "- Zero-shot prompts (`*/v1`); component prompts will differ.",
        "- Grounding and simulator checks are heuristics (word overlap and regex); read the examples and "
        f"transcripts (`{data['transcripts_file']}`).",
        "- Prices and model behaviour are as served by OpenRouter on the run date.",
        "",
    ]
    return "\n".join(lines)


def render_transcripts(data: dict[str, Any]) -> str:
    lines = ["# Simulator transcripts (model bake-off)", ""]
    for r in data["results"]:
        if r["task"] != "simulator":
            continue
        lines += [f"## `{r['config']}` · {r['key']}", ""]
        if r.get("error"):
            lines += [f"Error: {r['error']}", ""]
        for no, turn in enumerate(r.get("transcript") or [], 1):
            failed = [k for k, v in (turn.get("checks") or {}).items() if not v]
            lines += [
                f"**Q{no}.** {turn['question']}",
                "",
                f"> {turn['reply']}".replace("\n", "\n> "),
                "",
                f"_checks failed: {', '.join(failed) or 'none'}_",
                "",
            ]
    return "\n".join(lines)


# ---------------------------------------------------------------- main


def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return sha.strip() + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def read_log() -> list[dict[str, Any]]:
    path = llm._settings().log_path
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_report(data: dict[str, Any], review: Path | None = None) -> None:
    review_text = review.read_text(encoding="utf-8") if review else None
    REPORT_PATH.write_text(render_report(data, review_text), encoding="utf-8")
    (ROOT / data["transcripts_file"]).write_text(render_transcripts(data), encoding="utf-8")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)} and {data['transcripts_file']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", help="comma-separated configs, e.g. a/b,a/b@reasoning-min")
    parser.add_argument(
        "--limit", type=int, help="smoke run: N per class / N bugs / N dialogues; prints projected cost"
    )
    parser.add_argument("--budget", type=float, default=1.0, help="stop submitting calls above this spend (USD)")
    parser.add_argument("--report", type=Path, help="re-render reports/model_selection.md from a results file")
    parser.add_argument("--review", type=Path, help="Markdown file with a hand-written review, inserted in the report")
    args = parser.parse_args()

    if args.report:
        write_report(json.loads(args.report.read_text()), args.review)
        return
    if not args.models:
        parser.error("--models is required (or --report)")

    models_meta = {m["id"]: m for m in fetch_models()}
    configs = parse_configs(args.models, models_meta)
    prompts = {t: load_prompt(f"bakeoff_{t}") for t in ("classification", "extraction", "simulator")}
    val, test_keys = load_val()
    items = select_items(val, test_keys, args.limit)
    rows = {r.key: r for r in val.itertuples()}
    inputs = {k: "\n".join(extraction_input(rows[k])) for k in set(items["extraction"]) | set(items["simulator"])}

    budget = Budget(args.budget, llm._settings().log_path)
    print(
        f"Bake-off on VAL: {len(configs)} configs; items {', '.join(f'{t} {len(k)}' for t, k in items.items())}; "
        f"budget ${args.budget:.2f}"
    )
    results = run(configs, items, val, prompts, budget)
    log_rows, run_rows = read_log(), budget.run_rows()
    metrics = {c.name: config_metrics(c, results, log_rows, run_rows, inputs) for c in configs}

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    kind = "model_bakeoff_smoke" if args.limit else "model_bakeoff"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_file = RESULTS_DIR / f"{kind}_{stamp}.json"
    data = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "results_file": str(results_file.relative_to(ROOT)),
        "transcripts_file": str(results_file.with_name(f"{kind}_{stamp}_transcripts.md").relative_to(ROOT)),
        "prompt_versions": {t: p.version for t, p in prompts.items()},
        "configs": [asdict(c) for c in configs],
        "items": items,
        "inputs": inputs,
        "spent_this_run": round(budget.spent(), 6),
        "budget_exceeded": budget.exceeded(),
        "metrics": metrics,
        "proposal": propose(configs, metrics),
        "results": results,
    }
    if args.limit:
        full = {"classification": N_PER_CLASS * len(CLASSES), "extraction": N_EXTRACT, "simulator": N_SIMULATOR}
        data["projected_full_cost"] = project_full_cost(configs, results, log_rows, full)
    results_file.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {data['results_file']}; spent this run ${data['spent_this_run']:.4f}")

    if args.limit:
        projection = data["projected_full_cost"]
        for name, cost in projection.items():
            print(f"  projected full run  {name:<48} ${cost:.4f}")
        print(f"  projected full run  TOTAL{'':<44} ${sum(projection.values()):.4f}")
        (ROOT / data["transcripts_file"]).write_text(render_transcripts(data), encoding="utf-8")
    else:
        write_report(data, args.review)


if __name__ == "__main__":
    main()
