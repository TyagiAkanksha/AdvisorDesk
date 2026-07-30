"""`Chunk` ORM model — RAG units derived from published content (PRD §4 `chunks`)."""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Chunk(Base, TimestampMixin):
    """A retrieval-ready slice of a published content item's `body_md`.

    Hard-delete only (PRD §4.1): chunks are derived data whose physical
    removal is what guarantees retrieval never sees non-published or
    deleted content — no `is_deleted`/`updated_at`. `embedding` is
    `text-embedding-3-small`, 1536 dimensions (PRD §7.2).
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
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
