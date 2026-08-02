"""The `ChunkPipeline` seam — publish/archive/delete/update rely on this Protocol only.

PRD §4's lifecycle rule couples every status transition to chunk
(re)building: publish chunks + embeds + inserts, archive/delete remove the
content's chunks, editing a published item re-chunks. `app.services.content`
never talks to the embedding provider directly — it calls through this
`Protocol` so phase-2 (this task) can exercise every transition with
`NoopChunkPipeline` and phase-3 task-02 can swap in the real chunking +
embedding implementation later, without touching a single call site in
`content.py` (the brief's Interfaces block: "signatures must not change").
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import Content


class ChunkPipeline(Protocol):
    """The chunk (re)build/removal seam content lifecycle transitions call through.

    Implementations are injected via `app.state.chunk_pipeline` (wired by
    `app.factory.create_app`'s `chunk_pipeline` parameter) — never imported
    or constructed by `app.services.content` itself.
    """

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        """Chunk + embed `content.body_md`, replacing any chunks already stored for it.

        Called on publish and on every edit of an already-published item
        (PRD §4: "re-chunk and re-embed").

        Args:
            session: the caller's `Session` — the same transaction the
                status/timestamp write happened in (PRD §4 atomicity).
            content: the `Content` row to (re)chunk.

        Returns:
            The number of chunks written.
        """
        ...

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        """Remove every chunk stored for `content_id`.

        Called on archive and on delete (PRD §4) — in both cases in the
        same transaction as the status/`is_deleted` write.

        Args:
            session: the caller's `Session`.
            content_id: the `Content.id` whose chunks should be removed.

        Returns:
            The number of chunks removed.
        """
        ...


class NoopChunkPipeline:
    """Phase-2 default `ChunkPipeline`: touches nothing, always returns `0`.

    Wired as `app.state.chunk_pipeline`'s default (`create_app`'s
    `chunk_pipeline=None` parameter) so publish/archive/delete/update run
    end to end before phase-3 task-02 implements real chunking/embedding —
    no embedding provider is required for phase-2's CMS CRUD surface.
    """

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        """Do nothing; always returns `0` (no real chunking in phase-2)."""
        return 0

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        """Do nothing; always returns `0` (no real chunks exist to remove in phase-2)."""
        return 0
