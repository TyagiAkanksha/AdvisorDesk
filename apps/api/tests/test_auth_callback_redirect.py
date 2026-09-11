"""Callback landing amendment (phase-2 task-01 review M8 resolution, pre-task-04).

`GET /auth/callback` on success now sets the session cookie and responds
`303 See Other` to `settings.admin_app_url` instead of a bodyless 200 —
otherwise the browser dead-ends on the API's own origin after Google
sign-in. `tests/auth_helpers.py` and `tests/test_auth_endpoints.py` are the
test-author's pinned files and are not touched here (CONVENTIONS.md §10) —
this module follows `tests/test_auth_security.py`'s established pattern for
extending auth coverage: its own local `Settings`/`TestClient` builders,
importing only `FakeGoogleOAuthClient` and `login_as` from `auth_helpers`.
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.auth.sessions import COOKIE_NAME
from app.auth.state import mint_state
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app

_CALLBACK_PATH = "/api/v1/auth/callback"
_ME_PATH = "/api/v1/auth/me"
_ADMIN_APP_URL = "http://localhost:3001"

# Phase-6 task-05 (PRD §9 OAuth state CSRF) — brief-pinned literal, not assumed to be an
# `app.auth.state` export, so defined locally (mirrors `tests/test_auth_hardening.py`).
_STATE_COOKIE_NAME = "advisordesk_oauth_state"


def _build_settings(*, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        admin_app_url=_ADMIN_APP_URL,
    )


def _build_client(
    tmp_engine: Engine, *, admin_emails: str = "admin@example.com"
) -> tuple[TestClient, FakeGoogleOAuthClient]:
    """Build a `TestClient` over a real DB-backed app with a fake OAuth seam injected.

    Mirrors `tests/test_auth_endpoints.py::_build_client` (kept local here
    rather than imported, since that module is the test-author's pinned
    file and is not a shared-helper module — same precedent
    `tests/test_auth_security.py` follows).
    """
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
        oauth_client=oauth_client,
    )
    return TestClient(app), oauth_client


def test_callback_success_redirects_303_to_admin_app_url_with_cookie_set(
    tmp_engine: Engine,
) -> None:
    """Success: 303 to `settings.admin_app_url`, session cookie set on the SAME response."""
    client, oauth_client = _build_client(tmp_engine)
    code = "redirect-success-code"
    oauth_client.identities[code] = {
        "email": "admin@example.com",
        "name": "Ada Admin",
        "avatar_url": None,
    }
    # Phase-6 task-05: a direct (non-login_as) callback call needs a validly minted state +
    # matching double-submit cookie, or it 403s on the state check before ever reaching here.
    state = mint_state(client.app.state.settings)  # type: ignore[attr-defined]
    client.cookies.set(_STATE_COOKIE_NAME, state)

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": state}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == _ADMIN_APP_URL
    # CHANGED (phase-6 task-05): a successful callback now emits a SECOND Set-Cookie header
    # too — deleting the now-consumed oauth state cookie (Interfaces §ii: "On success, delete
    # the state cookie on the redirect response") — so a bare "is not None" check would still
    # pass even if session-cookie issuance itself regressed, since the state-deletion header
    # alone satisfies it. `get_list` + a name-prefix match pins the SESSION cookie specifically.
    set_cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith(f"{COOKIE_NAME}=") for c in set_cookies)


def test_callback_unlisted_email_redirects_303_to_signin_forbidden_with_no_cookie(
    tmp_engine: Engine,
) -> None:
    """Phase-8 C0: an allowlist failure lands on the admin sign-in page, never a JSON 403."""
    client, oauth_client = _build_client(tmp_engine)
    code = "redirect-unlisted-code"
    oauth_client.identities[code] = {
        "email": "outsider@example.com",
        "name": "Outsider",
        "avatar_url": None,
    }
    state = mint_state(client.app.state.settings)  # type: ignore[attr-defined]
    client.cookies.set(_STATE_COOKIE_NAME, state)

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": state}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"{_ADMIN_APP_URL}/signin?error=forbidden"
    assert response.headers.get("set-cookie") is None


def test_callback_failure_redirect_never_carries_the_email(tmp_engine: Engine) -> None:
    """The rejected address must not leak into the URL (it is logged at WARNING only)."""
    client, oauth_client = _build_client(tmp_engine)
    code = "redirect-unlisted-code-2"
    oauth_client.identities[code] = {
        "email": "outsider@example.com",
        "name": "Outsider",
        "avatar_url": None,
    }
    state = mint_state(client.app.state.settings)  # type: ignore[attr-defined]
    client.cookies.set(_STATE_COOKIE_NAME, state)

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": state}, follow_redirects=False
    )

    assert "outsider" not in response.headers["location"]
    assert "example.com" not in response.headers["location"]


def test_login_as_helper_still_lands_a_usable_session_despite_the_303(
    tmp_engine: Engine,
) -> None:
    """`login_as` (used by every later admin-route test) still works after the 303 change.

    `login_as` calls `/auth/callback` with `follow_redirects=False`
    (`tests/auth_helpers.py`), so `TestClient`'s default redirect-following
    behavior never sends it chasing `settings.admin_app_url`
    (`http://localhost:3001`, off the test app entirely, unreachable from
    the test process). The session cookie the 303 response carries lands in
    the client's cookie jar regardless of whether the redirect is followed
    — cookie processing happens before redirect-following ever kicks in —
    so the whole rest of the authored test suite (every later admin-route
    test built on `login_as`) stays green.
    """
    client, _ = _build_client(tmp_engine)

    login_as(client, "admin@example.com")

    assert client.get(_ME_PATH).status_code == 200
