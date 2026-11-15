"""C4 gap detector evaluation on the frozen ablation set (data/eval/gap_ablation.jsonl). Deterministic metrics only.

python eval/eval_c4.py --split dev [--limit 20]
python eval/eval_c4.py --split test --confirm-test          # once, after approval (eval/c4_final_config.json)

Metrics (class fields; fields the gold extraction could not decide are excluded; `unknown` counts as resolved):
missing-field precision / recall / F1 (micro, per field, per class) and the "not confirmed" sensitivity view;
false-confirmed rate on deleted fields; grounding of confirmed evidence; answered -> confirmed; unknown detection;
false-unknown rate.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.components.gap_detector import detect  # noqa: E402
from src.eval.ablation import gold_label, load_items, user_text, variant_kind  # noqa: E402
from src.eval.lock import check_test_allowed  # noqa: E402
from src.eval.metrics import bootstrap_ci, per_class_prf  # noqa: E402
from src.eval.run_log import Budget, call_metrics, paid_calls, read_lines  # noqa: E402
from src.eval.spans import quote_grounded  # noqa: E402
from src.prompting import load_prompt  # noqa: E402
from src.schemas.ticket_fields import class_fields  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
FINAL_CONFIG = ROOT / "eval" / "c4_final_config.json"
EVAL_REPORT = ROOT / "reports" / "05_evaluation.md"
WORKERS = 6
BIN = ["missing", "resolved"]


def run(items: list[dict], split: str, budget: Budget) -> tuple[list[dict], str]:
    prompt = load_prompt("c4_gap")

    def one(item: dict) -> dict[str, Any]:
        if budget.exceeded():
            return {"item_id": item["item_id"], "error": "skipped: budget exceeded"}
        try:
            states = detect(
                item["conversation"],
                item["class"],
                prompt=prompt,
                session_id=f"c4|{split}|{prompt.version}|{item['item_id']}",
            )
        except Exception as exc:
            return {"item_id": item["item_id"], "error": f"{type(exc).__name__}: {exc}"[:300]}
        return {"item_id": item["item_id"], "states": {n: s.model_dump() for n, s in states.items()}}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(one, items)), prompt.version


def field_rows(items: list[dict], results: list[dict]) -> list[dict[str, Any]]:
    """One row per (item, class field) with a decided gold label."""
    by_id = {r["item_id"]: r for r in results}
    rows = []
    for item in items:
        states = by_id.get(item["item_id"], {}).get("states")
        for f in class_fields(item["class"]):
            gold = gold_label(item, f.name)
            if gold is None:
                continue
            pred = states[f.name]["status"] if states else None
            rows.append(
                {
                    "item_id": item["item_id"],
                    "class": item["class"],
                    "kind": variant_kind(item),
                    "field": f.name,
                    "required": f.required,
                    "removed": f.name in item["removed"],
                    "gold": gold,
                    "pred": pred,
                }
            )
    return rows


def missing_prf(rows: list[dict], positive: tuple[str, ...] = ("missing",)) -> dict[str, Any]:
    """P/R/F1 of the "missing" class; a failed item (pred None) counts as wrong."""
    gold = ["missing" if r["gold"] == "missing" else "resolved" for r in rows]
    pred = [None if r["pred"] is None else "missing" if r["pred"] in positive else "resolved" for r in rows]
    m = per_class_prf(gold, pred, BIN)["missing"]
    out = {k: round(v, 3) for k, v in m.items()}
    if len(rows) >= 20:
        lo, hi = bootstrap_ci(gold, pred, lambda g, p: per_class_prf(g, p, BIN)["missing"]["f1"])
        out["f1_ci95"] = [round(lo, 3), round(hi, 3)]
    return out


def share(flags: list[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


def c4_metrics(items: list[dict], results: list[dict]) -> dict[str, Any]:
    rows = field_rows(items, results)
    by_id = {r["item_id"]: r for r in results}
    by_field, by_class = defaultdict(list), defaultdict(list)
    for r in rows:
        by_field[r["field"]].append(r)
        by_class[r["class"]].append(r)
    deleted = [r for r in rows if r["removed"] and r["kind"] == "minus"]
    answered = [r for r in rows if r["removed"] and r["kind"] == "answered"]
    unknown = [r for r in rows if r["removed"] and r["kind"] == "unknown"]
    confirmed_grounded = []
    common = Counter()
    for item in items:
        states = by_id.get(item["item_id"], {}).get("states")
        if not states:
            continue
        text = user_text(item)
        class_names = {f.name for f in class_fields(item["class"])}
        for name, s in states.items():
            if s["status"] == "confirmed":
                confirmed_grounded.append(bool(s["evidence"]) and all(quote_grounded(q, text) for q in s["evidence"]))
            if name not in class_names:
                common[f"{name}:{s['status']}"] += 1
    return {
        "n_items": len(items),
        "n_field_judgements": len(rows),
        "failures": sum("states" not in by_id.get(i["item_id"], {}) for i in items),
        "missing": missing_prf(rows),
        "not_confirmed_view": missing_prf(rows, ("missing", "assumed")),
        "per_field": {f: missing_prf(rs) for f, rs in sorted(by_field.items())},
        "per_class": {c: missing_prf(rs) for c, rs in sorted(by_class.items())},
        "false_confirmed_rate": share([r["pred"] == "confirmed" for r in deleted]),
        "deleted_marked_assumed": share([r["pred"] == "assumed" for r in deleted]),
        "n_deleted_fields": len(deleted),
        "answered_confirmed": share([r["pred"] == "confirmed" for r in answered]),
        "answered_assumed": share([r["pred"] == "assumed" for r in answered]),
        "unknown_detected": share([r["pred"] == "unknown" for r in unknown]),
        "unknown_marked_missing": share([r["pred"] == "missing" for r in unknown]),
        "false_unknown_rate": share([r["pred"] == "unknown" for r in rows if r["gold"] != "unknown"]),
        "confirmed_grounded": share(confirmed_grounded),
        "n_confirmed": len(confirmed_grounded),
        "common_fields": dict(sorted(common.items())),
        "errors": [r for r in rows if (r["gold"] == "missing") != (r["pred"] == "missing") or r["pred"] is None],
    }


def fmt(m: dict[str, Any]) -> str:
    mi = m["missing"]
    return (
        f"missing F1 {mi['f1']:.3f} {mi.get('f1_ci95', '')} (P {mi['precision']:.3f} R {mi['recall']:.3f}); "
        f"not-confirmed F1 {m['not_confirmed_view']['f1']:.3f}; false-confirmed {m['false_confirmed_rate']} "
        f"(assumed {m['deleted_marked_assumed']}); answered→confirmed {m['answered_confirmed']}; "
        f"unknown detected {m['unknown_detected']}; false-unknown {m['false_unknown_rate']}; "
        f"confirmed grounded {m['confirmed_grounded']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--limit", type=int, help="smoke run on the first N items")
    parser.add_argument("--budget", type=float, default=0.5)
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.split == "test":
        check_test_allowed("test", args.confirm_test, args.force, FINAL_CONFIG, RESULTS_DIR, prefix="c4")
        if json.loads(FINAL_CONFIG.read_text())["prompt_version"] != load_prompt("c4_gap").version:
            raise SystemExit("The c4_gap prompt version differs from eval/c4_final_config.json.")
    items = load_items(args.split)
    items = items[: args.limit] if args.limit else items
    budget = Budget(args.budget, llm._settings().log_path, prefix="c4|")
    results, version = run(items, args.split, budget)
    metrics = c4_metrics(items, results)
    calls = call_metrics(paid_calls(read_lines(llm._settings().log_path), budget.run_rows(), f"c4|{args.split}|"))
    model = llm._settings().models["generator"]
    data = {
        "stage": "c4",
        "split": args.split,
        "model": model,
        "prompt_version": version,
        "metrics": metrics,
        "calls": calls,
        "results": results,
    }
    smoke = "_smoke" if args.limit else ""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"c4_{args.split}{smoke}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"  {args.split}: n={len(items)}; {fmt(metrics)}; failures {metrics['failures']}")
    print(f"  calls {calls}; spent ${budget.spent():.4f}\nWrote {path.relative_to(ROOT)}")
    if args.limit:
        print(f"Projected for 360 items: ${budget.spent() / len(items) * 360:.3f}")
        return
    with EVAL_REPORT.open("a", encoding="utf-8") as f:
        row = [
            datetime.now(UTC).date().isoformat(),
            "C4 gap detector",
            f"missing-field F1 · false-confirmed · grounding ({args.split})",
            fmt(metrics),
            f"{len(items)} items / {metrics['n_field_judgements']} fields",
            model,
            version,
            f"{args.split}{', once' if args.split == 'test' else ''}; ablation set; "
            f"${calls['cost_per_100_calls']}/100 calls, p50 {calls['latency_p50_ms']} ms; {path.name}",
        ]
        f.write("| " + " | ".join(str(x) for x in row) + " |\n")


if __name__ == "__main__":
    main()
