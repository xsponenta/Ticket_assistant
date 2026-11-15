"""Human audit of C4 on deleted fields: is the deleted field's information still in the conversation? (no LLM)

On dev, C4 marked 137 of 173 deleted fields confirmed or assumed. Part of that is gold leakage: the information
survives in the title, in another field's passage, or in text the extraction never quoted. 20 cases, stratified by
where C4's evidence comes from, are labelled BLIND (C4's status and evidence are hidden). The label corrects the
false-confirmed rate; 0.468 stays the upper bound.

python -m src.eval.c4_audit_cli            # label (resumable) -> data/eval/c4_audit_labels.jsonl
python -m src.eval.c4_audit_cli --report   # corrected false-confirmed rate with a stratified bootstrap CI
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import shutil
import textwrap
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.eval.ablation import ABLATION, EXTRACTIONS, variant_kind
from src.eval.spans import find_spans, merge_spans
from src.schemas.ticket_fields import class_fields

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "data" / "eval" / "c4_audit_cases.jsonl"
META = ROOT / "data" / "eval" / "c4_audit_meta.json"
LABELS = ROOT / "data" / "eval" / "c4_audit_labels.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
N_CASES, SEED, N_BOOT = 20, 42, 1000
SOURCES = ("other field's passage", "unquoted text", "title", "evidence not found")

RUBRIC = """\
QUESTION: Is the information of the field named above still in the CONVERSATION (above the line)?
  y = STATED       the user still states it, explicitly or in other words, fully or partly
                   (partial counts: e.g. the Spark version without the deployment).
  i = INFERABLE    not stated, but a reader could infer it from an indirect cue
                   (e.g. the language from code syntax, the expected result from the error alone).
  n = NOT THERE    neither stated nor inferable.
Edge cases:
  - The title is part of the conversation.
  - The DELETED text (below the line) does not count; it only shows what was removed.
  - Information that belongs to another field counts only if it also states THIS field (otherwise: i or n).
  - An absence statement ("no workaround known") states the field."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evidence_source(text: str, evidence: list[str], other_quotes: list[str]) -> str:
    """Where C4's evidence for a deleted field sits in the variant text (first match wins: title, other field's
    passage, any other text)."""
    spans = [s for q in evidence for s in find_spans(q, text)]
    if any(start < text.index("\n\nDescription:") for start, _ in spans):
        return "title"
    if any(find_spans(e, q) or find_spans(q, e) for e in evidence for q in other_quotes):
        return "other field's passage"
    return "unquoted text" if spans else "evidence not found"


def allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Proportional allocation of n with largest remainders (ties: larger stratum first)."""
    total = sum(sizes.values())
    exact = {s: sizes[s] * n / total for s in sizes}
    quota = {s: int(x) for s, x in exact.items()}
    for s in sorted(sizes, key=lambda s: (-(exact[s] - quota[s]), -sizes[s]))[: n - sum(quota.values())]:
        quota[s] += 1
    return quota


def population(c4_file: Path) -> list[dict[str, Any]]:
    """All deleted fields (minus variants) with C4's status; confirmed/assumed ones carry their evidence source."""
    items = {i["item_id"]: i for i in read_jsonl(ABLATION) if i["split"] == "dev"}
    extractions = {r["key"]: r["extraction"] for r in read_jsonl(EXTRACTIONS)}
    rows = []
    for r in json.loads(c4_file.read_text())["results"]:
        item = items[r["item_id"]]
        if variant_kind(item) != "minus" or "states" not in r:
            continue
        text = item["conversation"][0]["content"]
        for field in item["removed"]:
            state = r["states"][field]
            others = [
                q
                for name, e in extractions[item["key"]].items()
                if name not in item["removed"] and e["status"] != "missing"
                for q in e["quotes"]
            ]
            source = evidence_source(text, state["evidence"], others) if state["status"] != "missing" else None
            rows.append({"item_id": item["item_id"], "field": field, "c4_status": state["status"], "source": source})
    return rows


def build_cases() -> list[dict[str, Any]]:
    files = sorted(glob.glob(str(RESULTS_DIR / "c4_dev_2*.json")))
    if not files:
        raise SystemExit("No eval/results/c4_dev_*.json: run eval/eval_c4.py --split dev first.")
    rows = population(Path(files[-1]))
    resolved = [r for r in rows if r["c4_status"] in ("confirmed", "assumed")]
    sizes = Counter(r["source"] for r in resolved)
    quota = allocate(dict(sizes), N_CASES)
    rng = random.Random(SEED)
    items = {i["item_id"]: i for i in read_jsonl(ABLATION)}
    extractions = {r["key"]: r for r in read_jsonl(EXTRACTIONS)}
    cases = []
    for source in SOURCES:
        pool = sorted((r for r in resolved if r["source"] == source), key=lambda r: (r["item_id"], r["field"]))
        for r in rng.sample(pool, quota.get(source, 0)):
            rec = extractions[items[r["item_id"]]["key"]]
            spans = merge_spans([tuple(s) for s in rec["extraction"][r["field"]]["spans"]])
            definition = next(f for f in class_fields(rec["class"]) if f.name == r["field"])
            cases.append(
                {
                    **r,
                    "case_id": f"{r['item_id']}|{r['field']}",
                    "class": rec["class"],
                    "definition": definition.description,
                    "conversation": items[r["item_id"]]["conversation"][0]["content"],
                    "deleted_text": [rec["text"][s:e] for s, e in spans],
                }
            )
    rng.shuffle(cases)
    meta = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "c4_results": Path(files[-1]).name,
        "n_deleted": len(rows),
        "c4_missing": sum(r["c4_status"] == "missing" for r in rows),
        "population": {s: dict(Counter(r["c4_status"] for r in resolved if r["source"] == s)) for s in sizes},
        "quota": quota,
    }
    CASES.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
    META.write_text(json.dumps(meta, indent=1))
    return cases


def show(case: dict[str, Any], done: int, total: int) -> None:
    width = min(110, shutil.get_terminal_size((110, 30)).columns)
    print("\n" + "═" * width)
    print(f" C4 audit   [{done}/{total} labelled]   {case['item_id']}   class: {case['class']}")
    print(f" FIELD: {case['field']}: {case['definition']}")
    print("─" * width + "\nCONVERSATION (what C4 saw):\n")
    print(case["conversation"])
    print("─" * width + "\nDELETED TEXT (does not count):")
    for t in case["deleted_text"]:
        print(textwrap.indent(t.strip()[:1200], "  ▸ "))
    print("─" * width + "\n" + RUBRIC)


def label_loop(cases: list[dict[str, Any]]) -> None:
    done = {r["case_id"] for r in read_jsonl(LABELS)}
    for case in cases:
        if case["case_id"] in done:
            continue
        show(case, len(done), len(cases))
        answer = ""
        while answer not in ("y", "i", "n", "s", "q"):
            answer = input("y = stated, i = inferable, n = not there, s = skip, q = quit: ").strip().lower()
        if answer == "q":
            return
        if answer == "s":
            continue
        record = {"case_id": case["case_id"], "label": answer, "labeled_at": datetime.now(UTC).isoformat()}
        with LABELS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        done.add(case["case_id"])


def corrected(meta: dict[str, Any], labels_by_source: dict[str, list[str]]) -> dict[str, float]:
    """Stratified estimates from the audit labels (a stratum without labels uses the pooled shares).

    A deleted field is still present only if its information is STATED (y); C4-missing deleted fields are taken as
    not stated (they were not audited).
    - false_confirmed_rate: C4 "confirmed" while not stated / deleted fields not stated;
    - resolved_but_gone_rate: C4 confirmed or assumed while not even inferable (n) / the same denominator;
    - leaked_share_of_resolved: share of C4's confirmed/assumed deleted fields whose information is still stated.
    """
    pooled = [lab for labs in labels_by_source.values() for lab in labs]

    def share(source: str, value: str) -> float:
        labs = labels_by_source.get(source) or pooled
        return sum(lab == value for lab in labs) / len(labs)

    resolved = stated = false_confirmed = gone = 0.0
    for source, counts in meta["population"].items():
        n = sum(counts.values())
        resolved += n
        stated += n * share(source, "y")
        false_confirmed += counts.get("confirmed", 0) * (1 - share(source, "y"))
        gone += n * share(source, "n")
    not_stated = meta["c4_missing"] + resolved - stated
    return {
        "false_confirmed_rate": false_confirmed / not_stated,
        "resolved_but_gone_rate": gone / not_stated,
        "leaked_share_of_resolved": stated / resolved,
    }


def report() -> dict[str, Any]:
    meta = json.loads(META.read_text())
    labels = {r["case_id"]: r["label"] for r in read_jsonl(LABELS)}
    cases = [c for c in read_jsonl(CASES) if c["case_id"] in labels]
    by_source: dict[str, list[str]] = {}
    for c in cases:
        by_source.setdefault(c["source"], []).append(labels[c["case_id"]])
    point = corrected(meta, by_source)
    rng = random.Random(SEED)
    boot = [
        corrected(meta, {s: [rng.choice(labs) for _ in labs] for s, labs in by_source.items()}) for _ in range(N_BOOT)
    ]
    ci = {}
    for k in point:
        values = sorted(b[k] for b in boot)
        ci[k] = [round(values[int(0.025 * N_BOOT)], 3), round(values[int(0.975 * N_BOOT) - 1], 3)]
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_labelled": len(cases),
        "labels_by_source": {s: dict(Counter(labs)) for s, labs in by_source.items()},
        "labels_by_c4_status": {
            st: dict(Counter(labels[c["case_id"]] for c in cases if c["c4_status"] == st))
            for st in ("confirmed", "assumed")
        },
        "upper_bound_false_confirmed": round(
            sum(c.get("confirmed", 0) for c in meta["population"].values()) / meta["n_deleted"], 3
        ),
        "corrected": {k: round(v, 3) for k, v in point.items()},
        "ci95": ci,
        "meta": meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        result = report()
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"c4_audit_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
        path.write_text(json.dumps(result, indent=1))
        print(json.dumps({k: v for k, v in result.items() if k != "meta"}, indent=1))
        print(f"Saved {path.relative_to(ROOT)}")
        return
    cases = read_jsonl(CASES) or build_cases()
    try:
        label_loop(cases)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
    print(f"\n{len(read_jsonl(LABELS))} of {len(cases)} labelled → {LABELS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
