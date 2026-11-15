"""Dense retrieval with small local sentence-transformers (CPU), with on-disk caching of corpus embeddings."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Protocol

import numpy as np

# (query prefix, passage prefix) as documented by each model for retrieval.
PREFIXES = {
    "BAAI/bge-small-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "sentence-transformers/all-MiniLM-L6-v2": ("", ""),
    "intfloat/e5-small-v2": ("query: ", "passage: "),
}


class TextEncoder(Protocol):
    model_id: str

    def encode_queries(self, texts: list[str]) -> np.ndarray: ...

    def encode_passages(self, texts: list[str]) -> np.ndarray: ...


class Embedder:
    """sentence-transformers model with its query/passage prefixes; L2-normalised float32 vectors."""

    def __init__(self, model_id: str, device: str = "cpu", batch_size: int = 64) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, only when dense retrieval is used

        self.model_id, self.batch_size = model_id, batch_size
        self.query_prefix, self.passage_prefix = PREFIXES.get(model_id, ("", ""))
        self.model = SentenceTransformer(model_id, device=device)

    def _encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([self.query_prefix + t for t in texts])

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([self.passage_prefix + t for t in texts])


def texts_hash(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class DenseIndex:
    """Corpus embeddings, loaded from `cache_path` (.npy + .json manifest) when model and texts match."""

    def __init__(self, encoder: TextEncoder, texts: list[str], cache_path: Path | None = None) -> None:
        self.encoder = encoder
        self.encode_seconds = 0.0
        digest = texts_hash(texts)
        manifest = cache_path.with_suffix(".json") if cache_path else None
        if cache_path and cache_path.exists() and manifest.exists():
            meta = json.loads(manifest.read_text())
            if meta.get("model_id") == encoder.model_id and meta.get("texts_sha256") == digest:
                self.matrix = np.load(cache_path)
                self.encode_seconds = meta.get("encode_seconds", 0.0)
                return
        start = time.perf_counter()
        self.matrix = encoder.encode_passages(texts)
        self.encode_seconds = round(time.perf_counter() - start, 1)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache_path, self.matrix)
            manifest.write_text(
                json.dumps(
                    {
                        "model_id": encoder.model_id,
                        "texts_sha256": digest,
                        "n": len(texts),
                        "dim": int(self.matrix.shape[1]),
                        "encode_seconds": self.encode_seconds,
                    }
                )
            )

    def scores(self, query: str) -> np.ndarray:
        return self.scores_from_vector(self.encoder.encode_queries([query])[0])

    def scores_from_vector(self, query_vector: np.ndarray) -> np.ndarray:
        """Cosine similarity (vectors are normalised)."""
        return self.matrix @ query_vector
