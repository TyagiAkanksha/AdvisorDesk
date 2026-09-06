"""`User` ORM model — content managers/advisors (PRD §4 `users`)."""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, Text
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
    # Server-side session revocation counter (PRD §9; phase-6 task-05). Bumped by
    # `app.services.users.bump_session_epoch` on `/auth/logout` — every outstanding session
    # cookie was signed with the epoch value in effect at issuance
    # (`app.auth.sessions.issue_cookie`), so once this row moves to N+1, `require_admin`
    # rejects any cookie still carrying N, even a captured/stolen one, without needing a
    # server-side session store. `default=0` (client-side) mirrors `server_default="0"` so a
    # freshly-flushed row reads `0` immediately, not only after a round trip to the DB.
    session_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
