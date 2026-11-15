"""Hybrid retrieval: reciprocal rank fusion (RRF) of a BM25 and a dense ranking."""

from __future__ import annotations

import numpy as np

from src.retrieval.text import top_k

RRF_K = 60


def rrf(rankings: list[np.ndarray], n: int, k: int = RRF_K) -> np.ndarray:
    """Fused score per item: sum over rankings of 1 / (k + rank), rank starting at 1; 0 if absent."""
    fused = np.zeros(n, dtype=np.float64)
    for ranking in rankings:
        fused[ranking] += 1.0 / (k + np.arange(1, len(ranking) + 1))
    return fused


def hybrid_scores(
    bm25_scores: np.ndarray, dense_scores: np.ndarray, mask: np.ndarray | None = None, depth: int = 100, k: int = RRF_K
) -> np.ndarray:
    """RRF of the top-`depth` BM25 and dense rankings within the allowed items (items outside both get 0)."""
    n = len(bm25_scores)
    fused = rrf([top_k(bm25_scores, depth, mask), top_k(dense_scores, depth, mask)], n, k)
    if mask is not None:
        fused[~mask] = -np.inf
    return fused
