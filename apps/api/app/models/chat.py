"""`ChatSession`/`ChatMessage` ORM models — client app chat (PRD §4)."""

from __future__ import annotations

import uuid

from sqlalchemy import REAL, Boolean, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class ChatSession(Base, TimestampMixin):
    """An anonymous client chat session; id is held client-side (PRD §4, §5.3).

    Append-only (PRD §4.1): `created_at` only.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()


class ChatMessage(Base, TimestampMixin):
    """A single turn in a `ChatSession` — append-only (PRD §4.1).

    `citations`/`retrieval_found`/`top_similarity` are populated on
    assistant rows only (PRD §4, §7.4); user rows leave them null.
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="role_valid"),
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    retrieval_found: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    top_similarity: Mapped[float | None] = mapped_column(REAL, nullable=True)
