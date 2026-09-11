"""Engine and session-factory construction — the only place connection mechanics live.

`app.main` (CONVENTIONS.md §2) builds its engine through this module rather
than calling `sqlalchemy.create_engine` directly, and so does the Alembic
`env.py` and the test fixtures (CONVENTIONS.md §10) — one code path for how
AdvisorDesk talks to Postgres.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str, *, schema: str | None = None) -> Engine:
    """Build a SQLAlchemy engine, optionally pinned to a schema via search_path.

    A bare ``postgresql://`` URL is normalized to the ``postgresql+psycopg``
    dialect so the engine always talks to the database over psycopg (v3) —
    the driver this project depends on (no `psycopg2` installed).

    When `schema` is given, the engine's libpq startup options set
    `search_path=<schema>,public`. The `,public` fallback is required so the
    `vector` TYPE — installed once into `public` and never into per-test
    schemas (to avoid collisions between parallel test runs) — still
    resolves when connected with a non-public search_path.

    Args:
        database_url: a `postgresql://` (or already-qualified
            `postgresql+psycopg://`) URL.
        schema: when set, the schema to prefer on the connection search_path.

    Returns:
        A configured `Engine`. Callers own disposal.
    """
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")

    connect_args: dict[str, str] = {}
    if schema is not None:
        connect_args["options"] = f"-csearch_path={schema},public"

    # `pool_pre_ping=True`: two post-deploy 500s (`psycopg.OperationalError: SSL connection has
    # been closed unexpectedly`, mcp-oauth verification-record §5) came from stale pooled
    # connections after the DB side dropped idle SSL sessions; this pings (`SELECT 1`) and
    # transparently reconnects on checkout instead of handing back a dead connection.
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to `engine`.

    `expire_on_commit=False` so ORM instances stay usable (e.g. for response
    serialization) after the caller commits the transaction.

    Args:
        engine: the engine to bind sessions to.

    Returns:
        A `sessionmaker` producing `Session` objects bound to `engine`.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)
