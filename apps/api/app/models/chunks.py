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


def _normalize_embedding(chunk: Chunk) -> None:
    """Coerce `chunk.embedding` to a plain `list[float]` if it isn't already one.

    Shared body for both the `"load"` and `"refresh"` listeners below — see
    their docstrings for why both are needed.
    """
    if chunk.embedding is not None and not isinstance(chunk.embedding, list):
        chunk.embedding = [float(value) for value in chunk.embedding]


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
    hit — but it does NOT fire on `session.refresh(chunk)` or an
    expired-attribute reload (an attribute accessed after `session.expire()`
    or at the end of a committed transaction with `expire_on_commit=True`),
    which SQLAlchemy routes through the separate `"refresh"` event instead
    (review round 1, finding M2) — see `_normalize_embedding_on_refresh`
    below for that path. Together, the two events are what actually cover
    every read path — including a plain `session.execute(select(Chunk)...)`
    load AND a `session.refresh()`/expired-attribute reload, not just reads
    that happen to go through `app.rag.pipeline`.

    This is deliberately a normalization event, not a new SQLAlchemy column
    type: keeping the mapped column itself as a bare `pgvector.sqlalchemy.
    Vector(1024)` (matching migration 0002's DDL exactly, byte for byte)
    keeps the ORM<->migration parity gate
    (`tests/test_models_schema.py::test_orm_metadata_matches_migration_head`)
    trivially green — a custom `TypeEngine` subclass would risk Alembic's
    autogenerate type comparison flagging a spurious diff for no schema
    reason at all.
    """
    _normalize_embedding(chunk)


def embedding_column_dims() -> int:
    """Return the vector width `Chunk.embedding`'s pgvector column actually enforces.

    Reads the dimension off `Chunk.__table__`'s mapped column type rather
    than a duplicated literal or `Settings.embedding_dimensions`, so callers
    stay tied to the real database constraint (migration 0002's DDL) instead
    of a config value that could in principle drift from it. Promoted here
    (final review, phase-3 t02 minor: dim-introspection duplication) from
    what used to be two near-identical private copies -- `app.rag.pipeline`'s
    defense-in-depth vector-width guard and `app.main`'s boot-time
    `embedding_dimensions` assertion both call this instead of re-deriving
    the same thing.

    Raises:
        RuntimeError: if `Chunk.embedding` is ever mapped to something other
            than a dimensioned `pgvector.sqlalchemy.Vector` column (would
            only happen from a model-definition bug -- migration 0002
            already sizes the real column).
    """
    column_type = Chunk.__table__.c.embedding.type
    if not isinstance(column_type, Vector) or column_type.dim is None:
        raise RuntimeError(
            "Chunk.embedding must be a dimensioned pgvector Vector column for "
            "embedding_column_dims() to read its width."
        )
    return column_type.dim


@event.listens_for(Chunk, "refresh")
def _normalize_embedding_on_refresh(chunk: Chunk, _context: Any, _attrs: Any) -> None:
    """Coerce `chunk.embedding` to a plain `list[float]` on a `"refresh"` reload.

    Review round 1, finding M2: the `"load"` listener above only fires when
    an ORM instance is first populated from a result row — `session.
    refresh(chunk)` and an expired-attribute reload (e.g. an attribute
    touched after `session.expire()`, or after a commit under
    `expire_on_commit=True`) repopulate an *existing* instance in place and
    fire SQLAlchemy's separate `"refresh"` event instead, which the `"load"`
    listener never sees. Without this twin, that path could hand back a
    non-`list` `chunk.embedding` despite the `"load"` guard, silently
    breaking the same `list[float]`-on-every-read contract for exactly the
    callers most likely to hit it (a long-lived session that re-reads a
    `Chunk` after another transaction touched it). `_attrs` (the specific
    attribute names being refreshed, or `None` for "all") is unused — the
    normalization always re-checks `embedding` unconditionally, same as the
    `"load"` listener, since re-deriving it from an already-normalized list
    is a no-op.
    """
    _normalize_embedding(chunk)
