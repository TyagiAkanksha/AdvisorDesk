"""`ChatSession`/`ChatMessage` ORM models — client app chat (PRD §4)."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    REAL,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
)
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

    Phase-9 DESIGN §A adds two more assistant-only signals, both nullable with no default —
    "never asked"/"never measured" must stay distinguishable from a real value: `feedback`
    (thumbs up/down from `POST /public/chat/{message_id}/feedback`, a later task) and
    `latency_ms` (the route's own whole-answer `time.monotonic()` measurement).
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="role_valid"),
        CheckConstraint("feedback in (-1, 1)", name="feedback_valid"),
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
    feedback: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
