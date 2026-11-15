"""Add doc evidence to `already_supported` scope labels that have no supporting chunk (labels are NOT changed).

For each such label (dev and test), shows the request and the hybrid top-5 chunks (BM25 + dense RRF) over the
current corpus, incl. the generated reference tables. No model verdicts are shown. You pick the chunk(s) that show
Spark can do it, or "n" if none does. Answers go to data/eval/scope_evidence_added.jsonl (resumable).

Usage:
    python -m src.eval.scope_evidence_cli
"""

from __future__ import annotations

import json
import re
import shutil
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src import llm
from src.components.scope_checker import DESC_CHARS, DocIndex, load_chunks, request_text
from src.retrieval.dense import Embedder
from src.retrieval.text import tokenize

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "eval" / "scope_evidence_added.jsonl"
EMB_DIR = ROOT / "data" / "processed" / "embeddings"
TOP = 5


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def targets() -> list[dict[str, Any]]:
    """already_supported labels without a supporting chunk, with their request text."""
    cands = {c["key"]: c for c in read_jsonl(ROOT / "data" / "eval" / "scope_candidates.jsonl")}
    return [
        {"key": r["key"], "summary": cands[r["key"]]["summary"], "description": cands[r["key"]]["description_md"]}
        for r in read_jsonl(ROOT / "data" / "eval" / "scope_labeled.jsonl")
        if r["label"] == "already_supported" and not r["supporting_chunk_ids"]
    ]


def matching_lines(text: str, query: str, n: int = 3) -> list[str]:
    """Up to n lines of the chunk that contain a distinctive query word (helps inside long reference lists)."""
    generic = {"spark", "support", "supports", "should", "would", "about", "which", "issue"}
    words = {w for w in tokenize(query) if len(w) >= 5 and w not in generic}
    hits = [ln.strip() for ln in text.splitlines() if words & set(tokenize(ln))]
    return hits[:n]


def show(item: dict[str, Any], hits: list[dict], done: int, total: int) -> None:
    width = min(110, shutil.get_terminal_size((110, 30)).columns)
    print("\n" + "═" * width)
    print(f" Scope evidence   [{done}/{total} done]   {item['key']}   your label: already_supported")
    print("─" * width)
    print(textwrap.fill("Summary: " + item["summary"], width))
    desc = item["description"][:DESC_CHARS]
    print(desc + ("…" if len(item["description"]) > DESC_CHARS else ""))
    print("─" * width)
    query = request_text(item["summary"], item["description"])
    for i, c in enumerate(hits, 1):
        body = c["text"].split("\n\n", 1)[-1]
        print(f" [{i}] {c['chunk_id']}   {' > '.join([c['title'], *c['header_path']])}")
        print(f"     {c['url']}")
        print(textwrap.indent(textwrap.fill(" ".join(body.split())[:300] + "…", width - 5), "     "))
        for line in matching_lines(body, query):
            print(f"     ▸ {line[: width - 8]}")
    print("─" * width)


def main() -> None:
    items = targets()
    done = {r["key"] for r in read_jsonl(OUT)}
    embedder_id = llm._settings().models["embedder"]
    chunks = load_chunks()
    index = DocIndex(
        chunks, "hybrid", Embedder(embedder_id), EMB_DIR / f"doc_chunks__{embedder_id.replace('/', '__')}.npy"
    )
    print(f"{len(done)} of {len(items)} done; corpus {len(chunks)} chunks (hybrid top-{TOP}).")
    try:
        for item in items:
            if item["key"] in done:
                continue
            hits = [chunks[i] for i in index.search(request_text(item["summary"], item["description"]), TOP)]
            while True:
                show(item, hits, len(done), len(items))
                answer = input("Supporting chunk(s) e.g. 1,3 | n = none | v<N> = view chunk N | s = skip | q = quit: ")
                answer = answer.strip().lower()
                if re.fullmatch(r"v[1-5]", answer):
                    print("\n" + hits[int(answer[1]) - 1]["text"])
                    input("\n(Enter to go back) ")
                    continue
                if answer in ("q", "s", "n") or re.fullmatch(r"[1-5](\s*,\s*[1-5])*", answer):
                    break
            if answer == "q":
                break
            if answer == "s":
                continue
            added = [] if answer == "n" else [hits[int(x) - 1]["chunk_id"] for x in re.findall(r"[1-5]", answer)]
            with OUT.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "key": item["key"],
                            "added_chunk_ids": sorted(set(added)),
                            "shown": [c["chunk_id"] for c in hits],
                            "retrieval": "hybrid",
                            "labeled_at": datetime.now(UTC).isoformat(timespec="seconds"),
                        }
                    )
                    + "\n"
                )
            done.add(item["key"])
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
    print(f"\n{len(done)} of {len(items)} done → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
