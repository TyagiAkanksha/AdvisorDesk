"""Cookie security properties + email-normalization pins (phase-2 task-01 review round 1).

Findings I2 (cookie `HttpOnly`/`SameSite`/`Secure` flags were untested) and
I3 (the callback normalized email for the allowlist check but passed the
RAW, differently-cased identity into `upsert_from_google`, splitting one
admin's identity across two rows). `tests/auth_helpers.py` and
`tests/test_auth_endpoints.py` are the test-author's pinned files and are
not touched here — this module follows the same fake-OAuth-seam pattern
(CONVENTIONS.md §10: mock only the true external seam) with its own local
`Settings`/`TestClient` builders, importing only `FakeGoogleOAuthClient` and
`login_as` from `auth_helpers`.
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAME
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User

_CALLBACK_PATH = "/api/v1/auth/callback"
_ME_PATH = "/api/v1/auth/me"


def _build_settings(
    *, environment: str = "development", admin_emails: str = "admin@example.com"
) -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        environment=environment,
    )


def _build_client(
    tmp_engine: Engine, *, environment: str = "development", admin_emails: str = "admin@example.com"
) -> tuple[TestClient, FakeGoogleOAuthClient]:
    """Build a `TestClient` over a real DB-backed app with a fake OAuth seam injected.

    Mirrors `tests/test_auth_endpoints.py::_build_client` (kept local here
    rather than imported, since that module is the test-author's pinned
    file and is not a shared-helper module).
    """
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(environment=environment, admin_emails=admin_emails),
        oauth_client=oauth_client,
    )
    return TestClient(app), oauth_client


def _count_users(engine: Engine) -> int:
    """Return the total row count of `users` (test-only introspection, bypasses `active_select`)."""
    session: Session = make_session_factory(engine)()
    try:
        return session.execute(select(func.count()).select_from(User)).scalar_one()
    finally:
        session.close()


def _fetch_user_by_email(engine: Engine, email: str) -> User | None:
    """Open a short-lived session and return the `User` row for the exact `email` given."""
    session: Session = make_session_factory(engine)()
    try:
        return session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# I2 — cookie security properties
# ---------------------------------------------------------------------------


def test_callback_sets_httponly_lax_non_secure_cookie_in_development(tmp_engine: Engine) -> None:
    """Dev (`ENVIRONMENT=development`, the default): `HttpOnly` + `SameSite=lax`, no `Secure`.

    A plain-HTTP local dev server (and the test suite's `TestClient`) still
    needs the cookie to round-trip, so `Secure` must be absent here (PRD §9 /
    task-01 brief: "Secure when not dev").
    """
    client, oauth_client = _build_client(tmp_engine, environment="development")
    code = "dev-cookie-code"
    oauth_client.identities[code] = {
        "email": "admin@example.com",
        "name": "Ada Admin",
        "avatar_url": None,
    }

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": "test-state"}, follow_redirects=False
    )

    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    assert set_cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie


def test_callback_sets_secure_cookie_in_production(tmp_engine: Engine) -> None:
    """Prod (`ENVIRONMENT=production`): the session cookie carries `Secure` too."""
    client, oauth_client = _build_client(tmp_engine, environment="production")
    code = "prod-cookie-code"
    oauth_client.identities[code] = {
        "email": "admin@example.com",
        "name": "Ada Admin",
        "avatar_url": None,
    }

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": "test-state"}, follow_redirects=False
    )

    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" in set_cookie


def test_me_returns_401_when_cookie_is_a_plaintext_user_id(tmp_engine: Engine) -> None:
    """A forged cookie holding a raw (unsigned) user id must not authenticate.

    `read_user_id` (`app.auth.sessions`) requires an `itsdangerous`-signed
    token; a plaintext value fails signature verification exactly like a
    tampered one, so `/auth/me` must 401 rather than trust it.
    """
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    assert client.get(_ME_PATH).status_code == 200  # sanity: the real session works first

    user = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user is not None
    client.cookies.set(COOKIE_NAME, str(user.id))  # plaintext id, no itsdangerous signature

    response = client.get(_ME_PATH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_me_returns_401_when_signed_cookie_is_tampered(tmp_engine: Engine) -> None:
    """Flipping a character in an otherwise-valid signed cookie must invalidate it.

    Proves `itsdangerous` signature verification is actually wired up end to
    end through the real HTTP surface, not just unit-tested in isolation.
    """
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    assert client.get(_ME_PATH).status_code == 200  # sanity: the real session works first

    valid_token = client.cookies.get(COOKIE_NAME)
    assert valid_token
    tampered_token = valid_token[:-1] + ("a" if valid_token[-1] != "a" else "b")
    client.cookies.set(COOKIE_NAME, tampered_token)

    response = client.get(_ME_PATH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


# ---------------------------------------------------------------------------
# I3 — email normalization
# ---------------------------------------------------------------------------


def test_callback_normalizes_mixed_case_email_to_single_lowercase_row(tmp_engine: Engine) -> None:
    """Login as `'Admin@Example.com'` against a lowercase allowlist creates exactly one row.

    Before the fix, the allowlist check normalized the email but the raw,
    mixed-case identity was passed into `upsert_from_google`, so the stored
    `users.email` was `'Admin@Example.com'` rather than the lowercase form —
    and a second login with different casing would insert a SECOND row
    (`users.email` has no case-insensitive uniqueness at the DB level).
    """
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")

    login_as(client, "Admin@Example.com", name="Ada Admin")

    user = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user is not None
    assert user.email == "admin@example.com"
    assert _count_users(tmp_engine) == 1


def test_second_login_with_different_casing_reuses_the_same_row(tmp_engine: Engine) -> None:
    """A second login under yet another casing must land on the SAME row, not a new one."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "Admin@Example.com", name="Ada Admin")
    first = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert first is not None

    login_as(client, "ADMIN@EXAMPLE.COM", name="Ada Admin (renamed)")

    second = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert second is not None
    assert second.id == first.id
    assert second.name == "Ada Admin (renamed)"
    assert _count_users(tmp_engine) == 1
