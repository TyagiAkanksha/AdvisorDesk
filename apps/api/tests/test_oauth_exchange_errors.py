"""Fixer-owned tests for final-review finding C-3 / t01 M14: unguarded OAuth exchange failures.

`app.auth.oauth.HttpxGoogleOAuthClient.exchange_code` used to let a
non-2xx Google response (`raise_for_status()`) or a userinfo payload
missing `"email"` (`payload["email"]` `KeyError`) escape as an unhandled
500 with a plain-text/traceback body — reachable from `/auth/callback` on
a reused/expired authorization code, or any transient Google-side failure.
Both are wrapped into the typed `OAuthExchangeError` (502, PRD §9 envelope)
now.

Two layers of coverage:
  1. `HttpxGoogleOAuthClient.exchange_code` in isolation, against a fake
     httpx transport (`httpx.MockTransport` — stdlib-adjacent, part of
     `httpx` itself, no extra dependency) standing in for Google's real
     endpoints. DB-less.
  2. `/auth/callback` end to end, with a minimal `GoogleOAuthClient` fake
     (structurally matching the Protocol, not `auth_helpers.py`'s pinned
     `FakeGoogleOAuthClient`, which never raises) that raises
     `OAuthExchangeError` directly — proving the ROUTE answers the §9
     envelope (502, no plain text/traceback) rather than an unhandled 500,
     regardless of what layer inside `exchange_code` raised it.

`tests/auth_helpers.py` and `tests/test_auth_endpoints.py` are
test-author-pinned files and are not touched here (CONVENTIONS.md §10).

Phase-6 task-05 (PRD §9 OAuth state CSRF) note: `test_callback_oauth_exchange_failure_
returns_enveloped_502_not_plain_text` now mints a real, signed `state` and injects a matching
`advisordesk_oauth_state` double-submit cookie before calling `/auth/callback` directly — the
same fix `tests/test_auth_hardening.py`'s test-author report applied to every other direct
(non-`login_as`) callback call across the suite, so this test reaches the `exchange_code` call
(and its `OAuthExchangeError`) it actually means to exercise, rather than answering a 303 to
`/signin?error=state` on the (now-checked-first) state CSRF guard. This file predates task-05's
RED phase (`git log` shows it last touched 2026-07-30, before the task-05 RED commit) and was
missed by that phase's caller audit — a pre-existing test broken as a mechanical side effect of
the interface change, not a task-05-authored test; only the input construction below changed, no
assertion did.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.auth.oauth import GoogleIdentity, HttpxGoogleOAuthClient
from app.auth.state import mint_state
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.services.errors import OAuthExchangeError

_CALLBACK_PATH = "/api/v1/auth/callback"
_TOKEN_HOST = "oauth2.googleapis.com"
# Phase-6 task-05 (PRD §9 OAuth state CSRF) — brief-pinned literal, not assumed to be an
# `app.auth.state` export, so defined locally (mirrors `tests/test_auth_hardening.py`).
_STATE_COOKIE_NAME = "advisordesk_oauth_state"


def _build_oauth_client(monkeypatch: pytest.MonkeyPatch, handler) -> HttpxGoogleOAuthClient:
    """Build a real `HttpxGoogleOAuthClient` whose internal `httpx.Client(...)` calls are routed
    through a `MockTransport(handler)` instead of the network — `exchange_code` builds its own
    `httpx.Client` internally (not injectable), so `httpx.Client` itself is monkeypatched at the
    `app.auth.oauth` import site, the same "mock only the true external seam" precedent
    CONVENTIONS.md §10 already applies to the Google OAuth client as a whole.
    """

    # Captured BEFORE patching: `app.auth.oauth.httpx` is the real `httpx` module object (not a
    # separate reference), so patching `httpx.Client` globally would make a naive
    # `httpx.Client(...)` call inside the factory itself resolve to the patched name too —
    # infinite recursion. Binding the real class first avoids that.
    real_client_class = httpx.Client

    def fake_client_factory(*args: object, **kwargs: object) -> httpx.Client:
        return real_client_class(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("app.auth.oauth.httpx.Client", fake_client_factory)
    return HttpxGoogleOAuthClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="https://example.com/api/v1/auth/callback",
    )


# ---------------------------------------------------------------------------
# 1. HttpxGoogleOAuthClient.exchange_code, in isolation
# ---------------------------------------------------------------------------


def test_exchange_code_raises_oauth_exchange_error_on_non_2xx_token_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-2xx response from Google's token endpoint (e.g. a reused/expired `code`) raises
    `OAuthExchangeError`, not an unhandled `httpx.HTTPStatusError`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == _TOKEN_HOST:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"email": "unreached@example.com"})

    client = _build_oauth_client(monkeypatch, handler)

    with pytest.raises(OAuthExchangeError):
        client.exchange_code("reused-or-expired-code")


def test_exchange_code_raises_oauth_exchange_error_on_non_2xx_userinfo_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-2xx response from Google's userinfo endpoint (token exchange itself succeeded)
    also raises `OAuthExchangeError`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == _TOKEN_HOST:
            return httpx.Response(200, json={"access_token": "fake-token"})
        return httpx.Response(503, json={"error": "unavailable"})

    client = _build_oauth_client(monkeypatch, handler)

    with pytest.raises(OAuthExchangeError):
        client.exchange_code("some-code")


def test_exchange_code_raises_oauth_exchange_error_on_missing_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both requests 2xx, but the userinfo payload has no `"email"` key — raises
    `OAuthExchangeError`, not an unhandled `KeyError`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == _TOKEN_HOST:
            return httpx.Response(200, json={"access_token": "fake-token"})
        return httpx.Response(200, json={"name": "No Email Here"})

    client = _build_oauth_client(monkeypatch, handler)

    with pytest.raises(OAuthExchangeError):
        client.exchange_code("some-code")


def test_exchange_code_succeeds_on_well_formed_2xx_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: the happy path is unaffected by the new error wrapping."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == _TOKEN_HOST:
            return httpx.Response(200, json={"access_token": "fake-token"})
        return httpx.Response(
            200, json={"email": "ada@example.com", "name": "Ada", "picture": None}
        )

    client = _build_oauth_client(monkeypatch, handler)

    identity = client.exchange_code("good-code")

    assert identity["email"] == "ada@example.com"
    assert identity["name"] == "Ada"


# ---------------------------------------------------------------------------
# 2. /auth/callback end to end: an OAuthExchangeError answers the §9 envelope, not a 500
# ---------------------------------------------------------------------------


@dataclass
class _RaisingOAuthClient:
    """A minimal `GoogleOAuthClient`-shaped fake (structural, not `auth_helpers`'s pinned fake)
    whose `exchange_code` always raises — proves the ROUTE maps `OAuthExchangeError` to the §9
    envelope, independent of exactly what inside `exchange_code` raised it."""

    def authorization_url(self, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/fake-consent?state={state}"

    def exchange_code(self, code: str) -> GoogleIdentity:
        raise OAuthExchangeError("Google's OAuth token exchange failed.")


def _build_client(tmp_engine: Engine) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with `_RaisingOAuthClient` injected.

    A real `session_factory` is required even though this route's happy
    path never reaches its DB write — `get_session` (`app.routes.deps`) is
    still resolved as a FastAPI dependency before the route body runs.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=Settings(
            session_secret="test-secret",
            google_client_id="test-google-client-id",
            google_client_secret="test-google-client-secret",
            admin_emails="admin@example.com",
        ),
        oauth_client=_RaisingOAuthClient(),
    )
    return TestClient(app)


def test_callback_oauth_exchange_failure_returns_enveloped_502_not_plain_text(
    tmp_engine: Engine,
) -> None:
    """A reused/expired code (or any Google-side exchange failure) 502s with the §9 envelope —
    not FastAPI/Starlette's plain-text/traceback default for an unhandled exception."""
    client = _build_client(tmp_engine)
    # Phase-6 task-05: a direct (non-login_as) callback call needs a validly minted state +
    # matching double-submit cookie, or it answers a 303 to `/signin?error=state` on the state
    # check before ever reaching `exchange_code` — the OAuthExchangeError -> 502 mapping this
    # test actually exercises.
    state = mint_state(client.app.state.settings)  # type: ignore[attr-defined]
    client.cookies.set(_STATE_COOKIE_NAME, state)

    response = client.get(
        _CALLBACK_PATH,
        params={"code": "reused-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 502
    assert response.headers.get("set-cookie") is None
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "oauth_exchange_failed"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert "Traceback" not in response.text
