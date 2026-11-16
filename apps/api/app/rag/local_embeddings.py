"""In-process open-source embeddings (`EMBEDDING_PROVIDER=local`, PRD §7.2).

`LocalEmbedder` runs a small ONNX model (`fastembed`, default `BAAI/bge-small-en-v1.5`) inside
the api process: no key, no outside service. The model is 384 wide while `chunks.embedding` is
`vector(1024)`, so each vector is right-padded with `0.0` — zero padding changes neither the dot
product nor either norm, so cosine similarity (the only operator retrieval uses) is preserved
exactly and no migration is needed.

`fastembed` is imported lazily in `from_settings` so a process on another provider never loads
onnxruntime.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Sequence
from typing import Literal, Protocol

from app.config import Settings
from app.services.errors import EmbeddingFailedError

logger = logging.getLogger(__name__)

__all__ = ["LocalEmbedder"]

# One document per model call: the fastest setting on the 2-vCPU box and the lightest on memory
# (~290 MB peak vs ~590 MB at batch 16), which matters with no swap.
_BATCH_SIZE = 1


class _EmbeddingModel(Protocol):
    """The slice of `fastembed.TextEmbedding` this module uses."""

    def embed(self, documents: list[str], batch_size: int = ...) -> Iterable[Iterable[float]]:
        """Lazily yield one vector per document."""
        ...


class LocalEmbedder:
    """An `app.rag.embeddings.Embedder` backed by an in-process model."""

    def __init__(self, *, model: _EmbeddingModel, dimensions: int, query_prefix: str = "") -> None:
        """Store the loaded model, the padded output width and the query-side prefix."""
        self._model = model
        self._dimensions = dimensions
        self._query_prefix = query_prefix
        # FastAPI runs sync endpoints on a thread pool; serialising bounds memory and a single
        # query takes ~12 ms, so it costs nothing.
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> LocalEmbedder:
        """Load the model eagerly (fail fast at boot, first query fast).

        Raises:
            RuntimeError: the model could not be loaded; names the settings to check.
        """
        from fastembed import TextEmbedding  # lazy: keep onnxruntime out of other providers

        try:
            model = TextEmbedding(
                model_name=settings.local_embedding_model,
                cache_dir=settings.local_embedding_cache_dir,
                threads=settings.local_embedding_threads,
                local_files_only=settings.local_embedding_offline,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not load the local embedding model "
                f"{settings.local_embedding_model!r}; check LOCAL_EMBEDDING_MODEL and "
                "LOCAL_EMBEDDING_CACHE_DIR (and LOCAL_EMBEDDING_OFFLINE if the cache is empty)."
            ) from exc
        return cls(
            model=model,
            dimensions=settings.embedding_dimensions,
            query_prefix=settings.local_embedding_query_prefix,
        )

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        """Embed `texts` in order; queries get the model's query prefix, passages none.

        Raises:
            EmbeddingFailedError: the model failed, returned a different number of vectors than
                texts, or returned a vector wider than the configured dimension.
        """
        if not texts:
            return []
        prefix = self._query_prefix if input_type == "query" else ""
        inputs = [prefix + text for text in texts]
        try:
            # `.embed` is lazy: the lock must cover iterating the output, not just the call.
            with self._lock:
                raw = [
                    [float(x) for x in vector]
                    for vector in self._model.embed(inputs, batch_size=_BATCH_SIZE)
                ]
        except Exception as exc:
            logger.warning("local embedding failed: %s", exc)
            raise EmbeddingFailedError("The embedding provider call failed.") from exc

        if len(raw) != len(texts):
            raise EmbeddingFailedError(
                f"local embedder returned {len(raw)} vector(s) for {len(texts)} input text(s)."
            )
        for vector in raw:
            if len(vector) > self._dimensions:
                raise EmbeddingFailedError(
                    f"local embedder returned a {len(vector)}-dim vector; at most "
                    f"{self._dimensions} (settings.embedding_dimensions) is allowed."
                )
        return [vector + [0.0] * (self._dimensions - len(vector)) for vector in raw]
