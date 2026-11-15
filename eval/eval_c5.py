"""C5 question generator evaluation on the frozen ablation set. Deterministic metrics only (no judge).

python eval/eval_c5.py --split dev --mode oracle    # input = gold field states (C5 alone)
python eval/eval_c5.py --split dev --mode chained   # input = C4's states from the latest eval/results/c4_<split>_*.json
python eval/eval_c5.py --split test --mode oracle --confirm-test   # once each mode, after approval

C5 is called only when the input has at least one missing class field. Metrics on the questions the user would see
(the first MAX_QUESTIONS): <= 2 per turn, targeting rate, redundancy rate, required-before-optional violations,
required coverage, and the re-ask rate for fields the user said they don't know (must be 0).
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.components.question_generator import MAX_QUESTIONS, generate  # noqa: E402
from src.eval.ablation import EXTRACTIONS, load_items, variant_kind  # noqa: E402
from src.eval.lock import check_test_allowed  # noqa: E402
from src.eval.metrics import bootstrap_mean_ci  # noqa: E402
from src.eval.run_log import Budget, call_metrics, paid_calls, read_lines  # noqa: E402
from src.prompting import load_prompt  # noqa: E402
from src.schemas.ticket_fields import class_fields  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
FINAL_CONFIG = ROOT / "eval" / "c5_final_config.json"
EVAL_REPORT = ROOT / "reports" / "05_evaluation.md"
WORKERS, SEED, N_SAMPLE = 6, 42, 20


def oracle_states(item: dict[str, Any], extraction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Gold states of the class fields; present values come from the gold extraction."""
    states = {}
    for f in class_fields(item["class"]):
        ext = extraction.get(f.name, {})
        if f.name in item["gold_missing"]:
            states[f.name] = {"status": "missing", "value": None}
        elif f.name in item["gold_unknown"]:
            states[f.name] = {"status": "unknown", "value": None}
        elif f.name in item["gold_present"]:
            states[f.name] = {"status": "confirmed", "value": ext.get("value")}
        else:  # excluded from the gold: keep the extraction's own status
            states[f.name] = {"status": ext.get("status", "missing"), "value": ext.get("value")}
    return states


def chained_states(split: str) -> dict[str, dict[str, dict[str, Any]]]:
    files = sorted(glob.glob(str(RESULTS_DIR / f"c4_{split}_2*.json")))
    if not files:
        raise SystemExit(f"No eval/results/c4_{split}_*.json: run eval/eval_c4.py --split {split} first.")
    return {r["item_id"]: r["states"] for r in json.loads(Path(files[-1]).read_text())["results"] if "states" in r}


def needs_questions(item: dict[str, Any], states: dict[str, dict[str, Any]]) -> bool:
    return any(states.get(f.name, {}).get("status") == "missing" for f in class_fields(item["class"]))


def item_metrics(item: dict[str, Any], questions: list[dict[str, str]], states: dict) -> dict[str, Any]:
    """Per-item flags for the questions the user sees (the first MAX_QUESTIONS)."""
    defs = {f.name: f for f in class_fields(item["class"])}
    required = {n for n, f in defs.items() if f.required}
    missing_req = set(item["gold_missing"]) & required
    shown = questions[:MAX_QUESTIONS]
    targets = [q["target_field"] for q in shown]
    unknown = item["gold_unknown"][0] if variant_kind(item) == "unknown" else None
    reasked = unknown is not None and any(q["target_field"] == unknown for q in questions)
    return {
        "n_questions": len(questions),
        "le_2": len(questions) <= MAX_QUESTIONS,
        "targeted": [t in missing_req for t in targets],
        "redundant": [t in item["gold_present"] for t in targets],
        "invalid_target": [t not in defs for t in targets],
        "order_violation": bool(missing_req - set(targets)) and any(t in defs and t not in required for t in targets)
        if missing_req
        else None,
        "coverage": len(set(targets) & missing_req) / min(MAX_QUESTIONS, len(missing_req)) if missing_req else None,
        "unknown_field": unknown,
        "reasked_unknown": reasked if unknown else None,
        "reask_cause": ("C4" if states.get(unknown, {}).get("status") != "unknown" else "C5") if reasked else None,
    }


def rate(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    lo, hi = bootstrap_mean_ci(values)
    return {"value": round(sum(values) / len(values), 3), "ci95": [round(lo, 3), round(hi, 3)], "n": len(values)}


def per_question(m: list[dict], key: str) -> list[float]:
    return [float(v) for mm in m for v in mm[key]]


def per_item(m: list[dict], key: str) -> list[float]:
    return [float(mm[key]) for mm in m if mm[key] is not None]


def c5_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    called = [r for r in rows if r.get("called")]
    ok = [r for r in called if "metrics" in r]
    m = [r["metrics"] for r in ok]
    return {
        "n_items": len(rows),
        "n_called": len(called),
        "failures": len(called) - len(ok),
        "n_questions_shown": sum(len(mm["targeted"]) for mm in m),
        "empty_when_required_missing": sum(mm["n_questions"] == 0 and mm["coverage"] is not None for mm in m),
        "le_2_per_turn": rate([float(mm["le_2"]) for mm in m]),
        "targeting_rate": rate(per_question(m, "targeted")),
        "redundancy_rate": rate(per_question(m, "redundant")),
        "invalid_target_rate": rate(per_question(m, "invalid_target")),
        "order_violation_rate": rate(per_item(m, "order_violation")),
        "required_coverage": rate(per_item(m, "coverage")),
        "unknown_reask_rate": rate(per_item(m, "reasked_unknown")),
        "unknown_reask_causes": [
            {"item_id": r["item_id"], "cause": r["metrics"]["reask_cause"]} for r in ok if r["metrics"]["reask_cause"]
        ],
    }


def fmt(m: dict[str, Any]) -> str:
    def v(key: str) -> str:
        return f"{m[key]['value']} {m[key]['ci95']}" if m[key] else "—"

    return (
        f"≤2/turn {v('le_2_per_turn')}; targeting {v('targeting_rate')}; redundancy {v('redundancy_rate')}; "
        f"order violations {v('order_violation_rate')}; required coverage {v('required_coverage')}; "
        f"unknown re-ask {v('unknown_reask_rate')}"
    )


def sample_markdown(items: dict[str, dict], rows: list[dict], mode: str, split: str) -> str:
    """N_SAMPLE items with questions, spread over classes, for the user's clarity check."""
    rng = random.Random(SEED)
    with_q = [r for r in rows if r.get("questions")]
    picked = []
    for cls in ("bug", "feature", "task", "idea"):
        pool = [r for r in with_q if items[r["item_id"]]["class"] == cls]
        picked += rng.sample(pool, min(N_SAMPLE // 4, len(pool)))
    lines = [f"# C5 question sample ({mode}, {split}; {len(picked)} items, seed {SEED})\n"]
    for r in picked:
        item = items[r["item_id"]]
        first = " ".join(item["conversation"][0]["content"].split())[:500]
        lines.append(f"## {item['item_id']} · {item['class']}\n\n> {first}…\n")
        for t in item["conversation"][1:]:
            lines.append(f"> **{t['role']}:** {' '.join(t['content'].split())[:200]}\n")
        lines.append(f"Gold missing: {item['gold_missing']} · unknown: {item['gold_unknown']}\n")
        for q in r["questions"][:MAX_QUESTIONS]:
            lines.append(f"- [{q['target_field']}] {q['question']}")
        lines.append("\nClarity (1 = unclear … 3 = clear): ___\n")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--mode", choices=["oracle", "chained"], required=True)
    parser.add_argument("--limit", type=int, help="smoke run on the first N items")
    parser.add_argument("--budget", type=float, default=0.4)
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.split == "test":
        check_test_allowed("test", args.confirm_test, args.force, FINAL_CONFIG, RESULTS_DIR, prefix=f"c5_{args.mode}")
        if json.loads(FINAL_CONFIG.read_text())["prompt_version"] != load_prompt("c5_questions").version:
            raise SystemExit("The c5_questions prompt version differs from eval/c5_final_config.json.")
    items = load_items(args.split)
    items = items[: args.limit] if args.limit else items
    with EXTRACTIONS.open(encoding="utf-8") as f:
        extractions = {r["key"]: r.get("extraction", {}) for r in map(json.loads, f)}
    c4 = chained_states(args.split) if args.mode == "chained" else {}
    prompt = load_prompt("c5_questions")
    budget = Budget(args.budget, llm._settings().log_path, prefix="c5|")

    def one(item: dict[str, Any]) -> dict[str, Any]:
        states = c4.get(item["item_id"]) if args.mode == "chained" else oracle_states(item, extractions[item["key"]])
        row = {"item_id": item["item_id"], "states": states}
        if states is None:
            return {**row, "called": False, "skipped": "C4 failed on this item"}
        if not needs_questions(item, states):
            return {**row, "called": False}
        if budget.exceeded():
            return {**row, "called": True, "error": "skipped: budget exceeded"}
        try:
            out = generate(
                item["conversation"],
                item["class"],
                states,
                prompt=prompt,
                session_id=f"c5|{args.mode}|{args.split}|{prompt.version}|{item['item_id']}",
            )
        except Exception as exc:
            return {**row, "called": True, "error": f"{type(exc).__name__}: {exc}"[:300]}
        questions = [q.model_dump() for q in out.questions]
        return {**row, "called": True, "questions": questions, "metrics": item_metrics(item, questions, states)}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = list(pool.map(one, items))
    metrics = c5_metrics(rows)
    calls = call_metrics(
        paid_calls(read_lines(llm._settings().log_path), budget.run_rows(), f"c5|{args.mode}|{args.split}|")
    )
    model = llm._settings().models["generator"]
    stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    smoke = "_smoke" if args.limit else ""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"c5_{args.mode}_{args.split}{smoke}_{stamp}.json"
    data = {"stage": "c5", "mode": args.mode, "split": args.split, "model": model, "prompt_version": prompt.version}
    path.write_text(json.dumps({**data, "metrics": metrics, "calls": calls, "results": rows}, indent=1))
    print(f"  {args.mode} {args.split}: called {metrics['n_called']}/{len(items)}; {fmt(metrics)}")
    print(f"  calls {calls}; spent ${budget.spent():.4f}\nWrote {path.relative_to(ROOT)}")
    if args.limit:
        print(f"Projected for 360 items: ${budget.spent() / max(1, metrics['n_called']) * 360:.3f}")
        return
    if args.split == "dev":
        sample = RESULTS_DIR / f"c5_questions_sample_{args.mode}_{stamp}.md"
        sample.write_text(sample_markdown({i["item_id"]: i for i in items}, rows, args.mode, args.split))
        print(f"Wrote {sample.relative_to(ROOT)}")
    with EVAL_REPORT.open("a", encoding="utf-8") as f:
        row = [
            datetime.now(UTC).date().isoformat(),
            f"C5 question generator ({args.mode})",
            f"targeting · redundancy · order · unknown re-ask ({args.split})",
            fmt(metrics),
            f"{metrics['n_called']} turns / {metrics['n_questions_shown']} questions",
            model,
            prompt.version,
            f"{args.split}{', once' if args.split == 'test' else ''}; ablation set; "
            f"${calls['cost_per_100_calls']}/100 calls, p50 {calls['latency_p50_ms']} ms; {path.name}",
        ]
        f.write("| " + " | ".join(str(x) for x in row) + " |\n")


if __name__ == "__main__":
    main()
