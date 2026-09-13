"""Failing (RED) route tests for the read-only weak-queries admin route (phase-9 task-19).

Task brief: docs/plans/phase-9-eval-data-loop/task-19-weak-queries-card.md, Steps (TDD) step 1.
`app.routes.weak_queries_routes` and `app.models.schemas.weak_queries` do not exist yet, and the
route is not mounted in `app.factory.create_app` — every request to `GET /api/v1/weak-queries`
below 404s (the router simply isn't there yet), not because of any assertion logic against a
working implementation. That 404 IS the RED evidence this file exists to produce.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL` is
set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`) — every test here requests `tmp_engine`, so
the whole module skips cleanly without a DB.

`_build_settings`/`_build_client` are a minimal copy of `tests/test_routes_content.py`'s own
helpers (no `chunk_pipeline`/`RecordingChunkPipeline` — this route never touches content
chunking, so there is nothing for a recording fake to observe). `_ask` is a minimal copy of
`tests/test_weak_queries.py::_ask` (no `content` parameter — decline detection is already pinned
at the service layer in that file; every seed below uses the neutral default answer text).

Seeding uses a SEPARATE, explicitly-committed `Session` (not the app's own request-scoped one
`_build_client`'s `TestClient` uses per request) — `_ask`'s `session.flush()` alone makes rows
visible only within that same session/transaction, and the `TestClient`'s request runs on a
different `Session` from a different connection, so the seed session must `commit()` before the
route is hit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import ChatMessage, ChatSession
from app.services.chat import NEGATIVE_FEEDBACK

_EXAMPLE_FIELDS = {"question", "kind", "top_similarity", "asked_at"}
_GROUP_FIELDS = {"normalized_question", "count", "kinds", "worst_top_similarity", "examples"}
_RESPONSE_FIELDS = {"threshold", "days", "count", "items"}


def _build_settings() -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10).

    Minimal copy of `tests/test_routes_content.py::_build_settings` — this file's tests never
    need to vary `admin_emails`, so that parameter is dropped.
    """
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails="admin@example.com",
    )


def _build_client(tmp_engine: Engine) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with fake OAuth.

    Minimal copy of `tests/test_routes_content.py::_build_client` — no `chunk_pipeline` (and so
    no `RecordingChunkPipeline`/tuple return): this route calls `weak_queries` only, never the
    chunking pipeline.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )
    return TestClient(app)


def _ask(
    session: Session,
    question: str,
    *,
    found: bool | None,
    top_similarity: float | None,
    feedback: int | None = None,
    ago: timedelta = timedelta(minutes=1),
) -> None:
    """Seed one user question + its next assistant reply, asked `ago` before now.

    Minimal copy of `tests/test_weak_queries.py::_ask` — no `content` parameter (these route
    tests never exercise decline detection, already pinned at the service layer in that file;
    every row here gets the same neutral placeholder answer text).
    """
    chat_session = ChatSession()
    session.add(chat_session)
    session.flush()
    asked_at = datetime.now(UTC) - ago
    session.add(
        ChatMessage(session_id=chat_session.id, role="user", content=question, created_at=asked_at)
    )
    session.add(
        ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content="reply",
            created_at=asked_at + timedelta(seconds=1),
            citations=[],
            retrieval_found=found,
            top_similarity=top_similarity,
            feedback=feedback,
        )
    )
    session.flush()


def test_weak_queries_get_requires_admin_session(tmp_engine: Engine) -> None:
    """PRD §9: `GET /api/v1/weak-queries` 401s with `{"error":{"code":"auth_required",...}}`
    without a session — same envelope every other admin route uses."""
    client = _build_client(tmp_engine)

    response = client.get("/api/v1/weak-queries")

    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"]["code"] == "auth_required"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_weak_queries_get_returns_groups_in_service_shape(tmp_engine: Engine) -> None:
    """The response mirrors `weak_queries`' own classification precedence table: one 👎, one
    refused, one near-miss, and a confidently-answered pair that must NOT appear."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    session = make_session_factory(tmp_engine)()
    _ask(session, "Does the firm cover crypto RSUs?", found=True, top_similarity=0.6, feedback=-1)
    _ask(session, "Anything on QSBS?", found=False, top_similarity=0.2)
    _ask(session, "Do RSUs work differently outside the US?", found=False, top_similarity=0.45)
    _ask(session, "When do my RSUs vest?", found=True, top_similarity=0.8)
    session.commit()
    session.close()

    response = client.get("/api/v1/weak-queries")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == _RESPONSE_FIELDS
    assert body["days"] == 7
    assert body["threshold"] == pytest.approx(0.5)
    assert body["count"] == 3
    items = body["items"]
    assert len(items) == 3
    for item in items:
        assert set(item) == _GROUP_FIELDS
        for example in item["examples"]:
            assert set(example) == _EXAMPLE_FIELDS
            datetime.fromisoformat(example["asked_at"])  # must parse as ISO-8601

    by_question = {item["normalized_question"]: item for item in items}
    assert "when do my rsus vest" not in by_question
    assert by_question["does the firm cover crypto rsus"]["kinds"] == [NEGATIVE_FEEDBACK]


def test_weak_queries_get_days_window_and_limit_apply(tmp_engine: Engine) -> None:
    """`days` windows on when the question was asked; `limit` caps GROUPS, not rows."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    session = make_session_factory(tmp_engine)()
    _ask(session, "Old refused question?", found=False, top_similarity=0.2, ago=timedelta(days=10))
    session.commit()

    default_response = client.get("/api/v1/weak-queries")
    assert default_response.status_code == 200, default_response.text
    assert default_response.json()["count"] == 0

    wide_response = client.get("/api/v1/weak-queries", params={"days": 30})
    assert wide_response.status_code == 200, wide_response.text
    assert wide_response.json()["count"] == 1

    _ask(session, "Second weak question?", found=False, top_similarity=0.2)
    _ask(session, "Third weak question?", found=False, top_similarity=0.2)
    session.commit()
    session.close()

    limited_response = client.get("/api/v1/weak-queries", params={"days": 30, "limit": 2})
    assert limited_response.status_code == 200, limited_response.text
    assert limited_response.json()["count"] == 2


def test_weak_queries_get_rejects_out_of_range_params(tmp_engine: Engine) -> None:
    """Out-of-range `days`/`limit` 422 with the standard validation-error envelope (same `code`
    the pre-existing pin in `test_routes_content.py:484` asserts)."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    for params in ({"days": 0}, {"days": 91}, {"limit": 0}, {"limit": 101}):
        response = client.get("/api/v1/weak-queries", params=params)

        assert response.status_code == 422, f"{params}: {response.status_code} {response.text}"
        body = response.json()
        assert body["error"]["code"] == "validation_error"
