"""`Content`, `Tag`, and `ContentTag` ORM models (PRD §4 `content`/`tags`/`content_tags`)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin, uuid_pk


class Content(Base, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin):
    """The core CMS entity: a piece of advisory guidance.

    `author_id` doubles as the created-by column (set once, never changed)
    and `updated_by` records the last writer; both are nullable because the
    seed script (PRD §8) writes outside any admin session (PRD §4.1).
    """

    __tablename__ = "content"
    __table_args__ = (
        CheckConstraint("status in ('draft', 'published', 'archived')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    body_md: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default=text("'draft'")
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Tag(Base, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin):
    """A content tag, e.g. `tax-planning`.

    PRD §4.1: creating a tag whose name matches a soft-deleted row
    reactivates that row (same `id`) rather than inserting — a service-layer
    concern, not modeled here. Tags carry no actor columns (PRD §4.1: the
    audit trail lives on the content row).
    """

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class ContentTag(Base, TimestampMixin):
    """The `content`↔`tag` join row.

    Append-only per PRD §4.1's mutable-table rule: `created_at` only, no
    `updated_at`/`is_deleted`, no surrogate `id` — the composite primary key
    is `(content_id, tag_id)`, exactly as PRD §4 specifies.
    """

    __tablename__ = "content_tags"
    __table_args__ = (Index("ix_content_tags_tag_id", "tag_id"),)

    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
