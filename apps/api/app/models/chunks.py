"""`Chunk` ORM model — RAG units derived from published content (PRD §4 `chunks`)."""

from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Chunk(Base, TimestampMixin):
    """A retrieval-ready slice of a published content item's `body_md`.

    Hard-delete only (PRD §4.1): chunks are derived data whose physical
    removal is what guarantees retrieval never sees non-published or
    deleted content — no `is_deleted`/`updated_at`. `embedding` is
    `nvidia/nv-embedqa-e5-v5`, 1024 dimensions (PRD §7.2, v1.5; migration
    0002 resized this column from the earlier `text-embedding-3-small`
    1536-dim shape).
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_content_id", "content_id"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)


@event.listens_for(Chunk, "load")
def _normalize_embedding_on_load(chunk: Chunk, _context: Any) -> None:
    """Coerce a freshly loaded `chunk.embedding` to a plain `list[float]`.

    Phase-3 task-02 controller decision: `Chunk.embedding`'s Python-side
    contract is `list[float]` on every read, from a fresh session — matching
    the `Mapped[list[float] | None]` annotation above literally, not just in
    the type checker's eyes — regardless of what the installed
    pgvector-python version or the psycopg driver's own (optional, unused
    here — see `app/db.py`, no `register_vector` call) type adapters hand
    back at the wire level in some pgvector-python/driver combination (a
    bare numpy `ndarray`, or a list of numpy scalar elements). SQLAlchemy's
    `"load"` event fires every time an ORM instance is populated from a
    result row, including a genuinely fresh session with no identity-map
    hit, so this is the one hook that covers every read path — including a
    plain `session.execute(select(Chunk)...)`, not just reads that happen to
    go through `app.rag.pipeline`.

    This is deliberately a normalization event, not a new SQLAlchemy column
    type: keeping the mapped column itself as a bare `pgvector.sqlalchemy.
    Vector(1024)` (matching migration 0002's DDL exactly, byte for byte)
    keeps the ORM<->migration parity gate
    (`tests/test_models_schema.py::test_orm_metadata_matches_migration_head`)
    trivially green — a custom `TypeEngine` subclass would risk Alembic's
    autogenerate type comparison flagging a spurious diff for no schema
    reason at all.
    """
    if chunk.embedding is not None and not isinstance(chunk.embedding, list):
        chunk.embedding = [float(value) for value in chunk.embedding]
