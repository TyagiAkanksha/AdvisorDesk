"""Regression tests for phase-6 task-05 review round 1, finding I-1 (logout epoch guard).

PRD §9 auth security. Review report `.superpowers/sdd/reports/p6-t05-review.md`, Important-1:
before this fix, `POST /auth/logout` best-effort-bumped `users.session_epoch` for ANY cookie
that merely passed `read_session`'s shape/signature checks, with no comparison against the
row's live epoch — so a cookie already revoked by a PRIOR logout (and therefore already
rejected everywhere else, e.g. `require_admin`'s 401) retained one privileged, destructive
server-side effect: replaying it at `/auth/logout` again silently killed whatever session the
admin was CURRENTLY using, for the remainder of the stale cookie's 30-day signed lifetime.

Controller-adjudicated fix shape: `app.services.users.bump_session_epoch` now takes the cookie's
own `epoch` and only bumps when it still equals the row's CURRENT `session_epoch` — i.e. only
when the presented cookie is itself still a live, currently-valid session. `/auth/logout`'s
response contract is unchanged: 200, cookie cleared, in every case.

This is a NEW file — `tests/test_auth_hardening.py` (the RED-phase, controller-pinned file for
this task) is not edited; its own logout-revocation tests only ever exercise a single logout
with a fresh-that-request cookie, so none of them cover a SECOND logout with a now-stale cookie
— exactly the gap this file closes. Fixture style (helpers, `_build_client`, `_fetch_user_by_email`)
mirrors `tests/test_auth_hardening.py`, kept local here rather than imported for the same reason
that file gives (`tests/test_auth_endpoints.py` precedent): these test-author-pinned modules are
not shared-helper modules.
"""

from __future__ import annotations

import sqlalchemy as sa
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.auth.sessions import COOKIE_NAME
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User

_LOGOUT_PATH = "/api/v1/auth/logout"
_ME_PATH = "/api/v1/auth/me"


def _build_settings(*, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        environment="development",
    )


def _build_client(tmp_engine: Engine, *, admin_emails: str = "admin@example.com") -> TestClient:
    """Build a `TestClient` over a real DB-backed app with a fake OAuth seam injected."""
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
        oauth_client=FakeGoogleOAuthClient(),
    )
    return TestClient(app)


def _fetch_user_by_email(engine: Engine, email: str) -> User | None:
    """Open a short-lived session and return the `User` row for the exact `email` given."""
    session = make_session_factory(engine)()
    try:
        return session.execute(sa.select(User).where(User.email == email)).scalar_one_or_none()
    finally:
        session.close()


def test_replaying_a_revoked_cookie_at_logout_does_not_bump_epoch_or_kill_concurrent_session(
    tmp_engine: Engine,
) -> None:
    """I-1 fix: a stale (already-revoked) cookie at `/auth/logout` must be fully inert.

    Reproduces the review report's probes P1/P1b: log in once (epoch 0), capture that cookie,
    log out (epoch -> 1), log back in on the SAME client (epoch 1 — a fresh cookie overwrites
    the jar) — then manually replay the FIRST (now-stale, epoch-0) cookie at `/auth/logout`.
    Before the fix this bumped the epoch again (1 -> 2), silently killing the second,
    concurrently valid epoch-1 session. After the fix: still 200 (the idempotent-200 contract
    holds unconditionally), but the row's epoch is UNCHANGED, and the concurrently-valid
    epoch-1 cookie still authenticates at `/auth/me`.
    """
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    stale_cookie = client.cookies.get(COOKIE_NAME)
    assert stale_cookie

    first_logout = client.post(_LOGOUT_PATH)
    assert first_logout.status_code == 200
    user_after_first_logout = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_after_first_logout is not None
    assert user_after_first_logout.session_epoch == 1

    login_as(client, "admin@example.com")
    fresh_cookie = client.cookies.get(COOKIE_NAME)
    assert fresh_cookie
    assert fresh_cookie != stale_cookie

    client.cookies.set(COOKIE_NAME, stale_cookie)
    replay_response = client.post(_LOGOUT_PATH)

    assert replay_response.status_code == 200
    user_after_replay = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_after_replay is not None
    assert user_after_replay.session_epoch == 1  # UNCHANGED — the stale cookie did not bump

    client.cookies.set(COOKIE_NAME, fresh_cookie)
    still_valid = client.get(_ME_PATH)
    assert still_valid.status_code == 200


def test_logout_with_a_current_cookie_still_returns_200_and_bumps_the_epoch(
    tmp_engine: Engine,
) -> None:
    """Regression for the intended behavior: a CURRENT (not-yet-revoked) cookie still revokes."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    user_before = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_before is not None
    assert user_before.session_epoch == 0

    response = client.post(_LOGOUT_PATH)

    assert response.status_code == 200
    user_after = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_after is not None
    assert user_after.session_epoch == 1


def test_logout_with_no_cookie_returns_200_and_does_not_bump_any_users_epoch(
    tmp_engine: Engine,
) -> None:
    """No cookie at all: still 200 idempotent, and no row's epoch moves (nothing to revoke)."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    user_before = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_before is not None
    assert user_before.session_epoch == 0

    client.cookies.delete(COOKIE_NAME)
    response = client.post(_LOGOUT_PATH)

    assert response.status_code == 200
    user_after = _fetch_user_by_email(tmp_engine, "admin@example.com")
    assert user_after is not None
    assert user_after.session_epoch == 0
