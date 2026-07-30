"""`User` ORM model — content managers/advisors (PRD §4 `users`)."""

from __future__ import annotations

import uuid

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin, uuid_pk


class User(Base, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin):
    """A content manager / advisor account.

    Populated on first allowlisted Google OAuth login (PRD §5.1). Soft-delete
    reactivation of a matching email on re-login is a service-layer concern
    (PRD §4.1) — not modeled here.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
