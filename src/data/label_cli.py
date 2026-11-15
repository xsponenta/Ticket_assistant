"""Interactive CLI for manual scope labelling of data/eval/scope_candidates.jsonl.

For each candidate it shows the summary, the first 1500 characters of the description and the top-5 doc chunks
(BM25 over data/processed/doc_chunks.jsonl), then asks for a label, optional supporting chunks and a note.
Every answer is appended to data/eval/scope_labeled.jsonl immediately, so you can quit at any time and resume.

Usage:
    python src/data/label_cli.py              # resume where you stopped
    python src/data/label_cli.py --show-hint  # also show the Jira resolution (off by default: it can bias labels)
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import textwrap
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prep_stats import EVAL, PROCESSED, SEED

LABELS = {
    "1": ("already_supported", "doable today with an existing API/config"),
    "2": ("needs_development", "reasonable for Spark but needs code changes"),
    "3": ("out_of_scope", "better as a third-party project, contradicts Spark design, or another product"),
    "4": ("insufficient_info", "cannot decide"),
}
DESCRIPTION_CHARS = 1500
TOP_K = 5
STOP = set("""a an the and or but if then of to in on at by for with from into is are was were be been being it its this that
these those as not no can could should would will may might must we you they i he she our your their there here which who
what when where why how do does did have has had also just only all any some such than too very via per so up out""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) > 1 and t not in STOP]


class BM25:
    """Okapi BM25 (k1=1.5, b=0.75) with an inverted index."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.lengths = [len(d) for d in docs]
        self.avgdl = sum(self.lengths) / max(1, len(docs))
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, doc in enumerate(docs):
            for term, tf in Counter(doc).items():
                self.postings[term].append((i, tf))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def top_k(self, query: list[str], k: int = TOP_K) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(query):
            for i, tf in self.postings.get(term, ()):
                norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avgdl)
                scores[i] += self.idf[term] * tf * (self.k1 + 1) / norm
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_label(answer: str) -> str | None:
    """'1'..'4' or a label name -> label name; anything else -> None."""
    answer = answer.strip().lower()
    if answer in LABELS:
        return LABELS[answer][0]
    names = {name for name, _ in LABELS.values()}
    return answer if answer in names else None


def parse_chunks(answer: str, shown: list[str]) -> list[str]:
    """'1,3' (positions in the shown list) and/or chunk ids -> list of chunk ids."""
    ids = []
    for part in re.split(r"[,\s]+", answer.strip()):
        if not part:
            continue
        if part.isdigit() and 1 <= int(part) <= len(shown):
            ids.append(shown[int(part) - 1])
        elif "#" in part:
            ids.append(part)
    return list(dict.fromkeys(ids))


def show_candidate(c: dict[str, Any], done: int, total: int, hits: list[tuple[dict, float]], show_hint: bool) -> None:
    width = min(110, shutil.get_terminal_size((110, 30)).columns)
    rule = "─" * width
    print("\n" + "═" * width)
    print(f" Scope labelling   [{done}/{total} labelled · {total - done} left]")
    print(rule)
    for key, (name, definition) in LABELS.items():
        print(f"  {key}  {name:<18} {definition}")
    print(rule)
    meta = f"{c['key']} · {c['target_class']} · components: {', '.join(c['components']) or '—'}"
    if show_hint:
        meta += f" · resolution hint: {c['resolution_hint']}"
    print(meta)
    print(textwrap.fill("Summary: " + c["summary"], width))
    print(f"\nDescription (first {DESCRIPTION_CHARS} chars):")
    print(c["description_md"][:DESCRIPTION_CHARS] + ("…" if len(c["description_md"]) > DESCRIPTION_CHARS else ""))
    print(rule)
    print(f"Top-{TOP_K} doc chunks (BM25):")
    for i, (chunk, score) in enumerate(hits, 1):
        body = " ".join(chunk["text"].split("\n\n", 1)[-1].split())
        print(f" [{i}] {chunk['chunk_id']}   score {score:.1f}")
        print(f"     {' > '.join([chunk['title'], *chunk['header_path']])}")
        print(f"     {chunk['url']}")
        print(textwrap.indent(textwrap.fill(body[:280] + "…", width - 5), "     "))
    print(rule)


# Expected scope label for each Jira resolution, following the contributing guide's resolution conventions.
# An assumption, used only to measure agreement with the resolution hint (the hint is not a label).
HINT_TO_LABEL = {
    "Fixed": "needs_development",  # a change was made, so code had to change
    "Won't Fix": "out_of_scope",  # "no support or interest in acting on it"
    "Won't Do": "out_of_scope",
    "Later": "out_of_scope",
    "Invalid": "out_of_scope",  # "not actionable, for example a non-Spark issue"
    "Not A Problem": "already_supported",  # works as intended / obsolete
    "Incomplete": "insufficient_info",
}


def summarize(labelled: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Count, label distribution, majority-class accuracy (C3 reference point), agreement with the resolution hint."""
    hint = {c["key"]: c["resolution_hint"] for c in candidates}
    bucket = {c["key"]: c["bucket"] for c in candidates}
    rows = [r for r in labelled if r["key"] in hint]
    if not rows:
        return {"labelled": 0, "candidates": len(candidates)}
    dist = Counter(r["label"] for r in rows)
    majority, majority_n = dist.most_common(1)[0]
    agree = [HINT_TO_LABEL.get(hint[r["key"]]) == r["label"] for r in rows]
    table: dict[str, Counter] = {}
    for r in rows:
        table.setdefault(bucket[r["key"]], Counter())[r["label"]] += 1
    return {
        "labelled": len(rows),
        "candidates": len(candidates),
        "label_distribution": dict(dist.most_common()),
        "majority_label": majority,
        "majority_class_accuracy": round(majority_n / len(rows), 3),
        "agreement_with_resolution_hint": round(sum(agree) / len(rows), 3),
        "hint_mapping": HINT_TO_LABEL,
        "bucket_x_label": {b: dict(c) for b, c in sorted(table.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual scope labelling.")
    parser.add_argument("--candidates", type=Path, default=EVAL / "scope_candidates.jsonl")
    parser.add_argument("--chunks", type=Path, default=PROCESSED / "doc_chunks.jsonl")
    parser.add_argument("--out", type=Path, default=EVAL / "scope_labeled.jsonl")
    parser.add_argument("--show-hint", action="store_true", help="show the Jira resolution of each candidate")
    parser.add_argument("--summary", action="store_true", help="summary of the labels so far (no labelling)")
    args = parser.parse_args()

    if args.summary:
        result = summarize(read_jsonl(args.out), read_jsonl(args.candidates))
        print(json.dumps(result, indent=1))
        if not result["labelled"]:
            print(f"No labels yet in {args.out}: run `python src/data/label_cli.py` first.")
        return

    candidates = read_jsonl(args.candidates)
    chunks = read_jsonl(args.chunks)
    if not candidates or not chunks:
        raise SystemExit("Missing input: run prepare.py, split.py, build_eval.py and chunk_docs.py first.")
    bm25 = BM25([tokenize(c["text"]) for c in chunks])
    labelled = {r["key"] for r in read_jsonl(args.out)}
    # Fixed shuffled order (seed 42): the file is grouped by resolution bucket, which would leak the hint.
    random.Random(SEED).shuffle(candidates)
    todo = [c for c in candidates if c["key"] not in labelled]
    print(f"{len(labelled)} of {len(candidates)} already labelled in {args.out}")

    try:
        label_loop(todo, candidates, chunks, bm25, labelled, args)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
    print(f"\n{len(labelled)} of {len(candidates)} labelled → {args.out}")


def label_loop(todo: list[dict], candidates: list[dict], chunks: list[dict], bm25: BM25, labelled: set[str],
               args: argparse.Namespace) -> None:
    for c in todo:
        hits = [(chunks[i], s) for i, s in bm25.top_k(tokenize(c["summary"] + " " + c["description_md"][:DESCRIPTION_CHARS]))]
        show_candidate(c, len(labelled), len(candidates), hits, args.show_hint)
        shown = [h[0]["chunk_id"] for h in hits]
        while True:
            answer = input("Label [1-4], s = skip, q = quit: ").strip().lower()
            if answer in ("q", "s") or parse_label(answer):
                break
            print("  Please type 1, 2, 3, 4, s or q.")
        if answer == "q":
            return
        if answer == "s":
            continue
        supporting = parse_chunks(input("Supporting chunks (e.g. 1,3 or chunk ids; Enter = none): "), shown)
        note = input("Note (Enter = none): ").strip()
        record = {"key": c["key"], "label": parse_label(answer), "supporting_chunk_ids": supporting, "note": note,
                  "bm25_top5": shown, "target_class": c["target_class"], "summary": c["summary"],
                  "labeled_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with args.out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        labelled.add(c["key"])


if __name__ == "__main__":
    main()
