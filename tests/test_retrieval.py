"""src/retrieval: key masking, tokenizer, BM25, top-k with mask, RRF, dense cache (fake encoder, no download)."""

import numpy as np

from src.retrieval.bm25 import BM25Index
from src.retrieval.dense import DenseIndex
from src.retrieval.hybrid import hybrid_scores, rrf
from src.retrieval.text import issue_keys, mask_issue_keys, tokenize, top_k


class FakeEncoder:
    """Bag-of-letters vectors: deterministic, enough to test caching and cosine ranking."""

    model_id = "fake/letters"

    def __init__(self) -> None:
        self.calls = 0

    def _vec(self, texts):
        self.calls += 1
        m = (
            np.array([[t.lower().count(c) for c in "abcdefghijklmnopqrstuvwxyz"] for t in texts], dtype=np.float32)
            + 1e-3
        )
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    encode_queries = _vec
    encode_passages = _vec


def test_issue_key_masking_keeps_standards():
    text = "Same as SPARK-1234 and HIVE-99; uses UTF-8, SHA-256, ISO-8601 and CVE-2023-34462 (see SPARK-1234)."
    assert issue_keys(text) == {"SPARK-1234", "HIVE-99"}
    masked = mask_issue_keys(text)
    assert "SPARK-1234" not in masked and masked.count("<ISSUE>") == 3
    assert "UTF-8" in masked and "SHA-256" in masked and "CVE-2023-34462" in masked


def test_tokenize():
    assert tokenize("Set spark.sql.adaptive.enabled to TRUE for the <ISSUE>") == [
        "set",
        "spark",
        "sql",
        "adaptive",
        "enabled",
        "true",
        "issue",
    ]


def test_bm25_ranks_relevant_doc_first_and_ignores_unknown_terms():
    docs = ["netty upgrade to fix CVE", "join fails with null pointer exception", "kafka source offsets lost"]
    index = BM25Index(docs)
    scores = index.scores("NullPointerException in join: null pointer")
    assert int(np.argmax(scores)) == 1
    assert index.scores("zzzz unknownterm").sum() == 0


def test_top_k_respects_mask_and_ties():
    scores = np.array([0.9, 0.5, 0.9, 0.1])
    assert top_k(scores, 2).tolist() == [0, 2]
    assert top_k(scores, 3, mask=np.array([False, True, True, True])).tolist() == [2, 1, 3]
    assert top_k(scores, 5, mask=np.array([False, False, False, False])).tolist() == []


def test_rrf_and_hybrid():
    fused = rrf([np.array([2, 0]), np.array([0, 1])], n=3, k=60)
    assert np.allclose(fused, [1 / 62 + 1 / 61, 1 / 62, 1 / 61])
    mask = np.array([True, True, False])
    h = hybrid_scores(np.array([0.1, 0.9, 5.0]), np.array([0.9, 0.2, 0.99]), mask, depth=2)
    assert np.isneginf(h[2]) and h[0] == h[1]  # each item is first in one ranking and second in the other


def test_dense_index_cache_round_trip(tmp_path):
    texts = ["apache spark", "zebra quiz", "spark streaming"]
    enc = FakeEncoder()
    path = tmp_path / "emb.npy"
    first = DenseIndex(enc, texts, path)
    calls = enc.calls
    second = DenseIndex(enc, texts, path)  # loaded from cache, no encoding
    assert enc.calls == calls and np.allclose(first.matrix, second.matrix)
    DenseIndex(enc, [*texts, "new doc"], path)  # texts changed -> re-encoded
    assert enc.calls == calls + 1
    assert int(np.argmax(first.scores("spark"))) in (0, 2)
