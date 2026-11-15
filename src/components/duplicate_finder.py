"""C2 duplicate finder: earlier SPARK issues similar to a draft ticket (BM25, dense or hybrid RRF; no LLM).

    finder = DuplicateFinder(issues_df, variant="hybrid", encoder=Embedder(model_id), alert_threshold=0.85)
    out = finder.find(summary, description, mode="full")            # -> C2Output (top 5 + alert flag)

Docs and queries = summary + first 1500 characters of the description (mode "summary": summary only), with Jira
issue keys masked as <ISSUE> so that two tickets citing the same issue are not matched on the key alone.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.retrieval.bm25 import BM25Index
from src.retrieval.dense import DenseIndex, TextEncoder
from src.retrieval.hybrid import hybrid_scores
from src.retrieval.text import mask_issue_keys, top_k
from src.schemas.c2 import JIRA_BROWSE, C2Output, DuplicateCandidate

DESC_CHARS = 1500
VARIANTS = ("bm25", "dense", "hybrid")
TOP = 5


def issue_text(summary: str, description: str, mode: str = "full", mask_keys: bool = True) -> str:
    text = (
        summary.strip()
        if mode == "summary" or not (description or "").strip()
        else (f"{summary.strip()}\n\n{description[:DESC_CHARS].strip()}")
    )
    return mask_issue_keys(text) if mask_keys else text


def utc_naive(ts: pd.Timestamp | str) -> np.datetime64:
    """Timestamp as naive UTC datetime64[ns] (comparable with the corpus' creation times)."""
    ts = pd.Timestamp(ts)
    ts = ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo else ts
    return np.datetime64(ts.to_datetime64(), "ns")


class DuplicateFinder:
    def __init__(
        self,
        issues: pd.DataFrame,
        variant: str,
        encoder: TextEncoder | None = None,
        alert_threshold: float = float("inf"),
        cache_path: Path | None = None,
        mask_keys: bool = True,
    ) -> None:
        if variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}")
        if variant != "bm25" and encoder is None:
            raise ValueError("dense and hybrid variants need an encoder")
        self.variant, self.alert_threshold, self.mask_keys = variant, alert_threshold, mask_keys
        self.keys = np.asarray(issues.key)
        self.summaries = list(issues.summary)
        self.created = pd.to_datetime(issues.created, utc=True).dt.tz_localize(None).to_numpy(dtype="datetime64[ns]")
        texts = [
            issue_text(s, d, "full", mask_keys) for s, d in zip(issues.summary, issues.description_md, strict=True)
        ]
        self.bm25 = BM25Index(texts) if variant != "dense" else None
        self.dense = DenseIndex(encoder, texts, cache_path) if variant != "bm25" else None

    def mask(self, created_before: pd.Timestamp | None, exclude_key: str | None) -> np.ndarray:
        allowed = np.ones(len(self.keys), dtype=bool)
        if created_before is not None:
            allowed &= self.created < utc_naive(created_before)
        if exclude_key is not None:
            allowed &= self.keys != exclude_key
        return allowed

    def score(self, query: str, allowed: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        """(ranking scores, dense cosines or None) for every corpus item; disallowed items get -inf."""
        dense = self.dense.scores(query) if self.dense is not None else None
        if self.variant == "bm25":
            s = self.bm25.scores(query).astype(np.float64)
        elif self.variant == "dense":
            s = dense.astype(np.float64)
        else:
            s = hybrid_scores(self.bm25.scores(query), dense, allowed)
        s = s.copy()
        s[~allowed] = -np.inf
        return s, dense

    def search(
        self,
        summary: str,
        description: str = "",
        mode: str = "full",
        created_before: pd.Timestamp | None = None,
        exclude_key: str | None = None,
        depth: int = TOP,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """(ranked corpus indices up to `depth`, their scores, alert_score). alert_score = dense cosine of the
        top-1 candidate (dense / hybrid) or its BM25 score (bm25)."""
        query = issue_text(summary, description, mode, self.mask_keys)
        allowed = self.mask(created_before, exclude_key)
        scores, dense = self.score(query, allowed)
        ranked = top_k(scores, depth, allowed)
        if not len(ranked):
            return ranked, scores[ranked], 0.0
        alert_score = float(dense[ranked[0]]) if dense is not None else float(scores[ranked[0]])
        return ranked, scores[ranked], alert_score

    def find(
        self,
        summary: str,
        description: str = "",
        mode: str = "full",
        created_before: pd.Timestamp | None = None,
        exclude_key: str | None = None,
    ) -> C2Output:
        ranked, scores, alert_score = self.search(summary, description, mode, created_before, exclude_key, TOP)
        candidates = [
            DuplicateCandidate(
                key=str(self.keys[i]),
                summary=self.summaries[i],
                url=JIRA_BROWSE + str(self.keys[i]),
                score=round(float(s), 6),
            )
            for i, s in zip(ranked, scores, strict=True)
        ]
        return C2Output(candidates=candidates, alert=alert_score >= self.alert_threshold, alert_score=alert_score)

    def timed_find(self, *args, **kwargs) -> tuple[C2Output, float]:
        start = time.perf_counter()
        out = self.find(*args, **kwargs)
        return out, 1000 * (time.perf_counter() - start)
