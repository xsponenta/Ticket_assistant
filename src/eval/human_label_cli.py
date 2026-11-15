"""Human-ceiling check for C1: label 40 val issues by hand without seeing the Jira issue type.

Shows 40 val issues (10 per class, seed 7, drawn from the 325-item C1 LLM val subset and disjoint from the model
bake-off sample; see src/eval/samples.py), summary + first 1500
characters of the description, and the class definitions from src/schemas/ticket_types.yaml. Asks for
bug / feature / task / idea. Every answer is appended to data/eval/human_ceiling_val.jsonl, so it can be resumed.

Usage:
    python -m src.eval.human_label_cli            # label (resume where you stopped)
    python -m src.eval.human_label_cli --report   # your macro-F1 vs the Jira labels
"""

from __future__ import annotations

import argparse
import json
import shutil
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.eval.metrics import CLASSES, accuracy, bootstrap_ci, confusion, macro_f1, per_class_prf, recall_of
from src.eval.samples import human_ceiling_sample, load_split

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "eval" / "human_ceiling_val.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
DESC_CHARS = 1500


def read_labels(path: Path = OUT) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["key"]: r["human_label"] for r in map(json.loads, f) if r.get("human_label")}


def definitions() -> dict[str, str]:
    types = yaml.safe_load((ROOT / "src" / "schemas" / "ticket_types.yaml").read_text())
    return {cls: types["classes"][cls]["description"] for cls in CLASSES}


def show(row: Any, done: int, total: int, defs: dict[str, str]) -> None:
    width = min(110, shutil.get_terminal_size((110, 30)).columns)
    print("\n" + "═" * width)
    print(f" Human ceiling (C1)   [{done}/{total} labelled · {total - done} left]")
    print("─" * width)
    for i, cls in enumerate(CLASSES, 1):
        print(textwrap.fill(f"  {i}  {cls:<8} {defs[cls]}", width, subsequent_indent=" " * 14))
    print("─" * width)
    print(f"{row.key}")
    print(textwrap.fill("Summary: " + row.summary, width))
    description = row.description_md[:DESC_CHARS] or "(no description)"
    print(f"\nDescription (first {DESC_CHARS} chars):")
    print(description + ("…" if len(row.description_md) > DESC_CHARS else ""))
    print("─" * width)


def label_loop(rows: dict[str, Any], keys: list[str], labels: dict[str, str]) -> None:
    defs = definitions()
    for key in keys:
        if key in labels:
            continue
        show(rows[key], len(labels), len(keys), defs)
        while True:
            answer = input("Class [1 bug, 2 feature, 3 task, 4 idea], s = skip, q = quit: ").strip().lower()
            if answer in ("q", "s") or answer in {"1", "2", "3", "4", *CLASSES}:
                break
            print("  Please type 1–4, a class name, s or q.")
        if answer == "q":
            return
        if answer == "s":
            continue
        label = CLASSES[int(answer) - 1] if answer.isdigit() else answer
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            record = {"key": key, "human_label": label, "labeled_at": datetime.now(UTC).isoformat(timespec="seconds")}
            f.write(json.dumps(record) + "\n")
        labels[key] = label


def report(val: pd.DataFrame, keys: list[str], labels: dict[str, str]) -> dict[str, Any]:
    jira = dict(zip(val.key, val.target_class, strict=True))
    done = [k for k in keys if k in labels]
    gold, pred = [jira[k] for k in done], [labels[k] for k in done]
    low, high = bootstrap_ci(gold, pred, macro_f1)
    result = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_labelled": len(done),
        "n_items": len(keys),
        "accuracy": round(accuracy(gold, pred), 3),
        "macro_f1": round(macro_f1(gold, pred), 3),
        "macro_f1_ci95": [round(low, 3), round(high, 3)],
        "idea_recall": round(recall_of("idea")(gold, pred), 3),
        "per_class": {c: {k: round(v, 3) for k, v in m.items()} for c, m in per_class_prf(gold, pred).items()},
        "confusion_rows_gold_cols_pred": {"labels": CLASSES, "matrix": [row[:4] for row in confusion(gold, pred)]},
        "disagreements": [{"key": k, "jira": jira[k], "human": labels[k]} for k in done if jira[k] != labels[k]],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", action="store_true", help="macro-F1 of your labels vs the Jira labels")
    args = parser.parse_args()

    val = load_split("val")
    keys = human_ceiling_sample(val)
    labels = read_labels()
    if args.report:
        if not labels:
            raise SystemExit(f"No labels yet in {OUT}.")
        result = report(val, keys, labels)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"human_ceiling_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
        path.write_text(json.dumps(result, indent=1))
        print(json.dumps({k: v for k, v in result.items() if k != "disagreements"}, indent=1))
        print(f"{len(result['disagreements'])} disagreements; saved to {path.relative_to(ROOT)}")
        return
    try:
        label_loop({r.key: r for r in val.itertuples()}, keys, labels)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
    print(f"\n{len(labels)} of {len(keys)} labelled → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
