"""C6 ticket composer evaluation on the frozen ablation set, with C4's states from the approved runs. Deterministic.

python eval/eval_c6.py --split dev [--limit 20]
python eval/eval_c6.py --split test --confirm-test        # once, after approval (eval/c6_final_config.json)

Inputs per item: the conversation, the gold class, the ticket's Jira component (mapped to the top 15) and C4's field
states (c4_dev_20261115T165319Z.json / c4_test_20261115T170923Z.json, the runs behind the approved C4 config).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.components.classifier import map_components  # noqa: E402
from src.components.ticket_composer import compose  # noqa: E402
from src.eval.ablation import load_items, user_text  # noqa: E402
from src.eval.lock import check_test_allowed  # noqa: E402
from src.eval.metrics import bootstrap_mean_ci  # noqa: E402
from src.eval.run_log import Budget, call_metrics, paid_calls, read_lines  # noqa: E402
from src.eval.spans import GENERIC_TERMS, content_word_share, invented_tokens, quote_grounded, risky_tokens  # noqa: E402
from src.prompting import load_prompt  # noqa: E402
from src.schemas.c1 import TOP_COMPONENTS  # noqa: E402
from src.schemas.c6 import UNKNOWN_TEXT  # noqa: E402
from src.schemas.ticket_fields import class_fields, heading  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
FINAL_CONFIG = ROOT / "eval" / "c6_final_config.json"
EVAL_REPORT = ROOT / "reports" / "05_evaluation.md"
C4_RUNS = {"dev": "c4_dev_20261115T165319Z.json", "test": "c4_test_20261115T170923Z.json"}
WORKERS, MIN_SHARE = 6, 0.6
GWT = re.compile(r"\bgiven\b.*?\bwhen\b.*?\bthen\b", re.I | re.S)
FORBIDDEN_LINE = re.compile(r"(?im)^\W*(priority|fix versions?|target versions?|assignee)\W*:")
LABEL_CUES = {
    "correctness": re.compile(r"wrong|incorrect|correctness|inconsistent result", re.I),
    "data-loss": re.compile(r"data[ -]loss|lost data|data is lost|losing data", re.I),
}
CRITERIA_FIELDS = {"feature": "acceptance_criteria", "task": "definition_of_done"}


def jira_components(keys: set[str]) -> dict[str, list[str]]:
    """The ticket's Jira components mapped to the top 15 (first one in Jira order), as the user would confirm."""
    df = pd.read_parquet(ROOT / "data" / "processed" / "issues.parquet", columns=["key", "components"])
    out = {}
    for key, comps in zip(df.key, df.components, strict=True):
        if key in keys:
            mapped = [c for c in comps if c in TOP_COMPONENTS]
            out[key] = mapped[:1] or sorted(map_components(list(comps)))[:1]
    return out


def item_metrics(item: dict, states: dict, ticket: dict) -> dict[str, Any]:
    cls, user = item["class"], user_text(item)
    fields = ticket["fields"]
    required = [f.name for f in class_fields(cls) if f.required]
    resolved = [n for n in required if states[n]["status"] in ("confirmed", "assumed", "unknown")]
    covered = [n for n in required if fields[n]["status"] in ("confirmed", "assumed", "unknown") and fields[n]["value"]]
    written = [n for n, f in fields.items() if f["status"] in ("confirmed", "assumed")]
    grounded = {
        n: {
            "status": fields[n]["status"],
            "ok": content_word_share(fields[n]["value"], user) >= MIN_SHARE
            or any(quote_grounded(q, fields[n]["value"]) for q in states[n]["evidence"]),
        }
        for n in written
    }
    body = ticket["body_markdown"]
    assumptions = body.split("### Assumptions to confirm", 1)[1] if "### Assumptions to confirm" in body else ""
    assumed = [n for n, s in states.items() if s["status"] == "assumed" and n in fields]
    unknown = [n for n, s in states.items() if s["status"] == "unknown" and n in fields]
    # Checked for inventions: the title and the confirmed fields. Assumed fields carry C4's inference on purpose and
    # are listed under "Assumptions to confirm" (M4); the template, component and type come from code.
    text = "\n".join([ticket["title"], *(f["value"] for f in fields.values() if f["status"] == "confirmed")])
    ignore = GENERIC_TERMS | set(ticket["component"])
    invented = invented_tokens(text, user, ignore)
    criteria = CRITERIA_FIELDS.get(cls)
    first_line = user.split("\n", 1)[0].removeprefix("Summary:").strip().lower()
    return {
        "required": len(required),
        "covered": len(covered),
        "resolved_required": len(resolved),
        "covered_of_resolved": sum(n in covered for n in resolved),
        "missing_filled": sum(states[n]["status"] == "missing" and fields[n]["status"] != "missing" for n in fields),
        "grounded": grounded,
        "invented": invented,
        "n_risky": len(risky_tokens(text) - ignore),
        "assumptions_listed": all(f"**{heading(n)}:**" in assumptions for n in assumed) if assumed else None,
        "unknown_rendered": all(fields[n]["value"] == UNKNOWN_TEXT for n in unknown) if unknown else None,
        "labels_without_cue": [lab for lab in ticket["labels"] if not LABEL_CUES[lab].search(user)],
        "gwt": bool(GWT.search(fields[criteria]["value"] or "")) if criteria in written else None,
        "forbidden_line": bool(FORBIDDEN_LINE.search(body)),
        "title_ok": 4 <= len(ticket["title"].split()) <= 20 and ticket["title"].strip().lower() != first_line,
    }


def mean_ci(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    lo, hi = bootstrap_mean_ci(values)
    return {"value": round(sum(values) / len(values), 3), "ci95": [round(lo, 3), round(hi, 3)], "n": len(values)}


def flags(ok: list[dict], key: str) -> list[float]:
    return [float(m[key]) for m in ok if m[key] is not None]


def c6_metrics(rows: list[dict]) -> dict[str, Any]:
    ok = [r["metrics"] for r in rows if "metrics" in r]
    grounded = {
        status: [float(g["ok"]) for m in ok for g in m["grounded"].values() if g["status"] == status]
        for status in ("confirmed", "assumed")
    }
    risky = sum(m["n_risky"] for m in ok)
    invented = sum(len(m["invented"]) for m in ok)
    return {
        "n_items": len(rows),
        "schema_valid": round(len(ok) / len(rows), 3) if rows else None,
        "required_coverage": round(sum(m["covered"] for m in ok) / max(1, sum(m["required"] for m in ok)), 3),
        "coverage_of_resolved": round(
            sum(m["covered_of_resolved"] for m in ok) / max(1, sum(m["resolved_required"] for m in ok)), 3
        ),
        "missing_filled": sum(m["missing_filled"] for m in ok),
        "grounded_confirmed": mean_ci(grounded["confirmed"]),
        "grounded_assumed": mean_ci(grounded["assumed"]),
        "invented_token_rate": round(invented / risky, 3) if risky else None,
        "n_risky_tokens": risky,
        "tickets_with_invented_token": mean_ci([float(bool(m["invented"])) for m in ok]),
        "assumptions_complete": mean_ci(flags(ok, "assumptions_listed")),
        "unknown_rendered": mean_ci(flags(ok, "unknown_rendered")),
        "labels_without_cue": sum(len(m["labels_without_cue"]) for m in ok),
        "given_when_then": mean_ci(flags(ok, "gwt")),
        "forbidden_lines": sum(m["forbidden_line"] for m in ok),
        "title_ok": mean_ci(flags(ok, "title_ok")),
    }


def fmt(m: dict[str, Any]) -> str:
    def v(key: str) -> Any:
        return m[key]["value"] if isinstance(m[key], dict) else m[key]

    return (
        f"schema-valid {m['schema_valid']}; required coverage {m['required_coverage']} (of resolved "
        f"{m['coverage_of_resolved']}); grounded confirmed {v('grounded_confirmed')} / assumed "
        f"{v('grounded_assumed')}; invented-token rate "
        f"{m['invented_token_rate']} (tickets with ≥1: {v('tickets_with_invented_token')}); assumptions complete "
        f"{v('assumptions_complete')}; unknown rendered {v('unknown_rendered')}; labels w/o cue "
        f"{m['labels_without_cue']}; GWT {v('given_when_then')}; forbidden lines {m['forbidden_lines']}; "
        f"title ok {v('title_ok')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--limit", type=int, help="smoke run on the first N items")
    parser.add_argument("--budget", type=float, default=0.4)
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    prompt = load_prompt("c6_compose")
    if args.split == "test":
        check_test_allowed("test", args.confirm_test, args.force, FINAL_CONFIG, RESULTS_DIR, prefix="c6")
        if json.loads(FINAL_CONFIG.read_text())["prompt_version"] != prompt.version:
            raise SystemExit("The c6_compose prompt version differs from eval/c6_final_config.json.")
    items = load_items(args.split)
    items = items[: args.limit] if args.limit else items
    states = {
        r["item_id"]: r["states"]
        for r in json.loads((RESULTS_DIR / C4_RUNS[args.split]).read_text())["results"]
        if "states" in r
    }
    components = jira_components({i["key"] for i in items})
    budget = Budget(args.budget, llm._settings().log_path, prefix="c6|")

    def one(item: dict) -> dict[str, Any]:
        row = {"item_id": item["item_id"]}
        st = states.get(item["item_id"])
        if st is None:
            return {**row, "error": "no C4 states for this item"}
        if budget.exceeded():
            return {**row, "error": "skipped: budget exceeded"}
        try:
            ticket = compose(
                item["conversation"],
                item["class"],
                components[item["key"]],
                st,
                prompt=prompt,
                session_id=f"c6|{args.split}|{prompt.version}|{item['item_id']}",
            ).model_dump()
        except Exception as exc:
            return {**row, "error": f"{type(exc).__name__}: {exc}"[:300]}
        return {**row, "ticket": ticket, "metrics": item_metrics(item, st, ticket)}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = list(pool.map(one, items))
    metrics = c6_metrics(rows)
    calls = call_metrics(paid_calls(read_lines(llm._settings().log_path), budget.run_rows(), f"c6|{args.split}|"))
    model = llm._settings().models["generator"]
    smoke = "_smoke" if args.limit else ""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"c6_{args.split}{smoke}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    data = {
        "stage": "c6",
        "split": args.split,
        "model": model,
        "prompt_version": prompt.version,
        "c4_run": C4_RUNS[args.split],
    }
    path.write_text(json.dumps({**data, "metrics": metrics, "calls": calls, "results": rows}, indent=1))
    print(f"  {args.split}: n={len(items)}; {fmt(metrics)}")
    print(f"  calls {calls}; spent ${budget.spent():.4f}\nWrote {path.relative_to(ROOT)}")
    if args.limit:
        print(f"Projected for 303 items: ${budget.spent() / len(items) * 303:.3f}")
        return
    with EVAL_REPORT.open("a", encoding="utf-8") as f:
        row = [
            datetime.now(UTC).date().isoformat(),
            "C6 ticket composer",
            f"schema · coverage · grounding · invented tokens · rules ({args.split})",
            fmt(metrics),
            str(len(items)),
            model,
            prompt.version,
            f"{args.split}{', once' if args.split == 'test' else ''}; ablation set + C4 states {C4_RUNS[args.split]}; "
            f"${calls['cost_per_100_calls']}/100 calls, p50 {calls['latency_p50_ms']} ms; {path.name}",
        ]
        f.write("| " + " | ".join(str(x) for x in row) + " |\n")


if __name__ == "__main__":
    main()
