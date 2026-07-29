"""Declarative base and shared column/mixin helpers for all ORM models.

PRD §4.1: every table gets a `uuid` primary key via `gen_random_uuid()`; every
table carries `created_at`; the three mutable tables (`users`, `content`,
`tags`) also carry `updated_at`; soft delete (`is_deleted`) is scoped to
those same three tables. Append-only/derived tables (`content_tags`,
`chunks`, `chat_sessions`, `chat_messages`) compose only `TimestampMixin`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# A conventional Alembic naming scheme so autogenerate diffs stay stable and
# every constraint/index gets a deterministic name (the four §4.1 FK/HNSW
# indexes are still given explicit names in the migration itself).
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base for every AdvisorDesk ORM model.

    Tables carry no explicit ``schema=`` so they create into whatever schema
    is first on the connection's search_path — the throwaway test schema, or
    ``public`` in production (see `app.db.make_engine`).
    """

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """Shared primary-key column: a server-generated UUID (PRD §4.1).

    Uses Postgres's built-in `gen_random_uuid()` (13+) — no `pgcrypto`
    extension required.
    """
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """`created_at` — every table carries this (PRD §4.1).

    `timestamptz not null default now()`, set once at insert.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class UpdatedAtMixin:
    """`updated_at` — mutable tables only (PRD §4.1: `users`/`content`/`tags`).

    `timestamptz not null default now()`. Maintained by the application
    (service) layer on every write, per CONVENTIONS.md §3 — no DB trigger or
    `onupdate=`.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SoftDeleteMixin:
    """`is_deleted` — scoped to `users`/`content`/`tags` only (PRD §4.1).

    Deleted rows are DB-level tombstones: no restore endpoint/UI/tool exists
    (PRD §4.1, §12). Every read of a model mixing this in must go through
    `app.services.queries.active_select` rather than an ad-hoc filter.
    """

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
