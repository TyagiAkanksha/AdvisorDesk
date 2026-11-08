"""The session-cookie path re-checks the LIVE `ADMIN_EMAILS` allowlist on every request.

Found by an agent-review design review: the bearer path (`resolve_bearer_token`) already
re-checked the allowlist on every MCP call, but `resolve_admin` (the cookie path used by the
admin app, `/agent/chat` and cookie-authenticated MCP calls) only checked it at login. A cookie
lives for days, so removing someone from `ADMIN_EMAILS` did not end their session until it
expired or their epoch was bumped.

Real DB-backed app through `TestClient`; the fake OAuth client is the only mocked seam
(CONVENTIONS.md §10). The allowlist change is applied by swapping `app.state.settings`, which
is exactly the object `resolve_admin` reads on each request.
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app

_ME_PATH = "/api/v1/auth/me"


def _settings(admin_emails: str) -> Settings:
    """Explicit test `Settings`; never reads the real `.env` (CONVENTIONS.md §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        environment="development",
    )


def _client(tmp_engine: Engine, admin_emails: str) -> TestClient:
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_settings(admin_emails),
        oauth_client=FakeGoogleOAuthClient(),
    )
    return TestClient(app)


def test_removing_an_admin_from_the_allowlist_ends_their_cookie_session(
    tmp_engine: Engine,
) -> None:
    """A live cookie stops working on the very next request after its owner is de-listed."""
    client = _client(tmp_engine, "admin@example.com,second@example.com")
    login_as(client, "second@example.com")
    assert client.get(_ME_PATH).status_code == 200  # sanity: the session works

    client.app.state.settings = _settings("admin@example.com")  # type: ignore[attr-defined]

    response = client.get(_ME_PATH)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_allowlist_recheck_is_case_and_whitespace_insensitive(tmp_engine: Engine) -> None:
    """The re-check normalizes like login and the bearer path, so a still-listed admin stays in."""
    client = _client(tmp_engine, "admin@example.com")
    login_as(client, "admin@example.com")

    client.app.state.settings = _settings("  ADMIN@Example.com  ")  # type: ignore[attr-defined]

    assert client.get(_ME_PATH).status_code == 200


def test_re_adding_a_removed_admin_restores_access_with_the_same_cookie(
    tmp_engine: Engine,
) -> None:
    """The check reads the live allowlist each time; it does not permanently revoke the cookie."""
    client = _client(tmp_engine, "admin@example.com,second@example.com")
    login_as(client, "second@example.com")

    client.app.state.settings = _settings("admin@example.com")  # type: ignore[attr-defined]
    assert client.get(_ME_PATH).status_code == 401

    client.app.state.settings = _settings(  # type: ignore[attr-defined]
        "admin@example.com,second@example.com"
    )
    assert client.get(_ME_PATH).status_code == 200
