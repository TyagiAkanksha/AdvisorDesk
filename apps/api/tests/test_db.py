"""Pins `app.db.make_engine`'s pool configuration (chore-2026-09 closeout item 1).

Two post-deploy 500s (`psycopg.OperationalError: SSL connection has been closed unexpectedly`,
mcp-oauth verification-record §5) traced back to stale pooled connections after the DB side
dropped idle SSL sessions. `pool_pre_ping=True` issues a cheap `SELECT 1` on checkout and
transparently reconnects instead of handing the caller a connection that fails on first use.

Deliberately DB-less, same idiom as `tests/test_main_guard.py`: `make_engine` only builds a
SQLAlchemy `Engine` object (lazy — no connection attempt), so a syntactically valid but
unreachable `DATABASE_URL` is enough to inspect the engine's pool configuration.
"""

from __future__ import annotations

from app.db import make_engine

_DUMMY_URL = "postgresql://user:pass@localhost:5432/advisordesk_dummy"


def test_make_engine_enables_pool_pre_ping() -> None:
    """`make_engine` builds its engine with `pool_pre_ping=True` — SQLAlchemy 2.x exposes this as
    `engine.pool._pre_ping` (there is no public accessor). Without it, a connection the DB side
    already dropped (an idle SSL session closed server-side) is handed back to the caller as-is
    and fails on first use instead of being pinged-and-replaced transparently on checkout.
    """
    engine = make_engine(_DUMMY_URL)

    assert engine.pool._pre_ping is True
