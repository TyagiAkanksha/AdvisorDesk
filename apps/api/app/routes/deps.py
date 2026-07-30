"""Request-scoped dependencies backing every route: DB session and settings.

CONVENTIONS.md §5: all shared state lives on `app.state`; routes read it
back through these dependencies rather than holding module-level globals.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session

from app.auth.oauth import GoogleOAuthClient
from app.config import Settings


def get_session(request: Request) -> Iterator[Session]:
    """Yield a `Session` for one request; commit on success, rollback on error, always close.

    CONVENTIONS.md §3/§5: the transaction boundary belongs to the HTTP
    layer — services `flush()` but never `commit()`/`rollback()`
    themselves. Reads `request.app.state.session_factory`, set by
    `create_app`/`app/main.py`.

    Raises:
        RuntimeError: if the app was built without a session factory (a
            DB-less `create_app()`, e.g. for the OpenAPI export or
            config-only tests) — a route depending on `get_session` must
            fail loudly rather than silently operating on no database.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "get_session() requires app.state.session_factory, but none was "
            "configured — this app was built by create_app() without a "
            "session_factory (DB-less mode). Only app/main.py wires a real one."
        )

    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    """Return the `Settings` instance `create_app` stored on `app.state`."""
    return cast(Settings, request.app.state.settings)


def get_oauth_client(request: Request) -> GoogleOAuthClient:
    """Return the `GoogleOAuthClient` `create_app` stored on `app.state` (PRD §5.1).

    `None` (a `create_app()` built without an `oauth_client`, e.g. the
    OpenAPI baseline export) is never dereferenced here — only routes that
    actually call a method on the returned client would fail, and no
    DB-less/schema-only caller does that.
    """
    return cast(GoogleOAuthClient, request.app.state.oauth_client)
