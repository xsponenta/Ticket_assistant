"""Okapi BM25 over a fixed corpus, vectorised with a sparse matrix (scores for all docs in one product)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import CountVectorizer

from src.retrieval.text import tokenize


class BM25Index:
    def __init__(
        self, texts: list[str], tokenizer: Callable[[str], list[str]] = tokenize, k1: float = 1.5, b: float = 0.75
    ) -> None:
        self.vectorizer = CountVectorizer(analyzer=tokenizer)
        tf = self.vectorizer.fit_transform(texts).tocsr().astype(np.float64)
        n_docs = tf.shape[0]
        doc_len = np.asarray(tf.sum(axis=1)).ravel()
        avgdl = doc_len.mean() if n_docs else 0.0
        df = np.bincount(tf.indices, minlength=tf.shape[1])
        idf = np.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        # w = idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl)), computed on the non-zeros only
        norm = k1 * (1 - b + b * doc_len / avgdl) if avgdl else np.full(n_docs, k1)
        rows = np.repeat(np.arange(n_docs), np.diff(tf.indptr))
        data = idf[tf.indices] * tf.data * (k1 + 1) / (tf.data + norm[rows])
        self.weights = csr_matrix((data, tf.indices, tf.indptr), shape=tf.shape)

    def scores(self, query: str) -> np.ndarray:
        """BM25 score of every document for the query (each distinct query term counted once)."""
        q = self.vectorizer.transform([query])
        q.data[:] = 1.0
        return np.asarray((self.weights @ q.T).todense()).ravel()
