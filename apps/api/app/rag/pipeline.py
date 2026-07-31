"""`EmbeddingChunkPipeline` — the real `ChunkPipeline` (PRD §4 lifecycle, §7.2 embeddings).

Fills the phase-2 `app.services.lifecycle.ChunkPipeline` seam: publish
chunks + embeds + inserts in one transaction; editing a published item
re-chunks; archive/delete remove chunks. `app.services.content` never
changes — it already calls through the `ChunkPipeline` Protocol, so wiring
this in (`app/main.py`) is the only change publish/edit/archive/delete need
to go from no-op to real (PRD §4 atomicity: the caller's session commit/
rollback boundary is what makes an embedding failure roll back the whole
transaction — this pipeline only ever `flush()`s, never commits).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.orm import Session

from app.models import Chunk, Content, embedding_column_dims
from app.rag.chunking import chunk_markdown
from app.rag.embeddings import Embedder, EmbeddingFailedError
from app.services.lifecycle import ChunkPipeline

# Dims-validation mechanism (controller decision: pipeline validates dims as
# defense-in-depth beyond `Embedder`'s own check; mechanism is the
# implementer's choice) — `embedding_column_dims()` reads the width off
# `Chunk.__table__`'s mapped column type rather than duplicating the number
# from `Settings.embedding_dimensions`. This is the same value either way
# *by construction* (migration 0002 and `Settings.embedding_dimensions`'s
# default are both 1024), but deriving it from the column keeps this guard
# tied to the actual database constraint that would otherwise reject a
# mismatched vector at INSERT time — the real backstop this check exists to
# pre-empt — instead of a config value that could in principle drift from
# it. Final review: promoted from a private `_expected_dims()` copy here
# (near-duplicate of `app.main`'s own boot-time assertion) to the shared
# `app.models.chunks.embedding_column_dims()` helper both now call.
_EXPECTED_DIMS: int = embedding_column_dims()


def _validate_dims(vectors: Sequence[Sequence[float]]) -> None:
    """Raise `EmbeddingFailedError` if any vector's length != `_EXPECTED_DIMS`.

    Defense-in-depth beyond `Embedder`'s own dimension check (real
    `OpenAICompatibleEmbedder` implementations check themselves; a
    swapped-in fake or a future `Embedder` implementation might not) —
    `EmbeddingChunkPipeline` never lets a wrong-width vector reach an
    INSERT, where it would otherwise fail anyway, just later and with a
    raw driver error instead of the app's typed error family.
    """
    for vector in vectors:
        if len(vector) != _EXPECTED_DIMS:
            raise EmbeddingFailedError(
                f"embedding provider returned a {len(vector)}-dim vector; expected "
                f"{_EXPECTED_DIMS} (Chunk.embedding's configured dimension)."
            )


class EmbeddingChunkPipeline(ChunkPipeline):
    """The real `ChunkPipeline`: `chunk_markdown` + `Embedder` + `Chunk` row (re)writes.

    Every write is `flush()`-only (CONVENTIONS.md §3) — the caller's session
    commit/rollback boundary is what makes a failed embed roll back the
    whole publish/edit transaction (PRD §4 atomicity, §9's rollback pin).
    """

    def __init__(self, embedder: Embedder) -> None:
        """Store the `Embedder` this pipeline chunks and embeds through."""
        self._embedder = embedder

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        """Delete `content`'s existing chunks, then chunk + embed + insert fresh ones.

        Called on publish and on every edit of an already-published item
        (PRD §4). The old rows are deleted first so a failed embed call
        (raised before any new row is added) leaves nothing but the
        caller's rollback to restore them — `_route_session`'s rollback in
        `tests/test_lifecycle.py` is exactly this path.

        Args:
            session: the caller's `Session` — the same transaction the
                status/timestamp write already happened in.
            content: the `Content` row to (re)chunk; `content.body_md` is
                the source text.

        Returns:
            The number of chunks written (`0` for an empty/whitespace-only
            `body_md` — `chunk_markdown` returns `[]`, and the embedder is
            never called for zero chunks).

        Raises:
            EmbeddingFailedError: the embedder call failed, or returned a
                vector whose length doesn't match the configured dimension.
        """
        session.execute(delete(Chunk).where(Chunk.content_id == content.id))

        chunk_data = chunk_markdown(content.body_md)
        if not chunk_data:
            session.flush()
            return 0

        vectors = self._embedder.embed_texts(
            [chunk.text for chunk in chunk_data], input_type="passage"
        )
        _validate_dims(vectors)

        for chunk, vector in zip(chunk_data, vectors, strict=True):
            session.add(
                Chunk(
                    content_id=content.id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    embedding=list(vector),
                )
            )
        session.flush()
        return len(chunk_data)

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        """Delete every chunk stored for `content_id`.

        Called on archive and on delete (PRD §4), in the same transaction
        as the status/`is_deleted` write.

        Args:
            session: the caller's `Session`.
            content_id: the `Content.id` whose chunks should be removed.

        Returns:
            The number of chunk rows removed.
        """
        # `session.execute` on a Core `delete()` returns a driver-backed
        # `CursorResult` at runtime (it only types as the broader `Result`
        # base) — narrowed here so `.rowcount` (`Result` itself has no such
        # attribute) type-checks under mypy strict.
        result = cast(
            "CursorResult[Any]",
            session.execute(delete(Chunk).where(Chunk.content_id == content_id)),
        )
        session.flush()
        return result.rowcount or 0
