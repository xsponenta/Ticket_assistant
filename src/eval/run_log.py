"""LLM-call metrics from logs/llm_calls.jsonl for eval scripts (cost, latency, tokens; budget guard).

Calls of an eval are identified by session ids with a fixed prefix. Metrics use the FIRST uncached log line of each
(session, repair) pair that the current run used, so a rerun served from the cache reproduces the numbers.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any


def read_lines(path: Path, offset: int = 0) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        f.seek(offset)
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:  # a line being written right now
                continue
    return rows


def paid_calls(all_rows: list[dict[str, Any]], run_rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """First uncached line of every (session, repair) pair that appears in this run and starts with `prefix`."""
    used = {(r["session_id"], bool(r["repair"])) for r in run_rows if (r.get("session_id") or "").startswith(prefix)}
    first: dict[tuple[str, bool], dict[str, Any]] = {}
    for r in all_rows:
        key = (r.get("session_id") or "", bool(r["repair"]))
        if key in used and not r["cached"]:
            first.setdefault(key, r)
    return list(first.values())


def call_metrics(calls: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [c for c in calls if c["status"] == "ok"]
    latencies = sorted(c["latency_ms"] for c in ok)
    cost = sum(c.get("cost") or 0.0 for c in calls)
    return {
        "calls": len(calls),
        "call_errors": len(calls) - len(ok),
        "repairs": sum(bool(c["repair"]) for c in calls),
        "latency_p50_ms": round(statistics.median(latencies)) if latencies else None,
        "latency_p95_ms": round(latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]) if latencies else None,
        "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in calls),
        "completion_tokens": sum(c.get("completion_tokens") or 0 for c in calls),
        "cost": round(cost, 6),
        "cost_per_100_calls": round(100 * cost / len(calls), 5) if calls else None,
    }


class Budget:
    """Spend of this run (uncached calls with the session prefix), read from the log."""

    def __init__(self, limit: float, log_path: Path, prefix: str) -> None:
        self.limit, self.log_path, self.prefix = limit, log_path, prefix
        self.offset = log_path.stat().st_size if log_path.exists() else 0

    def run_rows(self) -> list[dict[str, Any]]:
        return read_lines(self.log_path, self.offset)

    def spent(self) -> float:
        return sum(
            r.get("cost") or 0.0
            for r in self.run_rows()
            if (r.get("session_id") or "").startswith(self.prefix) and not r["cached"]
        )

    def exceeded(self) -> bool:
        return self.spent() > self.limit
