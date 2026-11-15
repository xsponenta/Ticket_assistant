"""Text helpers shared by the retrieval indexes."""

from __future__ import annotations

import re

import numpy as np

# Jira issue keys of any ASF project (SPARK-123, HIVE-45, ...). Standards and identifiers that share the shape
# (UTF-8, SHA-256, ISO-8601, CVE-2023-1234, JEP-411, ...) are not issue keys and are left alone.
NOT_ISSUE_PREFIXES = "UTF|SHA|ISO|AES|RFC|CVE|JSR|JEP|GHSA|MD|TLS|SSL|HTTP|IEEE|ECMA|UTC|GMT|IPV|PEP|ANSI|ASCII|X"
ISSUE_KEY_RE = re.compile(rf"\b(?!(?:{NOT_ISSUE_PREFIXES})-)[A-Z][A-Z0-9_]+-\d+\b")
ISSUE_TOKEN = "<ISSUE>"

STOPWORDS = set(
    """a an the and or but if then of to in on at by for with from into is are was were be been being it its this
    that these those as not no can could should would will may might must we you they i he she our your their there
    here which who what when where why how do does did have has had also just only all any some such than too very
    via per so up out""".split()
)
TOKEN_RE = re.compile(r"[a-z0-9_]+")


def mask_issue_keys(text: str) -> str:
    return ISSUE_KEY_RE.sub(ISSUE_TOKEN, text)


def issue_keys(text: str) -> set[str]:
    return set(ISSUE_KEY_RE.findall(text))


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens without stopwords. Dotted identifiers are split into their parts
    (spark.sql.adaptive -> spark, sql, adaptive); the <ISSUE> token becomes 'issue'."""
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def top_k(scores: np.ndarray, k: int, mask: np.ndarray | None = None) -> np.ndarray:
    """Indices of the k highest scores among allowed items (mask True = allowed), best first; ties by index."""
    s = scores.astype(np.float64, copy=True)
    if mask is not None:
        s[~mask] = -np.inf
    allowed = int(np.isfinite(s).sum())
    k = min(k, allowed)
    if k <= 0:
        return np.array([], dtype=int)
    idx = np.argpartition(-s, k - 1)[:k] if k < len(s) else np.arange(len(s))
    return idx[np.lexsort((idx, -s[idx]))][:k]
