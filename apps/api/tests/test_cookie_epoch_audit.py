"""P7 remediation (fresh-review M1) — the cookie-epoch-stale rejection branch in
`app.auth.deps.require_admin` must log a WARNING, mirroring the bearer path's own
`reason=revoked` audit line for the identical underlying event (a since-run `/auth/logout`
epoch bump revoking an outstanding credential).

Before this fix, `require_admin`'s `cookie_epoch != user.session_epoch` branch (`app/auth/
deps.py`) raised `AuthRequiredError` with no log line at all — the one authentication-failure
branch left unlogged relative to `app.auth.tokens.resolve_bearer_token`'s `reason=revoked` line
for the bearer path's equivalent case. A captured/stolen admin session cookie replayed AFTER
`/auth/logout` correctly 401s but previously left zero forensic trace in `docker logs`.

Mirrors `tests/test_bearer_revocation.py`'s own caplog pattern (`_build_settings`/`_build_client`
duplicated locally per this repo's established no-cross-test-file-import precedent — see that
file's module docstring) and its own "replay a captured pre-bump cookie after logout" technique
(`test_caplog_logout_logs_info_with_user_id_and_epoch_bumped_flag`), applied here to the
`require_admin` rejection side rather than the logout side.
"""

from __future__ import annotations

import logging

import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from app.auth.sessions import COOKIE_NAME
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User

_ME_PATH = "/api/v1/auth/me"
_LOGOUT_PATH = "/api/v1/auth/logout"


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
    """Build a `TestClient` over a real, DB-backed app with a fake OAuth seam."""
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
        oauth_client=FakeGoogleOAuthClient(),
    )
    return TestClient(app)


def test_replaying_revoked_cookie_logs_warning_with_user_id_and_revoked_cookie_reason(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """The core M1 pin: a session cookie captured BEFORE `/auth/logout` bumps `session_epoch`,
    then replayed AFTER, must 401 at `require_admin` AND log a WARNING naming the user id and the
    `revoked-cookie` reason keyword — the cookie-path counterpart to the bearer path's
    `reason=revoked` line (`app.auth.tokens.resolve_bearer_token`)."""
    email = "cookie-epoch-audit@example.com"
    client = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = session.execute(select(User).where(User.email == email)).scalar_one()
        user_id = str(owner.id)
    finally:
        session.close()

    stale_cookie = client.cookies.get(COOKIE_NAME)
    assert stale_cookie

    logout_response = client.post(_LOGOUT_PATH)
    assert logout_response.status_code == 200

    client.cookies.set(COOKIE_NAME, stale_cookie)

    with caplog.at_level(logging.WARNING):
        response = client.get(_ME_PATH)

    assert response.status_code == 401
    matches = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and user_id in r.getMessage()
        and "revoked-cookie" in r.getMessage().lower()
    ]
    assert matches, [r.getMessage() for r in caplog.records]


def test_replaying_revoked_cookie_never_logs_the_raw_cookie_value(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Log-hygiene pin (M1's own 'NEVER the cookie value' requirement): the raw signed cookie
    value must never appear in any captured record, mirroring `tests/test_auth_log_hygiene.py`'s
    treatment of the logout cookie value and the bearer path's raw-token/hash never-log pins."""
    email = "cookie-epoch-hygiene@example.com"
    client = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)

    stale_cookie = client.cookies.get(COOKIE_NAME)
    assert stale_cookie

    client.post(_LOGOUT_PATH)
    client.cookies.set(COOKIE_NAME, stale_cookie)

    with caplog.at_level(logging.WARNING):
        response = client.get(_ME_PATH)

    assert response.status_code == 401
    assert stale_cookie not in caplog.text
