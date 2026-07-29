"""Alembic environment: targets `Base.metadata`, honors the test-schema convention.

CONVENTIONS.md §6: Alembic is the only DDL path — no `create_all()` at
startup. The database URL comes from `DATABASE_URL` (production) or
`TEST_DATABASE_URL` (tests), falling back to `alembic.ini`'s
`sqlalchemy.url` only if neither is set. When `MIGRATE_SCHEMA` is set (the
test fixtures, CONVENTIONS.md §10), migrations run against that schema via
`app.db.make_engine`'s search_path mechanism, and Alembic's own
`alembic_version` bookkeeping table is created in that same schema so
parallel test runs never collide.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from app.db import make_engine
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `app.models` (imported above) registers every PRD §4 table on this metadata.
target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the database URL: `DATABASE_URL`, then `TEST_DATABASE_URL`, then the ini fallback."""
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("TEST_DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
        or ""
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: emit SQL without a live DB connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=os.environ.get("MIGRATE_SCHEMA"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection.

    Builds the engine through `app.db.make_engine` so `MIGRATE_SCHEMA` (set
    by the test fixtures) pins the connection's search_path exactly the way
    production code would — and pins Alembic's `alembic_version` table to
    that same schema via `version_table_schema`.
    """
    schema = os.environ.get("MIGRATE_SCHEMA")
    connectable = make_engine(_database_url(), schema=schema)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=schema,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
