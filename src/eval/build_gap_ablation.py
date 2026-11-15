"""Build the C4/C5 ablation set: rich tickets with the exact text of 1-2 required fields deleted.

python -m src.eval.build_gap_ablation --extract [--limit 5]   # one generator call per ticket -> gap_extractions.jsonl
python -m src.eval.build_gap_ablation --show 10               # spot check: fields, quotes (✓/✗), one variant diff
python -m src.eval.build_gap_ablation --build                 # deterministic variants -> gap_ablation.jsonl (frozen)

Tickets: dev = rich VAL tickets (same rule as build_eval.build_simulator, seed 42, <= 15 per class); test = the 60
simulator_candidates (test split). Variants per ticket: original, minus_<f> (each deletable required field), one
seeded pair minus_<f>_<g>, answered_<f> (asked, user gives the deleted text back), unknown_<f> (asked, user says
they don't know). Gold covers the class fields; fields the extraction marked assumed or could not ground are excluded.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src import llm
from src.eval.ablation import ABLATION, EXTRACTIONS, META, items_sha256
from src.eval.run_log import Budget
from src.eval.spans import delete_spans, find_spans, merge_spans, overlaps
from src.prompting import load_prompt
from src.schemas.c4 import extraction_model
from src.schemas.ticket_fields import CLASSES, class_fields, render_fields

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "data"))  # src/data scripts use sibling imports (not a package)
from build_eval import SIMULATOR_CAP, SIMULATOR_MIN_WORDS, bug_signals, n_words, sample_keys  # noqa: E402

EVAL = ROOT / "data" / "eval"
RESULTS_DIR = ROOT / "eval" / "results"
DESC_CHARS, MIN_DESC_WORDS, SEED, WORKERS = 4000, 20, 42, 6
MAX_TOKENS = 4000  # caps a runaway generation (one smoke call produced 131k tokens, $0.07)
UNKNOWN_REPLIES = ("I don't know.", "Sorry, I can't provide that.", "No idea, I don't have that information.")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def ticket_text(summary: str, description: str) -> str:
    return f"Summary: {summary.strip()}\n\nDescription:\n{(description or '')[:DESC_CHARS].strip()}"


def description_words(text: str) -> int:
    return len(text.split("Description:", 1)[-1].split())


# ---------------------------------------------------------------- tickets


def dev_tickets() -> list[dict[str, Any]]:
    """Rich val tickets, selected exactly like the test simulator candidates (build_eval.build_simulator)."""
    df = pd.read_parquet(ROOT / "data" / "processed" / "issues.parquet")
    val_keys = set(json.loads((ROOT / "data" / "processed" / "splits.json").read_text())["val"])
    val = df[df.key.isin(val_keys) & df.has_description].copy()
    val["n_words"] = val.description_md.map(n_words)
    rng, rows = random.Random(SEED), []
    for cls in CLASSES:
        part = val[val.target_class == cls]
        if cls == "bug":
            rich = part[[sum(bug_signals(t).values()) >= 3 for t in part.description_md]]
        else:
            rich = part[part.n_words >= SIMULATOR_MIN_WORDS]
        for key in sample_keys(list(rich.key), SIMULATOR_CAP, rng):
            r = rich[rich.key == key].iloc[0]
            rows.append({"key": key, "summary": r.summary, "description": r.description_md, "class": cls})
    return [dict(t, split="dev") for t in rows]


def test_tickets() -> list[dict[str, Any]]:
    return [
        {"key": c["key"], "summary": c["summary"], "description": c["description_md"], "class": c["target_class"]}
        | {"split": "test"}
        for c in read_jsonl(EVAL / "simulator_candidates.jsonl")
    ]


# ---------------------------------------------------------------- extraction


def ground(extraction: dict[str, Any], text: str) -> dict[str, Any]:
    """Add spans per quote and `grounded` (every quote found; a confirmed field needs at least one quote)."""
    out = {}
    for name, field in extraction.items():
        spans = [find_spans(q, text) for q in field["quotes"]]
        grounded = all(spans) and (field["status"] != "confirmed" or bool(spans))
        out[name] = {**field, "spans": [s for group in spans for s in group], "grounded": grounded}
    return out


def extract(ticket: dict[str, Any], budget: Budget) -> dict[str, Any]:
    prompt = load_prompt("ablation_extract")
    text = ticket_text(ticket["summary"], ticket["description"])
    base = {**ticket, "description": (ticket["description"] or "")[:DESC_CHARS], "text": text}
    if budget.exceeded():
        return {**base, "error": "budget"}
    fields = render_fields(class_fields(ticket["class"]))
    messages = [
        {"role": "system", "content": prompt.render("system", cls=ticket["class"], fields=fields)},
        {"role": "user", "content": prompt.render("user", cls=ticket["class"], ticket=text)},
    ]
    try:
        out = llm.complete(
            messages,
            role="generator",
            component="ablation_extract",
            session_id=f"abl|{ticket['key']}",
            schema=extraction_model(ticket["class"]),
            max_tokens=MAX_TOKENS,
        )
    except Exception as exc:
        return {**base, "error": f"{type(exc).__name__}: {exc}"[:300]}
    return {**base, "prompt_version": prompt.version, "extraction": ground(out.model_dump(), text)}


# ---------------------------------------------------------------- variants


def field_groups(rec: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """(present, missing, excluded) class fields of an extraction, in YAML order."""
    ext = rec["extraction"]
    names = [f.name for f in class_fields(rec["class"])]
    present = [n for n in names if ext[n]["status"] == "confirmed" and ext[n]["grounded"]]
    missing = [n for n in names if ext[n]["status"] == "missing"]
    return present, missing, [n for n in names if n not in present and n not in missing]


def title_end(text: str) -> int:
    return text.index("\n\nDescription:")


def deletable(rec: dict[str, Any], present: list[str]) -> list[str]:
    """Required present fields not quoted in the title (a real conversation always starts with a title) whose
    deletion leaves >= MIN_DESC_WORDS description words. Overlaps with other fields are allowed; see overlapped()."""
    required = {f.name for f in class_fields(rec["class"]) if f.required}
    end = title_end(rec["text"])
    spans = {n: merge_spans([tuple(s) for s in rec["extraction"][n]["spans"]]) for n in present}
    return [
        n
        for n in present
        if n in required
        and all(start >= end for start, _ in spans[n])
        and description_words(delete_spans(rec["text"], spans[n])) >= MIN_DESC_WORDS
    ]


def overlapped(removed: list[str], present: list[str], spans: dict[str, list]) -> list[str]:
    """Present fields that lose part of their text when `removed` are deleted: left out of scoring for that variant,
    so no half-deleted field is ever scored."""
    deleted = [s for n in removed for s in spans[n]]
    return [n for n in present if n not in removed and overlaps(spans[n], deleted)]


def ask(field_name: str, cls: str) -> str:
    f = next(f for f in class_fields(cls) if f.name == field_name)
    return f"Could you add the {field_name.replace('_', ' ')}? {f.description}"


def build_items(rec: dict[str, Any]) -> list[dict[str, Any]]:
    rng = random.Random(f"{SEED}|{rec['key']}")
    present, missing, excluded = field_groups(rec)
    spans = {n: merge_spans([tuple(s) for s in rec["extraction"][n]["spans"]]) for n in present}
    text, cls = rec["text"], rec["class"]

    def item(variant, conversation, removed=(), gold_missing=(), gold_unknown=(), re_added=()):
        cut = overlapped(list(removed), present, spans)
        gold_missing = sorted(set(missing) | set(gold_missing))
        gold_present = [
            n for n in present if (n not in removed or n in re_added) and n not in gold_unknown and n not in cut
        ]
        return {
            "item_id": f"{rec['key']}|{variant}",
            "key": rec["key"],
            "split": rec["split"],
            "class": cls,
            "variant": variant,
            "conversation": conversation,
            "removed": list(removed),
            "gold_missing": gold_missing,
            "gold_present": gold_present,
            "gold_unknown": list(gold_unknown),
            "excluded_fields": excluded + cut,
        }

    def user(t):
        return [{"role": "user", "content": t}]

    items = [item("original", user(text))]
    singles = deletable(rec, present)
    for f in singles:
        items.append(item(f"minus_{f}", user(delete_spans(text, spans[f])), removed=[f], gold_missing=[f]))
    if len(singles) >= 2:
        pair = sorted(rng.sample(singles, 2), key=singles.index)
        pair_text = delete_spans(text, spans[pair[0]] + spans[pair[1]])
        if description_words(pair_text) >= MIN_DESC_WORDS:
            items.append(item(f"minus_{pair[0]}_{pair[1]}", user(pair_text), removed=pair, gold_missing=pair))
    if singles:
        f_answer = rng.choice(singles)
        f_unknown = rng.choice([f for f in singles if f != f_answer] or singles)
        for kind, f in (("answered", f_answer), ("unknown", f_unknown)):
            reply = "\n\n".join(text[s:e] for s, e in spans[f]) if kind == "answered" else rng.choice(UNKNOWN_REPLIES)
            conversation = [
                *user(delete_spans(text, spans[f])),
                {"role": "assistant", "content": ask(f, cls)},
                {"role": "user", "content": reply},
            ]
            if kind == "answered":
                items.append(item(f"answered_{f}", conversation, removed=[f], re_added=[f]))
            else:
                items.append(item(f"unknown_{f}", conversation, removed=[f], gold_unknown=[f]))
    return items


# ---------------------------------------------------------------- CLI


def show(n: int) -> Path:
    recs = [r for r in read_jsonl(EXTRACTIONS) if "extraction" in r]
    rng = random.Random(SEED)
    picked = [r for cls in CLASSES for r in rng.sample([x for x in recs if x["class"] == cls], 2)]
    rest = [r for r in recs if r not in picked]
    picked += rng.sample(rest, max(0, n - len(picked)))
    lines = [f"# Ablation spot check ({len(picked)} extractions, seed {SEED})\n"]
    for r in picked[:n]:
        lines.append(f"## {r['key']} · {r['class']} · {r['split']}\n\n**Summary:** {r['summary']}\n")
        for name, f in r["extraction"].items():
            lines.append(f"- **{name}**: `{f['status']}`{'' if f['grounded'] else ' ⚠ ungrounded'} — {f['value']}")
            for q in f["quotes"]:
                mark = "✓" if find_spans(q, r["text"]) else "✗"
                lines.append(f"  - {mark} “{' '.join(q.split())[:220]}”")
        variants = [i for i in build_items(r) if i["variant"].startswith("minus_") and len(i["removed"]) == 1]
        if variants:
            v = variants[0]
            spans = merge_spans([tuple(s) for s in r["extraction"][v["removed"][0]]["spans"]])
            deleted = " ⟨…⟩ ".join(" ".join(r["text"][s:e].split())[:300] for s, e in spans)
            lines.append(f"\n*Variant `{v['variant']}`* deletes: “{deleted}”")
            words = description_words(v["conversation"][0]["content"])
            lines.append(f"→ gold missing {v['gold_missing']}; description words left {words}")
        else:
            lines.append("\n*No deletable required field* (only the `original` variant).")
        lines.append("")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"gap_spotcheck_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build() -> dict[str, Any]:
    if ABLATION.exists():
        raise SystemExit(f"{ABLATION.relative_to(ROOT)} exists and is frozen.")
    recs = read_jsonl(EXTRACTIONS)
    failed = [r["key"] for r in recs if "extraction" not in r]
    items = [i for r in recs if "extraction" in r for i in build_items(r)]
    dev_keys = {i["key"] for i in items if i["split"] == "dev"}
    assert not dev_keys & {i["key"] for i in items if i["split"] == "test"}, "a key is in both dev and test"
    excluded = Counter(f for r in recs if "extraction" in r for f in field_groups(r)[2])
    meta = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "extraction_prompt": recs[0].get("prompt_version"),
        "tickets": dict(Counter(f"{r['split']}/{r['class']}" for r in recs)),
        "extraction_failures": failed,
        "items": dict(Counter(f"{i['split']}/{i['variant'].split('_')[0]}" for i in items)),
        "items_per_class": dict(Counter(f"{i['split']}/{i['class']}" for i in items)),
        "excluded_fields": dict(excluded),
        "test_sha256": items_sha256([i for i in items if i["split"] == "test"]),
    }
    write_jsonl(ABLATION, items)
    META.write_text(json.dumps(meta, indent=1))
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--show", type=int)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--limit", type=int, help="smoke run: first N tickets per split")
    parser.add_argument("--budget", type=float, default=0.3)
    args = parser.parse_args()
    if args.extract:
        if ABLATION.exists():
            raise SystemExit("The ablation set is frozen; extractions must not change.")
        dev, test = dev_tickets(), test_tickets()
        tickets = dev[: args.limit] + test[: args.limit] if args.limit else dev + test
        budget = Budget(args.budget, llm._settings().log_path, prefix="abl|")
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            recs = list(pool.map(lambda t: extract(t, budget), tickets))
        if not args.limit:
            write_jsonl(EXTRACTIONS, recs)
        ok = [r for r in recs if "extraction" in r]
        fields = [f for r in ok for f in r["extraction"].values()]
        print(
            f"{len(ok)}/{len(recs)} extracted; statuses {dict(Counter(f['status'] for f in fields))}; "
            f"ungrounded confirmed {sum(f['status'] == 'confirmed' and not f['grounded'] for f in fields)}; "
            f"items {sum(len(build_items(r)) for r in ok)}; spent ${budget.spent():.4f}"
            + (f"; projected full run ${budget.spent() / len(recs) * 118:.3f}" if args.limit else "")
        )
    if args.show:
        print(f"Wrote {show(args.show).relative_to(ROOT)}")
    if args.build:
        print(json.dumps(build(), indent=1))


if __name__ == "__main__":
    main()
