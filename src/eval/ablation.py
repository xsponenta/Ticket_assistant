"""The frozen C4/C5 ablation set (data/eval/gap_ablation.jsonl, built by src.eval.build_gap_ablation): loading, gold
labels and the test-hash check shared by eval/eval_c4.py and eval/eval_c5.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ABLATION = ROOT / "data" / "eval" / "gap_ablation.jsonl"
META = ROOT / "data" / "eval" / "gap_ablation_meta.json"
EXTRACTIONS = ROOT / "data" / "eval" / "gap_extractions.jsonl"
DESC_CHARS = 4000  # description characters in the ticket text (extraction input, C4's first turn, e2e hidden ticket)


def ticket_text(summary: str, description: str) -> str:
    return f"Summary: {summary.strip()}\n\nDescription:\n{(description or '')[:DESC_CHARS].strip()}"


def items_sha256(items: list[dict[str, Any]]) -> str:
    lines = sorted(json.dumps(i, ensure_ascii=False, sort_keys=True) for i in items)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def load_items(split: str, path: Path = ABLATION, meta: Path = META) -> list[dict[str, Any]]:
    """Items of one split ("dev" | "test"); the test items must match the hash frozen at build time."""
    if not path.exists():
        raise SystemExit("No ablation set yet: run `python -m src.eval.build_gap_ablation --build` first.")
    with path.open(encoding="utf-8") as f:
        items = [i for i in (json.loads(line) for line in f if line.strip()) if i["split"] == split]
    if split == "test" and items_sha256(items) != json.loads(meta.read_text())["test_sha256"]:
        raise SystemExit("Test items do not match test_sha256 in gap_ablation_meta.json: the frozen set changed.")
    return items


def variant_kind(item: dict[str, Any]) -> str:
    """original | minus (one or two fields deleted) | answered | unknown."""
    return item["variant"].split("_")[0]


def gold_label(item: dict[str, Any], field: str) -> str | None:
    """missing | unknown | present for a class field; None if excluded from the metrics (gold uncertain)."""
    if field in item["gold_missing"]:
        return "missing"
    if field in item["gold_unknown"]:
        return "unknown"
    if field in item["gold_present"]:
        return "present"
    return None


def user_text(item: dict[str, Any]) -> str:
    return "\n\n".join(t["content"] for t in item["conversation"] if t["role"] == "user")
