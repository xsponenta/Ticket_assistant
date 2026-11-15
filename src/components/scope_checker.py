"""C3 scope checker: is a feature/idea request already supported, does it need development, is it out of scope?

    index = DocIndex(load_chunks(), variant="hybrid", encoder=Embedder(model_id), cache_path=...)
    out, retrieved = check(summary, description, k=5, index=index)     # -> (C3Output, retrieved chunk ids)

Retrieval over the Spark 4.3.0 doc chunks with src/retrieval (BM25 / dense / hybrid RRF); one LLM call (role
"generator") decides the verdict from the request + top-k chunks and cites chunk ids.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src import llm
from src.prompting import Prompt, load_prompt
from src.retrieval.bm25 import BM25Index
from src.retrieval.dense import DenseIndex, TextEncoder
from src.retrieval.hybrid import hybrid_scores
from src.retrieval.text import mask_issue_keys, top_k
from src.schemas.c3 import SCOPE_LABELS, C3Output

ROOT = Path(__file__).resolve().parents[2]
CHUNKS_PATH = ROOT / "data" / "processed" / "doc_chunks.jsonl"
DESC_CHARS = 1500  # as shown to the labeller in src/data/label_cli.py
VARIANTS = ("bm25", "dense", "hybrid")


def load_chunks(path: Path = CHUNKS_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def request_text(summary: str, description: str) -> str:
    return mask_issue_keys(f"{summary.strip()}\n\n{(description or '')[:DESC_CHARS].strip()}".strip())


class DocIndex:
    """Retrieval over doc chunks with one of the shared variants."""

    def __init__(
        self, chunks: list[dict], variant: str, encoder: TextEncoder | None = None, cache_path: Path | None = None
    ) -> None:
        if variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}")
        self.chunks, self.variant = chunks, variant
        self.ids = [c["chunk_id"] for c in chunks]
        texts = [c["text"] for c in chunks]
        self.bm25 = BM25Index(texts) if variant != "dense" else None
        self.dense = DenseIndex(encoder, texts, cache_path) if variant != "bm25" else None

    def search(self, query: str, k: int) -> list[int]:
        if self.variant == "bm25":
            scores = self.bm25.scores(query)
        elif self.variant == "dense":
            scores = self.dense.scores(query)
        else:
            scores = hybrid_scores(self.bm25.scores(query), self.dense.scores(query), depth=max(100, k))
        return [int(i) for i in top_k(np.asarray(scores, dtype=np.float64), k)]


def label_definitions() -> str:
    return "\n".join(f"- {label}: {definition}" for label, definition in SCOPE_LABELS.items())


def build_messages(prompt: Prompt, summary: str, description: str, chunks: list[dict]) -> list[dict[str, str]]:
    rendered = "\n\n".join(prompt.render("chunk", chunk_id=c["chunk_id"], url=c["url"], text=c["text"]) for c in chunks)
    return [
        {"role": "system", "content": prompt.render("system", label_definitions=label_definitions())},
        {
            "role": "user",
            "content": prompt.render(
                "user",
                summary=summary.strip(),
                description=(description or "")[:DESC_CHARS].strip() or "(none)",
                chunks=rendered or "(none)",
            ),
        },
    ]


def check(
    summary: str,
    description: str,
    *,
    k: int,
    index: DocIndex,
    session_id: str | None = None,
    prompt: Prompt | None = None,
) -> tuple[C3Output, list[str]]:
    prompt = prompt or load_prompt("c3_scope")
    hits = [index.chunks[i] for i in index.search(request_text(summary, description), k)]
    out = llm.complete(
        build_messages(prompt, summary, description, hits),
        role="generator",
        component="c3_scope",
        session_id=session_id,
        schema=C3Output,
    )
    return out, [c["chunk_id"] for c in hits]
