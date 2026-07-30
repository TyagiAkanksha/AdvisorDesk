"""`app.routes.deps.get_session` direct coverage, DB-less (task-03 review F5).

Drives the real dependency through a `TestClient` app wired with a stub
session factory (records `commit`/`rollback`/`close` calls) rather than a
real `sessionmaker` — no database needed. Complements
`test_app_factory.py`'s existing error-envelope test, which never exercises
`get_session` at all.
"""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.factory import create_app
from app.routes.deps import get_session
from app.services.errors import NotFoundError


class _StubSession:
    """Records `commit`/`rollback`/`close` calls; backs no real database."""

    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def test_get_session_commits_and_closes_on_success() -> None:
    """A route that completes normally commits once, never rolls back, and closes."""
    stub_session = _StubSession()
    app = create_app(session_factory=cast(sessionmaker[Session], lambda: stub_session))
    probe_router = APIRouter()

    @probe_router.get("/_probe/ok", operation_id="probe_get_session_ok")
    def _ok(session: Session = Depends(get_session)) -> dict[str, str]:
        assert session is stub_session
        return {"status": "ok"}

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app)

    response = client.get("/api/v1/_probe/ok")

    assert response.status_code == 200
    assert stub_session.commit_calls == 1
    assert stub_session.rollback_calls == 0
    assert stub_session.close_calls == 1


def test_get_session_rolls_back_and_closes_on_error() -> None:
    """A route that raises rolls back, never commits, still closes, and hits the error handler."""
    stub_session = _StubSession()
    app = create_app(session_factory=cast(sessionmaker[Session], lambda: stub_session))
    probe_router = APIRouter()

    @probe_router.get("/_probe/fails", operation_id="probe_get_session_fails")
    def _fails(session: Session = Depends(get_session)) -> None:
        raise NotFoundError("widget not found")

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/_probe/fails")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "widget not found"}}
    assert stub_session.commit_calls == 0
    assert stub_session.rollback_calls == 1
    assert stub_session.close_calls == 1


def test_get_session_without_factory_raises_runtime_error() -> None:
    """`create_app()` with no `session_factory` fails loudly, not silently, at request time."""
    app = create_app()
    probe_router = APIRouter()

    @probe_router.get("/_probe/needs-session", operation_id="probe_get_session_no_factory")
    def _needs_session(session: Session = Depends(get_session)) -> dict[str, str]:
        return {"status": "ok"}  # pragma: no cover - never reached

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app)

    with pytest.raises(RuntimeError, match="get_session"):
        client.get("/api/v1/_probe/needs-session")
