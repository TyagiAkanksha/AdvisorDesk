"""§9 smoke test: boot the real app, log in, hit `/api/v1/stats` (task-03 Step 5).

PRD §9 ("Tests (minimum)"): "a smoke test that boots the API and hits
`/api/v1/stats`". This is deliberately minimal and independent of
`test_routes_content.py` (unique test-file basenames, CONVENTIONS.md §10) —
the standing "does the whole app boot and answer one authenticated request"
gate, not a full CRUD/route-behavior suite. RED phase: `GET /api/v1/stats`
does not exist yet (`app.routes.content_routes` is not created until this
task's implementer step), so this 404s today rather than passing.
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app


def _build_settings() -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails="admin@example.com",
    )


def test_smoke_boots_app_logs_in_and_stats_returns_by_status(tmp_engine: Engine) -> None:
    """Boot `create_app` with a real session factory + fake OAuth, log in, `GET /api/v1/stats`.

    Creates one draft `Content` row through the real `/api/v1/content` route
    first, so `by_status` is observably populated rather than trivially
    empty on a fresh schema — the point of the §9 smoke test is proving an
    authenticated request flows end to end through the real app (routing,
    auth, DB, DTOs), not merely that an empty dict comes back. The brief
    names no exact response body beyond "`by_status` keys" so this is a
    resolved implementation choice (PRD implementer contract §11: simplest
    behavior consistent with the brief), recorded here rather than left
    ambiguous.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )
    client = TestClient(app)
    login_as(client, "admin@example.com")
    create_response = client.post(
        "/api/v1/content", json={"title": "Smoke Test Item", "body_md": "", "tags": []}
    )
    assert create_response.status_code == 201, create_response.text

    response = client.get("/api/v1/stats")

    assert response.status_code == 200
    body = response.json()
    assert "by_status" in body
    assert body["by_status"].get("draft") == 1
