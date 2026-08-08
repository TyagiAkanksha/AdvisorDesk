"""Failing tests for phase-6 task-05 (auth hardening: logout revocation + OAuth state CSRF).

PRD §9 auth security; phase-2 ledgered findings t01-M6 (logout does not revoke) and t01-M7
(OAuth state not verified), owner-ratified for pre-deploy fix 2026-08-08
(`docs/plans/phase-6-deployment/task-05-auth-hardening.md`).

RED phase (CONVENTIONS.md §10): `app.auth.state` does not exist yet; `app.auth.sessions`
still carries a bare-`str(user_id)` cookie payload with no `read_session`/`bump_session_epoch`
wiring; `users.session_epoch` has no column/migration. Every test here is expected to fail
today on those missing pieces, not on assertion logic.

Two behaviors are pinned:

1. **Logout revocation** — `POST /auth/logout` best-effort-bumps `users.session_epoch` for the
   cookie's owner, so a captured/stolen cookie signed at the old epoch is dead the instant the
   row moves to the new one — not just "cleared from this one browser's jar." Logout itself
   stays idempotent-200 regardless of whether a cookie was present or valid.
2. **OAuth state CSRF** — `/auth/login` mints a signed, timestamped `state` and sets it as a
   double-submit cookie (`advisordesk_oauth_state`); `/auth/callback` requires BOTH a valid
   signature/age AND an exact match against that cookie before it will exchange `code` with
   Google at all.

The fake OAuth client is the ONLY mocked collaborator (CONVENTIONS.md §10: mock only the true
external seam); everything else goes through the real HTTP surface (`TestClient`) and a real
throwaway-schema Postgres DB (`tmp_engine`/`db_session`, `conftest.py`), except the three
`app.auth.state` unit tests, which are DB-less by design (pure function, no HTTP needed).
"""

from __future__ import annotations

import time
import urllib.parse

import pytest
import sqlalchemy as sa
from app.auth.state import mint_state, verify_state
from auth_helpers import FakeGoogleOAuthClient, begin_login, login_as
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAME
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User

_CALLBACK_PATH = "/api/v1/auth/callback"
_LOGIN_PATH = "/api/v1/auth/login"
_LOGOUT_PATH = "/api/v1/auth/logout"
_ME_PATH = "/api/v1/auth/me"

# Brief-pinned literal (Interfaces §ii) — not assumed to be an `app.auth.state` export, so it
# is defined locally rather than imported (see the test-author report's interface-assumptions
# section).
_STATE_COOKIE_NAME = "advisordesk_oauth_state"

# Mirrors `app.auth.sessions`' existing (pre-task-05) `_SALT` constant — used verbatim, not
# imported (it is private), to hand-construct legacy/malformed session-cookie fixtures below.
_LEGACY_SESSION_SALT = "advisordesk.auth.session"


def _build_settings(
    *, admin_emails: str = "admin@example.com", environment: str = "development"
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
    tmp_engine: Engine,
    *,
    admin_emails: str = "admin@example.com",
    environment: str = "development",
) -> tuple[TestClient, FakeGoogleOAuthClient]:
    """Build a `TestClient` over a real DB-backed app with a fake OAuth seam injected.

    Mirrors `tests/test_auth_endpoints.py::_build_client` (kept local here rather than
    imported — that module is a test-author-pinned file, not a shared-helper module, same
    precedent `tests/test_auth_security.py`/`tests/test_auth_callback_redirect.py` follow).
    """
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails, environment=environment),
        oauth_client=oauth_client,
    )
    return TestClient(app), oauth_client


def _fetch_user_by_email(engine: Engine, email: str) -> User | None:
    """Open a short-lived session and return the `User` row for the exact `email` given."""
    session = make_session_factory(engine)()
    try:
        return session.execute(sa.select(User).where(User.email == email)).scalar_one_or_none()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# app.auth.state — direct unit tests (DB-less; pure functions)
# ---------------------------------------------------------------------------


def test_verify_state_accepts_a_freshly_minted_state() -> None:
    """`verify_state` accepts what `mint_state` just produced (Interfaces §ii pin)."""
    settings = _build_settings()

    state = mint_state(settings)

    assert verify_state(state, settings) is True


def test_verify_state_rejects_an_unsigned_garbage_string() -> None:
    """A value `mint_state` never produced fails signature verification."""
    settings = _build_settings()

    assert verify_state("not-a-real-signed-state-token", settings) is False


def test_verify_state_never_raises_on_pathological_input() -> None:
    """The never-raises contract (Interfaces §ii pin) holds for a degenerate empty string."""
    settings = _build_settings()

    assert verify_state("", settings) is False


# ---------------------------------------------------------------------------
# Migration 0004 pin — users.session_epoch
# ---------------------------------------------------------------------------


def test_users_table_has_session_epoch_integer_not_null_default_zero(tmp_engine: Engine) -> None:
    """Migration 0004 pin: `users.session_epoch` exists, integer, not null, server default 0."""
    inspector = sa.inspect(tmp_engine)
    columns = {column["name"]: column for column in inspector.get_columns("users")}

    assert "session_epoch" in columns
    session_epoch = columns["session_epoch"]
    assert session_epoch["nullable"] is False
    assert session_epoch["default"] is not None
    assert "0" in str(session_epoch["default"])


def test_new_user_row_gets_session_epoch_zero_by_default(db_session: Session) -> None:
    """A freshly inserted `User` row starts at `session_epoch == 0` with no explicit value."""
    user = User(email="epoch-default@example.com")
    db_session.add(user)
    db_session.flush()

    assert user.session_epoch == 0


# ---------------------------------------------------------------------------
# Logout revocation — users.session_epoch bump
# ---------------------------------------------------------------------------


def test_logout_revokes_session_replaying_the_captured_cookie_returns_401(
    tmp_engine: Engine,
) -> None:
    """The core acceptance pin: a cookie signed at epoch N is dead once the row moves to N+1.

    Captures the REAL, live session cookie value right after login, logs out (which bumps
    `users.session_epoch`), then manually replays the CAPTURED (stale) cookie — simulating a
    stolen cookie — and proves it no longer authenticates. Epochs are not forgeable
    client-side: the signature covers them, so this is not merely "the client's cookie jar got
    cleared" (any client obeys that) but "the SERVER now rejects that exact token."
    """
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    assert client.get(_ME_PATH).status_code == 200  # sanity: session works pre-logout

    captured_cookie = client.cookies.get(COOKIE_NAME)
    assert captured_cookie

    response = client.post(_LOGOUT_PATH)
    assert response.status_code == 200

    client.cookies.set(COOKIE_NAME, captured_cookie)
    replayed = client.get(_ME_PATH)

    assert replayed.status_code == 401
    assert replayed.json()["error"]["code"] == "auth_required"


def test_relogin_after_logout_issues_a_working_session(tmp_engine: Engine) -> None:
    """Re-login after logout works — the new cookie carries the freshly bumped epoch."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    client.post(_LOGOUT_PATH)
    assert client.get(_ME_PATH).status_code == 401  # sanity: logged out

    login_as(client, "admin@example.com")

    assert client.get(_ME_PATH).status_code == 200


def test_logout_without_a_cookie_returns_200(tmp_engine: Engine) -> None:
    """Logout stays idempotent-200 with no session cookie at all (unauthenticated caller)."""
    client, _ = _build_client(tmp_engine)

    response = client.post(_LOGOUT_PATH)

    assert response.status_code == 200


def test_logout_with_a_tampered_cookie_returns_200_and_does_not_touch_any_users_epoch(
    tmp_engine: Engine,
) -> None:
    """An invalid (tampered) cookie is best-effort-ignored: still 200, and revokes nobody."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    user_before = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_before is not None
    assert user_before.session_epoch == 0

    valid_token = client.cookies.get(COOKIE_NAME)
    assert valid_token
    tampered = ("a" if valid_token[0] != "a" else "b") + valid_token[1:]
    client.cookies.set(COOKIE_NAME, tampered)

    response = client.post(_LOGOUT_PATH)

    assert response.status_code == 200
    user_after = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_after is not None
    assert user_after.session_epoch == 0


def test_logout_bumps_session_epoch_in_the_database(tmp_engine: Engine) -> None:
    """Logout with a valid cookie increments the owning `User` row's `session_epoch` by 1."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    user_before = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_before is not None
    assert user_before.session_epoch == 0

    client.post(_LOGOUT_PATH)

    user_after = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_after is not None
    assert user_after.session_epoch == 1


# ---------------------------------------------------------------------------
# Legacy / malformed cookie payloads — never-raises contract (Interfaces §i pin)
# ---------------------------------------------------------------------------


def test_legacy_bare_string_session_cookie_is_treated_as_no_session(tmp_engine: Engine) -> None:
    """A pre-task-05 cookie (bare `str(user_id)` payload) is inert, not a crash (interface pin)."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    user = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user is not None

    legacy_serializer = URLSafeTimedSerializer(
        client.app.state.settings.session_secret.get_secret_value(),  # type: ignore[attr-defined]
        salt=_LEGACY_SESSION_SALT,
    )
    client.cookies.set(COOKIE_NAME, legacy_serializer.dumps(str(user.id)))

    response = client.get(_ME_PATH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_cookie_dict_payload_missing_epoch_key_is_treated_as_no_session(tmp_engine: Engine) -> None:
    """A validly signed dict payload missing the `"epoch"` key returns no session, not a crash."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    user = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user is not None

    serializer = URLSafeTimedSerializer(
        client.app.state.settings.session_secret.get_secret_value(),  # type: ignore[attr-defined]
        salt=_LEGACY_SESSION_SALT,
    )
    client.cookies.set(COOKIE_NAME, serializer.dumps({"uid": str(user.id)}))

    response = client.get(_ME_PATH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_cookie_dict_payload_with_non_int_epoch_is_treated_as_no_session(
    tmp_engine: Engine,
) -> None:
    """A validly signed dict payload whose `"epoch"` is not an int returns no session."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    login_as(client, "admin@example.com")
    user = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user is not None

    serializer = URLSafeTimedSerializer(
        client.app.state.settings.session_secret.get_secret_value(),  # type: ignore[attr-defined]
        salt=_LEGACY_SESSION_SALT,
    )
    client.cookies.set(COOKIE_NAME, serializer.dumps({"uid": str(user.id), "epoch": "not-an-int"}))

    response = client.get(_ME_PATH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


# ---------------------------------------------------------------------------
# OAuth state CSRF — /auth/login mints + sets the double-submit cookie
# ---------------------------------------------------------------------------


def test_login_response_state_matches_oauth_state_cookie_dev_flags() -> None:
    """`/auth/login`'s redirect `state` equals its own `advisordesk_oauth_state` cookie value.

    Also pins the cookie's dev-mode flags (HttpOnly, SameSite=Lax, no Secure, 600s max-age) —
    DB-less: `/auth/login` never depends on `get_session`.
    """
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(settings=_build_settings(), oauth_client=oauth_client)
    client = TestClient(app)

    response = client.get(_LOGIN_PATH, follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    parsed_state = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["state"][0]

    set_cookies = response.headers.get_list("set-cookie")
    state_cookie_header = next(
        (c for c in set_cookies if c.startswith(f"{_STATE_COOKIE_NAME}=")), None
    )
    assert state_cookie_header is not None
    assert f"{_STATE_COOKIE_NAME}={parsed_state}" in state_cookie_header
    assert "HttpOnly" in state_cookie_header
    assert "SameSite=lax" in state_cookie_header
    assert "; Secure" not in state_cookie_header
    assert "Max-Age=600" in state_cookie_header


def test_login_state_cookie_is_secure_in_production() -> None:
    """Prod (`ENVIRONMENT=production`): the state cookie carries `Secure` too."""
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(settings=_build_settings(environment="production"), oauth_client=oauth_client)
    client = TestClient(app)

    response = client.get(_LOGIN_PATH, follow_redirects=False)

    set_cookies = response.headers.get_list("set-cookie")
    state_cookie_header = next(
        (c for c in set_cookies if c.startswith(f"{_STATE_COOKIE_NAME}=")), None
    )
    assert state_cookie_header is not None
    assert "Secure" in state_cookie_header


# ---------------------------------------------------------------------------
# OAuth state CSRF — /auth/callback verification
# ---------------------------------------------------------------------------


def test_callback_rejects_forged_unsigned_state_with_403(tmp_engine: Engine) -> None:
    """A `state` value never produced by `mint_state` fails signature verification -> 403.

    The callback `code` is deliberately left unregistered on the fake OAuth client: a correct
    implementation checks `state` BEFORE calling `exchange_code`, so it never looks the code up
    at all. If it did, the fake's `exchange_code` would raise `KeyError` instead of this test's
    expected 403 — a stronger failure signal than a passing assertion alone.
    """
    client, _ = _build_client(tmp_engine)
    forged_state = "forged-unsigned-state-value"
    client.cookies.set(_STATE_COOKIE_NAME, forged_state)

    response = client.get(
        _CALLBACK_PATH,
        params={"code": "unregistered-code", "state": forged_state},
        follow_redirects=False,
    )

    assert response.status_code == 403
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_callback_rejects_valid_state_with_no_state_cookie_with_403(tmp_engine: Engine) -> None:
    """A validly SIGNED `state` with no double-submit cookie at all is still rejected — 403.

    Proves the double-submit cookie is required in addition to the signature: an attacker can
    mint a valid `state` from their OWN `/auth/login`, but cannot forge the victim's browser
    cookie (this IS the CSRF pin, not the signature check above).
    """
    client, _ = _build_client(tmp_engine)
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    state = mint_state(settings)
    # deliberately no client.cookies.set(_STATE_COOKIE_NAME, ...)

    response = client.get(
        _CALLBACK_PATH,
        params={"code": "unregistered-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 403
    body = response.json()
    assert set(body.keys()) == {"error"}


def test_callback_rejects_valid_state_with_mismatched_state_cookie_with_403(
    tmp_engine: Engine,
) -> None:
    """A validly signed `state` whose double-submit cookie holds a DIFFERENT signed state — 403."""
    client, _ = _build_client(tmp_engine)
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    state = mint_state(settings)
    other_state = mint_state(settings)
    client.cookies.set(_STATE_COOKIE_NAME, other_state)

    response = client.get(
        _CALLBACK_PATH,
        params={"code": "unregistered-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_callback_rejects_expired_state_with_403(
    tmp_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `state` minted before `STATE_MAX_AGE_SECONDS` elapsed is rejected once it expires.

    Monkeypatches the module-level `app.auth.state.STATE_MAX_AGE_SECONDS` to 0 so any positive
    age at all counts as expired, then sleeps past a full second boundary so the elapsed-time
    check is unambiguous regardless of clock/timestamp granularity.
    """
    client, _ = _build_client(tmp_engine)
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    state = mint_state(settings)
    client.cookies.set(_STATE_COOKIE_NAME, state)
    monkeypatch.setattr("app.auth.state.STATE_MAX_AGE_SECONDS", 0)
    time.sleep(1.1)

    response = client.get(
        _CALLBACK_PATH,
        params={"code": "unregistered-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_full_login_then_callback_round_trip_succeeds_with_303_and_deletes_state_cookie(
    tmp_engine: Engine,
) -> None:
    """The real user-facing flow: `/auth/login` then `/auth/callback` on the SAME client.

    `begin_login` (`tests/auth_helpers.py`) drives `/auth/login` and returns its minted
    `state`, landing the matching double-submit cookie in the client's jar exactly as a real
    browser would — the happy-path proof that `login_as`'s own two-call flow (used throughout
    the wider suite) actually satisfies both state checks end to end. Also pins that a
    successful callback deletes the now-consumed state cookie.
    """
    client, oauth_client = _build_client(tmp_engine)
    state = begin_login(client)
    code = "full-round-trip-code"
    oauth_client.identities[code] = {
        "email": "admin@example.com",
        "name": "Ada Admin",
        "avatar_url": None,
    }

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": state}, follow_redirects=False
    )

    assert response.status_code == 303
    set_cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith(f"{COOKIE_NAME}=") for c in set_cookies)
    state_deletion = next((c for c in set_cookies if c.startswith(f"{_STATE_COOKIE_NAME}=")), None)
    assert state_deletion is not None
    assert "Max-Age=0" in state_deletion
