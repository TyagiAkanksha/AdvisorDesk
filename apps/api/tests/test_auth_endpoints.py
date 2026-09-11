"""Failing endpoint tests for task-01 (Google OAuth, signed sessions, allowlist, require_admin).

PRD §5.1 (routes), §4.1 (users soft delete / reactivation), §9 (cookie +
allowlist rules). RED phase (CONVENTIONS.md §10): `app.auth`, `app.services.users`,
and `app.routes.auth_routes` do not exist yet, and `create_app` does not yet
accept an `oauth_client` param — every test here is expected to fail today
on those missing pieces, not on assertion logic. The fake OAuth client is
the ONLY mocked collaborator (CONVENTIONS.md §10: mock only the true
external seam); everything else goes through the real HTTP surface
(`TestClient`) and a real throwaway-schema Postgres DB (`tmp_engine`/
`db_session`, `conftest.py`).

DB-fixture tests (`tmp_engine`/`db_session`) skip cleanly when
`TEST_DATABASE_URL` is unset, per `conftest.py`'s skip-by-fixture-name hook;
`test_settings_repr_hides_secret_values` and
`test_login_redirects_to_fake_google_consent_url` are deliberately DB-less
and must run either way.
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.auth.state import mint_state
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User

# Phase-6 task-05 (PRD §9 OAuth state CSRF) — brief-pinned literal, not assumed to be an
# `app.auth.state` export, so defined locally (mirrors `tests/test_auth_hardening.py`).
_STATE_COOKIE_NAME = "advisordesk_oauth_state"


def _build_settings(admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
    )


def _build_client(
    tmp_engine: Engine, *, admin_emails: str = "admin@example.com"
) -> tuple[TestClient, FakeGoogleOAuthClient]:
    """Build a `TestClient` over a real DB-backed app with a fake OAuth seam injected.

    Mirrors `app/main.py`'s real wiring (`session_factory` from `app.db`)
    rather than a stub session, per CONVENTIONS.md §10 ("simulate actual
    usage, don't mock the interaction").
    """
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
        oauth_client=oauth_client,
    )
    return TestClient(app), oauth_client


def _fetch_user_by_email(engine: Engine, email: str) -> User | None:
    """Open a short-lived session against `engine` and return the `User` row for `email`, if any.

    Deliberately bypasses `active_select` (unlike app code) — these
    assertions need to see soft-deleted rows too. A fresh session (distinct
    from any fixture's `db_session`) avoids identity-map staleness when
    asserting on state the app under test mutated through its own, separate
    session.
    """
    session = make_session_factory(engine)()
    try:
        return session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    finally:
        session.close()


def _soft_delete_user_by_email(engine: Engine, email: str) -> None:
    """Flip `is_deleted` to `True` for `email` directly in the DB, bypassing the app entirely.

    Simulates an operator deactivating an admin mid-session — the PRD §9
    pin this module tests requires `require_admin` to notice on the very
    next request, not just at the moment of login.
    """
    session = make_session_factory(engine)()
    try:
        user = session.execute(select(User).where(User.email == email)).scalar_one()
        user.is_deleted = True
        session.commit()
    finally:
        session.close()


def test_settings_repr_hides_secret_values() -> None:
    """Interfaces block (Settings hardening): `session_secret`/`google_client_secret`/

    `nvidia_api_key` (phase-3 task-02: renamed from `openai_api_key`) become pydantic
    `SecretStr` — a naive `repr(Settings(...))` (e.g. via structured logging) must never leak
    them. DB-less: runs with no `TEST_DATABASE_URL`.
    """
    settings = Settings(
        session_secret="test-secret",
        google_client_secret="super-secret-google-value",
        nvidia_api_key="super-secret-nvidia-value",
        admin_emails="admin@example.com",
    )

    rendered = repr(settings)

    assert "test-secret" not in rendered
    assert "super-secret-google-value" not in rendered
    assert "super-secret-nvidia-value" not in rendered


def test_login_redirects_to_fake_google_consent_url() -> None:
    """PRD §5.1: `GET /auth/login` redirects (307) to the injected OAuth client's consent URL.

    DB-less: login never touches a session/DB row, only the injected fake seam.
    """
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(settings=_build_settings(), oauth_client=oauth_client)
    client = TestClient(app)

    response = client.get("/api/v1/auth/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith(oauth_client.consent_url)


def test_openapi_contains_auth_operation_ids() -> None:
    """Interfaces block: the four §5.1 auth routes carry exact, stable operation_ids."""
    schema = create_app(settings=_build_settings(), oauth_client=FakeGoogleOAuthClient()).openapi()

    operation_ids = {
        operation.get("operationId")
        for methods in schema["paths"].values()
        for operation in methods.values()
    }

    assert {"auth_login", "auth_callback", "auth_logout", "auth_me"} <= operation_ids


def test_callback_allowlisted_email_creates_user_and_sets_session_cookie(
    tmp_engine: Engine,
) -> None:
    """PRD §5.1 Step 1: an allowlisted email creates a `User` row and sets the session cookie."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")

    login_as(
        client, "admin@example.com", name="Ada Admin", avatar_url="https://example.com/ada.png"
    )

    assert len(client.cookies) >= 1
    user = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user is not None
    assert user.is_deleted is False
    assert user.name == "Ada Admin"
    assert user.avatar_url == "https://example.com/ada.png"


def test_callback_unlisted_email_redirects_to_signin_forbidden_and_no_row_created(
    tmp_engine: Engine,
) -> None:
    """PRD §5.1/§9 + phase-8 C0: an email outside `ADMIN_EMAILS` is rejected before any row write
    and lands on the admin sign-in page with `?error=forbidden`."""
    client, oauth_client = _build_client(tmp_engine, admin_emails="admin@example.com")
    code = "unlisted-code"
    oauth_client.identities[code] = {
        "email": "outsider@example.com",
        "name": "Outsider",
        "avatar_url": "https://example.com/outsider.png",
    }
    # Phase-6 task-05: a direct (non-login_as) callback call now needs a validly minted state
    # + matching double-submit cookie, or it answers a 303 to `/signin?error=state` on the state
    # check BEFORE ever reaching the allowlist check this test actually means to exercise.
    state = mint_state(client.app.state.settings)  # type: ignore[attr-defined]
    client.cookies.set(_STATE_COOKIE_NAME, state)

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3001/signin?error=forbidden"
    assert response.headers.get("set-cookie") is None
    assert _fetch_user_by_email(tmp_engine, "outsider@example.com") is None


def test_callback_reactivates_soft_deleted_allowlisted_user_same_id(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §4.1 pin: re-login of a soft-deleted allowlisted user reactivates the SAME row.

    Uniqueness-vs-soft-delete (§4.1): `users.email` upsert flips `is_deleted`
    back to `False` on the existing row id rather than inserting a duplicate.
    """
    existing = User(email="comeback@example.com", name="Old Name", is_deleted=True)
    db_session.add(existing)
    db_session.flush()
    existing_id = existing.id
    db_session.commit()

    client, _ = _build_client(tmp_engine, admin_emails="comeback@example.com")
    login_as(client, "comeback@example.com", name="New Name")

    user = _fetch_user_by_email(tmp_engine, "comeback@example.com")
    assert user is not None
    assert user.id == existing_id
    assert user.is_deleted is False
    assert user.name == "New Name"


def test_me_without_cookie_returns_401_envelope(tmp_engine: Engine) -> None:
    """PRD §5.1/§9: `GET /auth/me` without a session cookie is 401 with the standard envelope."""
    client, _ = _build_client(tmp_engine)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "auth_required"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_me_with_valid_cookie_returns_me_response(tmp_engine: Engine) -> None:
    """PRD §5.1: `GET /auth/me` with a valid session returns the `MeResponse` shape."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(
        client, "admin@example.com", name="Ada Admin", avatar_url="https://example.com/ada.png"
    )

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"id", "email", "name", "avatar_url"}
    assert body["email"] == "admin@example.com"
    assert body["name"] == "Ada Admin"
    assert body["avatar_url"] == "https://example.com/ada.png"
    user = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user is not None
    assert body["id"] == str(user.id)


def test_me_returns_401_after_session_user_soft_deleted_in_db(tmp_engine: Engine) -> None:
    """PRD §9 pin: a valid cookie for a soft-deleted session user is unauthenticated.

    `require_admin` must re-check `is_deleted` on every request, not just at
    login time — a signed cookie alone never re-authorizes a deactivated admin.
    """
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    assert client.get("/api/v1/auth/me").status_code == 200  # sanity: session works pre-flip

    _soft_delete_user_by_email(tmp_engine, "admin@example.com")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "auth_required"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_logout_clears_session_cookie(tmp_engine: Engine) -> None:
    """PRD §5.1: `POST /auth/logout` invalidates the session — `/auth/me` is 401 afterward."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    assert client.get("/api/v1/auth/me").status_code == 200  # sanity: session works pre-logout

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
