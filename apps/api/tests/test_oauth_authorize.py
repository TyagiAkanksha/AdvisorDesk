"""Failing (RED) tests for `GET /api/v1/oauth/authorize` + `GET /api/v1/oauth/authorize/continue`
(mcp-oauth plan, task 05).

Task brief: docs/plans/mcp-oauth/task-05-authorize-pkce-google-bridge.md. Spec:
docs/plans/mcp-oauth/DESIGN.md §"End-to-end flow" steps 5-6, §"Google bridge + consent", §"Security
/ threat model" (PKCE, exact redirect, open-redirect prevention, code TTL); RFC 6749 §4.1
(authorization code grant) + §4.1.2.1 (unknown-client/unregistered-redirect never redirect); RFC
7636 (PKCE).

Today neither `/oauth/authorize` nor `/oauth/authorize/continue` exists — `app.routes.oauth_routes`
(task 04) declares only `POST /oauth/register` — so every request below 404s (rendered as the
existing `http_404`-coded §9 envelope by `app.routes.errors._http_exception_handler`) instead of
producing the 303/302/400/307/429 this file pins. No not-yet-existing name is imported at module
level (`app.auth.oauth_request`/`app.auth.oauth_authorize`/`app.services.oauth_codes`/
`app.services.pkce` all land this task's GREEN step) — the pending-authorization cookie's name is
defined locally as `_AUTHORIZE_COOKIE_NAME` instead, mirroring `tests/
test_auth_callback_redirect.py`'s own `_STATE_COOKIE_NAME` precedent ("brief-pinned literal, not
assumed to be a module export, so defined locally") — so this file collects cleanly and every test
below fails at ASSERTION time, not at collection; see the test-author report for the literal
per-test failure output.

Two tests are expected to ALREADY pass today, kept as regression guards rather than dropped:
`test_mcp_cookie_path_still_401_with_challenge` (mirrors `tests/test_mcp_www_authenticate.py::
test_stale_cookie_401_carries_www_authenticate` — the task-05 `resolve_admin`/`require_admin`
split must not change this observable behavior at all) and
`test_callback_without_pending_cookie_still_goes_to_admin_app` (today's `auth_callback` already
unconditionally redirects to `settings.admin_app_url` on success, since the pending-cookie branch
this task adds doesn't exist yet — a plain login with no pending authorization must keep landing
there once it does).

CONVENTIONS.md §10: every test here requests `tmp_engine` (skipped by fixture name when
`TEST_DATABASE_URL` is unset). `_build_app`/`_build_settings` mirror `tests/
test_mcp_www_authenticate.py`'s own shape (a real Google OAuth seam via `FakeGoogleOAuthClient`,
needed for the Google-bridge tests), pinned to `oauth_issuer_url="https://api.example"` and
`admin_app_url="https://admin.example"` per the test-author brief's own controller resolutions.
`follow_redirects=False` on every request in this file, per the task brief's explicit mandate —
several redirect targets (the client's own `redirect_uri`, `settings.admin_app_url`) are
deliberately off-app and unreachable from the test process.
"""

from __future__ import annotations

import urllib.parse

from auth_helpers import FakeGoogleOAuthClient, begin_login, login_as
from fastapi import FastAPI
from fastapi.testclient import TestClient
from oauth_helpers import complete_authorization
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User
from app.models.oauth import OAuthAuthorizationCode
from app.services.token_hashing import hash_token

_ISSUER = "https://api.example"
_ADMIN_APP_URL = "https://admin.example"
_ME_PATH = "/api/v1/auth/me"
_MCP_PATH = "/api/v1/mcp"

#: Not yet exported by any existing module (`app.auth.oauth_request` lands this task's GREEN
#: step) — defined locally per this file's own module docstring.
_AUTHORIZE_COOKIE_NAME = "advisordesk_oauth_authz"

_REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
#: RFC 7636 Appendix B's worked example: `S256(_CODE_VERIFIER) == _CODE_CHALLENGE`.
_CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
#: The MCP resource indicator for `_ISSUER` (`Settings.mcp_resource_url`, mcp-oauth task 01).
_RESOURCE = f"{_ISSUER}/api/v1/mcp"
_STATE = "xyz"

#: Streamable HTTP requires both of these on Accept or the transport 406s before ever reaching
#: auth/dispatch — copied from `tests/test_mcp_www_authenticate.py` (kept local per that file's
#: own no-cross-test-file-dependency precedent).
_MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
_INITIALIZE_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.1"},
    },
}


def _build_settings(
    *,
    admin_emails: str = "admin@example.com",
    oauth_rate_limit_per_min: int = 30,
) -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        mcp_http_enabled=True,
        oauth_issuer_url=_ISSUER,
        admin_app_url=_ADMIN_APP_URL,
        oauth_rate_limit_per_min=oauth_rate_limit_per_min,
    )


def _build_app(tmp_engine: Engine, *, settings: Settings | None = None) -> FastAPI:
    """Build a real, DB-backed app with a fake Google OAuth seam injected.

    `settings` defaults to `_build_settings()`'s own defaults.
    """
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=settings if settings is not None else _build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )


def _register(client: TestClient) -> str:
    """Register a fresh OAuth client (`POST /oauth/register`, task 04); return its `client_id`."""
    response = client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": [_REDIRECT_URI]},
    )
    assert response.status_code == 201, response.text
    client_id: str = response.json()["client_id"]
    return client_id


def _authorize_params(client_id: str, **overrides: str | None) -> dict[str, str]:
    """A full, valid `/authorize` query dict for `client_id` — RFC 7636 Appendix B's vector,
    `state="xyz"`, `resource=_RESOURCE`.

    A keyword override set to `None` OMITS that key entirely (rather than sending an empty query
    value), so `_authorize_params(client_id, code_challenge=None)` exercises a truly ABSENT
    `code_challenge`, matching the route's own `code_challenge: str | None = None` query
    parameter shape.
    """
    params: dict[str, str | None] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _REDIRECT_URI,
        "code_challenge": _CODE_CHALLENGE,
        "code_challenge_method": "S256",
        "scope": "mcp",
        "resource": _RESOURCE,
        "state": _STATE,
    }
    params.update(overrides)
    return {key: value for key, value in params.items() if value is not None}


def _redirect_query(location: str) -> dict[str, list[str]]:
    """Parse a redirect `Location`'s query string into `{name: [values]}`."""
    return urllib.parse.parse_qs(urllib.parse.urlparse(location).query)


# ---------------------------------------------------------------------------
# Steps 1-2 (RFC 6749 §4.1.2.1): unknown client / unregistered redirect NEVER redirect.
# ---------------------------------------------------------------------------


def test_unknown_client_400_json_no_redirect(tmp_engine: Engine) -> None:
    """`client_id=adkc_nope` (never registered) is `invalid_client`, 400, JSON body, no
    `Location` — RFC 6749 §4.1.2.1: an unknown client can never be trusted with a redirect."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params("adkc_nope"),
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_client"
    assert "location" not in response.headers


def test_unregistered_redirect_400_json_no_redirect(tmp_engine: Engine) -> None:
    """A `redirect_uri` not on the (registered) client's allowlist is `invalid_redirect_uri`,
    400, JSON body, no `Location` — same RFC 6749 §4.1.2.1 rationale: redirecting to an
    unregistered URI is exactly the open-redirect this check exists to prevent."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, redirect_uri="https://evil.example/cb"),
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_redirect_uri"
    assert "location" not in response.headers


# ---------------------------------------------------------------------------
# Steps 3-7: every OTHER validation failure redirects to the (now-verified) redirect_uri, with
# `state` preserved and no-store headers.
# ---------------------------------------------------------------------------


def test_missing_challenge_redirects_invalid_request(tmp_engine: Engine) -> None:
    """An absent `code_challenge` redirects (302) to the registered `redirect_uri` with
    `error=invalid_request` and the original `state` preserved."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, code_challenge=None),
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(_REDIRECT_URI)
    query = _redirect_query(location)
    assert query["error"] == ["invalid_request"]
    assert query["state"] == [_STATE]


def test_plain_method_redirects_invalid_request(tmp_engine: Engine) -> None:
    """`code_challenge_method=plain` (S256 required) redirects with `error=invalid_request`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, code_challenge_method="plain"),
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    query = _redirect_query(response.headers["location"])
    assert query["error"] == ["invalid_request"]
    assert query["state"] == [_STATE]


def test_response_type_token_redirects_unsupported(tmp_engine: Engine) -> None:
    """`response_type=token` (only `code` is supported) redirects with
    `error=unsupported_response_type`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, response_type="token"),
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    query = _redirect_query(response.headers["location"])
    assert query["error"] == ["unsupported_response_type"]
    assert query["state"] == [_STATE]


def test_bad_scope_redirects_invalid_scope(tmp_engine: Engine) -> None:
    """`scope=admin` (only `mcp`, or absent, is supported) redirects with `error=invalid_scope`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, scope="admin"),
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    query = _redirect_query(response.headers["location"])
    assert query["error"] == ["invalid_scope"]
    assert query["state"] == [_STATE]


def test_bad_resource_redirects_invalid_target(tmp_engine: Engine) -> None:
    """A `resource` other than this server's own MCP endpoint (or absent) redirects with
    `error=invalid_target`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, resource="https://other.example/api/v1/mcp"),
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    query = _redirect_query(response.headers["location"])
    assert query["error"] == ["invalid_target"]
    assert query["state"] == [_STATE]


def test_error_redirect_has_no_store(tmp_engine: Engine) -> None:
    """Every redirect-shaped `/authorize` error carries `Cache-Control: no-store` +
    `Pragma: no-cache` — an intermediary must never cache a response that can carry
    authorization-flow detail in its `Location`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, code_challenge=None),
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("pragma") == "no-cache"


# ---------------------------------------------------------------------------
# The happy path: 303 to `continue`, signed HttpOnly pending cookie, default scope/resource.
# ---------------------------------------------------------------------------


def test_valid_request_303_sets_httponly_cookie(tmp_engine: Engine) -> None:
    """A fully valid request 303s to `/oauth/authorize/continue` and sets the signed pending-
    authorization cookie: `HttpOnly`, `Path=/api/v1`, `SameSite=lax` (case-insensitive)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )

    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/api/v1/oauth/authorize/continue"
    set_cookie = response.headers.get("set-cookie", "")
    assert f"{_AUTHORIZE_COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/api/v1" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_absent_scope_and_resource_default(tmp_engine: Engine, db_session: Session) -> None:
    """Omitting both `scope` and `resource` still 303s (defaults apply silently) — verified via
    the later `OAuthAuthorizationCode` row once the flow completes: `scope == "mcp"`,
    `resource == settings.mcp_resource_url`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    authorize_response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id, scope=None, resource=None),
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text

    login_as(client, "admin@example.com")

    continue_response = client.get("/api/v1/oauth/authorize/continue", follow_redirects=False)
    assert continue_response.status_code == 302, continue_response.text

    row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    assert row.scope == "mcp"
    assert row.resource == _RESOURCE


# ---------------------------------------------------------------------------
# `/authorize/continue`: no cookie, no session (Google bridge), tampered cookie.
# ---------------------------------------------------------------------------


def test_continue_without_cookie_400(tmp_engine: Engine) -> None:
    """No pending-authorization cookie at all -> 400 `invalid_request`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get("/api/v1/oauth/authorize/continue", follow_redirects=False)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"


def test_continue_without_session_307_login(tmp_engine: Engine) -> None:
    """A pending cookie present but no admin session -> 307 to `/api/v1/auth/login` (the Google
    bridge)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    authorize_response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text

    response = client.get("/api/v1/oauth/authorize/continue", follow_redirects=False)

    assert response.status_code == 307, response.text
    assert response.headers["location"] == "/api/v1/auth/login"


def test_tampered_cookie_is_ignored(tmp_engine: Engine) -> None:
    """A garbage (unsigned/tampered) pending-authorization cookie is treated as absent -> 400
    `invalid_request`, never a 500 from a signature-verification crash."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client.cookies.set(_AUTHORIZE_COOKIE_NAME, "garbage")

    response = client.get("/api/v1/oauth/authorize/continue", follow_redirects=False)

    assert response.status_code == 400, response.text


# ---------------------------------------------------------------------------
# The full bridge: register -> authorize -> login_as -> continue -> a real, single-use code.
# ---------------------------------------------------------------------------


def test_full_bridge_issues_code(tmp_engine: Engine, db_session: Session) -> None:
    """The shared `oauth_helpers.complete_authorization` flow issues a real `adkac_` code backed
    by exactly one `OAuthAuthorizationCode` row, and the `continue` response's own `Set-Cookie`
    deletes the pending-authorization cookie.

    The deletion check reads `client.cookies` (TestClient's own jar) rather than a raw response
    header: `TestClient` auto-applies every `Set-Cookie` it receives, including a delete
    (Starlette's `delete_cookie` emits a Max-Age=0/epoch-`expires` Set-Cookie), so the jar no
    longer carrying the cookie after `complete_authorization` returns IS the observable effect of
    that deletion header — the same effect a real browser gives it — without this test needing to
    thread a raw `httpx.Response` back out of the shared helper (which returns only
    `AuthorizationResult`, by the brief's own pinned contract, since it exists to hand
    later `/token`-exchange tests a redeemable code, not to expose authorize/continue's own
    request/response shape).
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    result = complete_authorization(client)

    assert result.code.startswith("adkac_")
    assert result.state == _STATE
    assert result.client_id
    assert result.redirect_uri == _REDIRECT_URI

    row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    assert row.code_hash == hash_token(result.code)
    assert row.consumed_at is None
    ttl_seconds = (row.expires_at - row.created_at).total_seconds()
    assert 55 <= ttl_seconds <= 65
    assert row.client_id == result.client_id
    assert row.redirect_uri == result.redirect_uri
    assert row.resource == _RESOURCE
    assert row.scope == "mcp"

    assert _AUTHORIZE_COOKIE_NAME not in client.cookies


def test_continue_via_google_callback_redirects_to_continue(tmp_engine: Engine) -> None:
    """After `/authorize` parks the pending cookie, driving the REAL `/auth/login` ->
    `/auth/callback` round trip (rather than `login_as`, so this test can see the callback's own
    redirect) lands 303 to `/oauth/authorize/continue` — the Google-bridge amendment to
    `auth_callback`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    authorize_response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text

    oauth_client: FakeGoogleOAuthClient = client.app.state.oauth_client  # type: ignore[attr-defined]
    code = "fake-google-code"
    oauth_client.identities[code] = {
        "email": "admin@example.com",
        "name": "Test Admin",
        "avatar_url": "https://example.com/avatar.png",
    }
    state = begin_login(client)

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/api/v1/oauth/authorize/continue"


def test_callback_without_pending_cookie_still_goes_to_admin_app(tmp_engine: Engine) -> None:
    """A plain login with NO pending authorization in flight still 303s to `settings.admin_app_url`
    — the Google-bridge amendment must not touch the pre-existing plain-login redirect target.

    Expected to ALREADY pass today (see module docstring): today's `auth_callback` has no
    pending-cookie branch at all and always redirects to `admin_app_url`; this pins that this
    task's change is additive, not a regression, once the branch exists.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    oauth_client: FakeGoogleOAuthClient = client.app.state.oauth_client  # type: ignore[attr-defined]
    code = "plain-login-code"
    oauth_client.identities[code] = {
        "email": "admin@example.com",
        "name": "Test Admin",
        "avatar_url": "https://example.com/avatar.png",
    }
    state = begin_login(client)

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303, response.text
    assert response.headers["location"] == _ADMIN_APP_URL


def test_non_allowlisted_admin_access_denied(tmp_engine: Engine) -> None:
    """A logged-in admin whose email has since fallen off the allowlist (mirrors
    `tests/test_bearer_expiry_allowlist.py`'s live `admin_emails` mutation) gets `access_denied` on
    `continue`, redirected with `state` preserved — `require_admin`/`resolve_admin` itself does
    NOT check the allowlist, only the callback and this route's own check do."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client)

    authorize_response = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text

    login_as(client, "admin@example.com")
    client.app.state.settings.admin_emails = "someone-else@example.com"  # type: ignore[attr-defined]

    response = client.get("/api/v1/oauth/authorize/continue", follow_redirects=False)

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(_REDIRECT_URI)
    query = _redirect_query(location)
    assert query["error"] == ["access_denied"]
    assert query["state"] == [_STATE]


# ---------------------------------------------------------------------------
# Rate limiting, the resolve_admin regression guard, OpenAPI.
# ---------------------------------------------------------------------------


def test_authorize_rate_limited(tmp_engine: Engine) -> None:
    """`oauth_rate_limit_per_min=1`: the second `/authorize` call from the same IP 429s.

    The client is registered against a SEPARATE app instance (default rate limit) sharing the
    same `tmp_engine`/database, so the registration call itself never consumes the tight limit's
    one slot — `RateLimiter.check_oauth_request` keys its sliding window by IP alone
    (`f"oauth:{ip}"`), shared across every `/api/v1/oauth/*` path on a given app/limiter instance,
    so isolating registration onto its own app/limiter is what makes "the SECOND `/authorize`
    call" the one that 429s, rather than an incidental collision with registration's own slot.
    """
    setup_app = _build_app(tmp_engine)
    client_id = _register(TestClient(setup_app))

    app = _build_app(tmp_engine, settings=_build_settings(oauth_rate_limit_per_min=1))
    client = TestClient(app)

    first = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )
    assert first.status_code == 303, first.text

    second = client.get(
        "/api/v1/oauth/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )

    assert second.status_code == 429, second.text


def test_mcp_cookie_path_still_401_with_challenge(tmp_engine: Engine, db_session: Session) -> None:
    """Regression guard for the `resolve_admin`/`require_admin` split (mirrors `tests/
    test_mcp_www_authenticate.py::test_stale_cookie_401_carries_www_authenticate`): a session
    cookie whose owner's `session_epoch` has since moved must still 401 with the RFC 9728
    `WWW-Authenticate` challenge on `/api/v1/mcp` — `_require_admin_with_challenge`'s simplified
    body (now a bare `resolve_admin(request) is None -> raise _auth_required(request)`) must
    preserve this exact observable behavior.

    Expected to ALREADY pass today — `_require_admin_with_challenge` doesn't change until this
    task's GREEN step, so this is a before/after regression guard, not a RED case.
    """
    email = "stale-cookie-t05@example.com"
    app = _build_app(tmp_engine, settings=_build_settings(admin_emails=email))
    client = TestClient(app)
    login_as(client, email)

    owner = db_session.execute(select(User).where(User.email == email)).scalar_one()
    owner.session_epoch += 1
    db_session.commit()

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert "resource_metadata=" in response.headers.get("www-authenticate", "")


def test_openapi_has_authorize_operations(tmp_engine: Engine) -> None:
    """`/openapi.json` lists both new `operation_id`s — CONVENTIONS.md §5's "every route has a
    stable unique operation_id", codegen-visible for both frontend apps."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    operation_ids = {
        operation.get("operationId")
        for methods in response.json()["paths"].values()
        for operation in methods.values()
    }
    assert "oauth_authorize" in operation_ids
    assert "oauth_authorize_continue" in operation_ids
