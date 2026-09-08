"""Failing (RED) tests for `POST /api/v1/oauth/revoke` (RFC 7009 token revocation) and the
admin-session-gated connected-apps API — `GET /api/v1/oauth/clients` (list) and
`DELETE /api/v1/oauth/clients/{client_id}` (revoke a client outright) — mcp-oauth plan, task 08.

Task brief: docs/plans/mcp-oauth/task-08-revoke-admin-api.md. Spec: docs/plans/mcp-oauth/DESIGN.md
§"Endpoints" (`/revoke`), §"Admin management UI"; RFC 7009 (OAuth 2.0 Token Revocation).

Today `app.routes.oauth_routes` declares `/register`, `/authorize` (+ `/continue`,
`/authorize/decision`), and `/token` (tasks 04-07) — there is no `/revoke` route, and
`app.routes.oauth_admin_routes` (the sibling admin router this task creates, mounted at
`/oauth/clients`) does not exist at all, so `app.factory.create_app` never includes it. Every
request this file makes to `/api/v1/oauth/revoke`, `/api/v1/oauth/clients`, or
`/api/v1/oauth/clients/{client_id}` therefore 404s at the Starlette router, rendered as the
generic §9 `http_404` envelope (`app.routes.errors._http_exception_handler`,
`{"error": {"code": "http_404", "message": "Not Found"}}`) — never the bare OAuth
`{"error": "...", "error_description": "..."}` shape `/revoke` itself pins, and never the nested
§9 `{"error": {"code": "auth_required", ...}}` envelope the admin routes' own `require_admin`
gate would answer with once they exist. No not-yet-existing module is imported at module scope:
every collaborator this file imports (`app.models.oauth`, `app.models.api_tokens`,
`app.services.token_hashing`, `tests.oauth_helpers.complete_authorization`,
`tests.auth_helpers.login_as`) already exists as of task 01/05/06/07 — `app.services.oauth_tokens`
already exists too (task 07's `revoke_family`), but this file never imports it, and never imports
`app.services.oauth_admin*`/`app.routes.oauth_admin_routes` (neither exists yet) — driving
everything through the HTTP surface instead. So this module collects cleanly and every test fails
at ASSERTION time (a 404 where a 200/204/400/401/429 was expected, or a wrong body shape), never at
collection.

CONVENTIONS.md §10: every test below requests `tmp_engine`/`db_session` (skipped by fixture name
when `TEST_DATABASE_URL` is unset). `_build_settings`/`_build_app`/`_register_client`/`_exchange`/
`_refresh`/`_mcp_initialize` (plus `_MCP_HEADERS`/`_INITIALIZE_BODY`) are copied verbatim from
`tests/test_oauth_token.py` (task brief's own Context/Interfaces instruction: copy, don't import a
test module) so this file's helpers can never drift from that file's own proven shapes.
`tests.oauth_helpers.complete_authorization` drives register -> authorize -> Google-bridge login ->
consent approve -> code end to end and leaves a live admin session cookie on `client` afterward
(the same cookie the admin-gated routes below need) — every admin-route test that also needs a
live OAuth grant reuses that one flow rather than hand-rolling the sequence twice.

Controller ruling (plan defect, carried from the task-08 dispatch): the brief's own
`ConnectedAppRow.consent_granted_at` comment says "latest `OAuthConsent.updated_at`" — that column
does not exist on `OAuthConsent` (`app.models.oauth.OAuthConsent` carries `created_at` only, via
`TimestampMixin`; the brief's own Files section, oddly, does NOT list `oauth_consents` as touched
by this task's migration). Per the controller: `consent_granted_at` is `OAuthConsent.created_at` of
the active (`revoked_at IS NULL`) consent row. `test_admin_list_shape` below asserts it is not
`None` and (once GREEN) would equal that row's own `created_at` for one full authorization flow;
this file makes no assertion about a re-grant's timestamp.

Per-test notes for the less self-explanatory cases:

- `test_revoke_rate_limited` mirrors `test_oauth_token.py::test_token_rate_limited`'s isolation
  trick: a client_id is registered against a SEPARATE app/limiter instance (default 30/min) sharing
  the same `tmp_engine`/schema, so that setup traffic never consumes the tight
  `oauth_rate_limit_per_min=1` budget the app-under-test is built with — only the two `/revoke`
  POSTs against the tight-limit client do. Unlike
  `test_oauth_consent.py::test_decision_rate_limited`, `/oauth/revoke` needs no admin session or
  pending-authorization cookie, so no cookie-transplant is needed here — a bare second app/client
  pair, exactly like the `/token` precedent.
- `test_admin_list_shape`/`test_admin_list_counts_exclude_expired_and_revoked` read the admin list
  through the SAME `client` that `complete_authorization` + `_exchange` already drove — its cookie
  jar still carries the live admin session `login_as` (inside `complete_authorization`) minted,
  since neither call clears it. `db_session.expire_all()` is called before any DB read that follows
  an HTTP mutation the app itself made in a different session, mirroring every earlier mcp-oauth
  test file's own idiom.
- `test_admin_list_ordered_newest_first` backdates one client's `created_at` directly via
  `db_session` rather than relying on two back-to-back `now()` inserts to land in a provably
  different instant — mirrors `tests/test_content_gaps.py::test_gaps_ordered_newest_first`'s own
  explicit-timestamp idiom, avoiding any flakiness from two inserts landing in the same DB tick.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi import FastAPI
from fastapi.testclient import TestClient
from oauth_helpers import AuthorizationResult, complete_authorization
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models.api_tokens import ApiToken
from app.models.oauth import OAuthClient, OAuthConsent, OAuthRefreshToken
from app.services.token_hashing import hash_token

_ISSUER = "https://api.example"
#: The MCP resource indicator for `_ISSUER` (`Settings.mcp_resource_url`, mcp-oauth task 01) —
#: identical value `tests/oauth_helpers.py`'s own `_RESOURCE` module constant hardcodes.
_MCP_PATH = "/api/v1/mcp"
_TOKEN_PATH = "/api/v1/oauth/token"
_REGISTER_PATH = "/api/v1/oauth/register"
_REVOKE_PATH = "/api/v1/oauth/revoke"
_ADMIN_CLIENTS_PATH = "/api/v1/oauth/clients"

#: A realistic claude.ai-shaped callback — matches `tests/oauth_helpers.py`'s own
#: `_REDIRECT_URI` convention; used only by tests that register a client directly (not through
#: `complete_authorization`) and therefore need their own literal.
_REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"

#: Streamable HTTP requires both of these on Accept or the transport 406s before ever reaching
#: auth/dispatch — copied from `tests/test_oauth_token.py` (kept local per that file's own
#: no-cross-test-file-dependency precedent).
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
        oauth_rate_limit_per_min=oauth_rate_limit_per_min,
    )


def _build_app(tmp_engine: Engine, *, settings: Settings | None = None) -> FastAPI:
    """Build a real, DB-backed app with a fake Google OAuth seam injected.

    `settings` defaults to `_build_settings()`'s own defaults — mirrors `tests/
    test_oauth_token.py::_build_app` exactly.
    """
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=settings if settings is not None else _build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )


def _register_client(client: TestClient, redirect_uri: str) -> str:
    """Register a fresh OAuth client (`POST /oauth/register`) against `redirect_uri`; return its
    `client_id` — copied from `tests/test_oauth_token.py::_register_client`."""
    response = client.post(_REGISTER_PATH, json={"redirect_uris": [redirect_uri]})
    assert response.status_code == 201, response.text
    client_id: str = response.json()["client_id"]
    return client_id


def _exchange(
    client: TestClient, result: AuthorizationResult, **overrides: str | None
) -> httpx.Response:
    """POST a code-grant `/token` request built from `result`, with any `overrides` applied.

    Copied from `tests/test_oauth_token.py::_exchange` verbatim: an override set to `None` OMITS
    that form field entirely, matching the route's `Annotated[str | None, Form()] = None` shape.
    """
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": result.code,
        "redirect_uri": result.redirect_uri,
        "code_verifier": result.code_verifier,
        "client_id": result.client_id,
    }
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return client.post(_TOKEN_PATH, data=data)


def _refresh(
    client: TestClient, refresh_token: str, client_id: str, **overrides: str | None
) -> httpx.Response:
    """POST a refresh-grant `/token` request — copied from `tests/test_oauth_token.py::_refresh`."""
    data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return client.post(_TOKEN_PATH, data=data)


def _mcp_initialize(client: TestClient, access_token: str) -> httpx.Response:
    """POST an MCP `initialize` call authenticated with `access_token` as a bearer header —
    copied from `tests/test_oauth_token.py::_mcp_initialize`."""
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {access_token}"}
    return client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)


def _revoke(
    client: TestClient,
    *,
    token: str | None,
    client_id: str | None,
    token_type_hint: str | None = None,
) -> httpx.Response:
    """POST `/oauth/revoke` with `token`/`client_id`/`token_type_hint`, each OMITTED entirely
    when `None` — matching the route's `Annotated[str | None, Form()] = None` field shape (task
    brief Interfaces block), the same convention `_exchange`/`_refresh` above use."""
    data: dict[str, str] = {}
    if token is not None:
        data["token"] = token
    if client_id is not None:
        data["client_id"] = client_id
    if token_type_hint is not None:
        data["token_type_hint"] = token_type_hint
    return client.post(_REVOKE_PATH, data=data)


# ---------------------------------------------------------------------------
# POST /oauth/revoke (RFC 7009)
# ---------------------------------------------------------------------------


def test_revoke_refresh_token_kills_family(tmp_engine: Engine, db_session: Session) -> None:
    """Revoking a live refresh token kills its whole rotation family (`revoke_family`): 200, empty
    body, `no-store`/`no-cache`; the refresh row's `revoked_at` is set; the access token it minted
    401s at MCP afterward. RED today: 404, not 200 (and no `revoked_at`/401 to observe at all).

    Fix round 1 (review M-4): passes `token_type_hint="refresh_token"` so the RFC 7009 field the
    route declares (accepted, per `revoke_token`'s own docstring, but never read) is actually
    exercised end to end by at least one call in this file — a spec-compliant client's request is
    accepted verbatim, same assertions as before this hint was added."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]
    refresh_token = exchange.json()["refresh_token"]

    response = _revoke(
        client,
        token=refresh_token,
        client_id=result.client_id,
        token_type_hint="refresh_token",
    )

    assert response.status_code == 200, response.text
    assert response.text == ""
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("pragma") == "no-cache"

    db_session.expire_all()
    refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(refresh_token))
    ).scalar_one()
    assert refresh_row.revoked_at is not None

    mcp_response = _mcp_initialize(client, access_token)
    assert mcp_response.status_code == 401, mcp_response.text


def test_revoke_access_token_only(tmp_engine: Engine, db_session: Session) -> None:
    """Revoking an access token deletes only that `ApiToken` row: the access token 401s at MCP
    afterward, but the refresh token is untouched and can still rotate. RED today: 404, not 200."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]
    refresh_token = exchange.json()["refresh_token"]

    response = _revoke(client, token=access_token, client_id=result.client_id)

    assert response.status_code == 200, response.text

    mcp_response = _mcp_initialize(client, access_token)
    assert mcp_response.status_code == 401, mcp_response.text

    rotate_response = _refresh(client, refresh_token, result.client_id)
    assert rotate_response.status_code == 200, rotate_response.text

    db_session.expire_all()
    old_refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(refresh_token))
    ).scalar_one()
    assert old_refresh_row.revoked_at is not None  # revoked by the rotation above, not by /revoke


def test_revoke_unknown_token_200(tmp_engine: Engine) -> None:
    """RFC 7009 §2.2: revoking an unknown token still answers 200 (never reveals whether a token
    existed) — as long as `client_id` names a real, registered client. RED today: 404, not 200."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register_client(client, _REDIRECT_URI)

    response = _revoke(client, token="adkr_totally-unknown-value", client_id=client_id)

    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == "no-store"


def test_revoke_other_clients_token_noop(tmp_engine: Engine, db_session: Session) -> None:
    """Presenting client A's refresh token alongside client B's `client_id` is a no-op — 200, but
    nothing is revoked (`revoke_token` only acts when `refresh.client_id == client_id`). RED today:
    404, not 200 (and no live grant to prove survives, since `/token` doesn't exist either)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]
    refresh_token = exchange.json()["refresh_token"]
    other_client_id = _register_client(client, result.redirect_uri)

    response = _revoke(client, token=refresh_token, client_id=other_client_id)

    assert response.status_code == 200, response.text

    db_session.expire_all()
    refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(refresh_token))
    ).scalar_one()
    assert refresh_row.revoked_at is None

    mcp_response = _mcp_initialize(client, access_token)
    assert mcp_response.status_code < 400, mcp_response.text


def test_revoke_other_clients_access_token_noop(tmp_engine: Engine, db_session: Session) -> None:
    """The access-token twin of `test_revoke_other_clients_token_noop` above (fix round 1, review
    M-3): presenting client A's ACCESS token alongside client B's `client_id` is also a no-op —
    200, but the `ApiToken` row is left untouched and the access token still works at MCP
    afterward (`revoke_token`'s access branch only acts when `access.client_id == client_id`,
    docs/plans/mcp-oauth/task-08-revoke-admin-api.md)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]
    other_client_id = _register_client(client, result.redirect_uri)

    response = _revoke(client, token=access_token, client_id=other_client_id)

    assert response.status_code == 200, response.text

    db_session.expire_all()
    access_row = db_session.execute(
        select(ApiToken).where(ApiToken.token_hash == hash_token(access_token))
    ).scalar_one()
    assert access_row is not None

    mcp_response = _mcp_initialize(client, access_token)
    assert mcp_response.status_code < 400, mcp_response.text


def test_revoke_missing_token_400(tmp_engine: Engine) -> None:
    """An absent `token` field is 400 `invalid_request` "token is required." — checked before any
    `client_id` lookup (task brief's own pinned route order). RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = _revoke(client, token=None, client_id=None)

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "invalid_request"
    assert body["error_description"] == "token is required."
    assert response.headers.get("cache-control") == "no-store"


def test_revoke_unknown_client_401(tmp_engine: Engine) -> None:
    """An unregistered `client_id` is 401 `invalid_client` "Unknown client." — RFC 7009's one
    caller-visible failure mode (a bad `client_id`, as opposed to a bad/absent `token`). RED today:
    404, not 401."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = _revoke(client, token="adkr_whatever", client_id="adkc_totally-unregistered")

    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"] == "invalid_client"
    assert body["error_description"] == "Unknown client."


def test_revoke_rate_limited(tmp_engine: Engine) -> None:
    """`oauth_rate_limit_per_min=1`: the second `/revoke` call from the same IP 429s, with the §9
    `ErrorEnvelope` shape (standing ruling: the per-IP budget is shared across ALL `/oauth/*`
    routes, and the RATE-LIMIT check runs before any token/client_id validation) — mirrors
    `tests/test_oauth_token.py::test_token_rate_limited`'s isolation trick exactly. RED today: both
    calls 404 identically, so neither reaches 429."""
    setup_app = _build_app(tmp_engine)
    setup_client = TestClient(setup_app)
    client_id = _register_client(setup_client, _REDIRECT_URI)

    app = _build_app(tmp_engine, settings=_build_settings(oauth_rate_limit_per_min=1))
    client = TestClient(app)

    first = _revoke(client, token="adkr_whatever", client_id=client_id)
    assert first.status_code != 429, first.text

    second = _revoke(client, token="adkr_whatever", client_id=client_id)

    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "rate_limited"


def test_revoke_logs_client_id_never_the_token(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Final fix round 1, P13: a successful `POST /oauth/revoke` emits one INFO audit line naming
    `client_id` — the one security-relevant action that previously left no trace — and the raw
    token string appears in NO emitted record. Mirrors `tests/test_auth_log_hygiene.py:123-131`'s
    own `caplog`-around-one-call, assert-token-absent-everywhere pattern."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    refresh_token = exchange.json()["refresh_token"]

    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = _revoke(client, token=refresh_token, client_id=result.client_id)
    assert response.status_code == 200, response.text

    assert all(refresh_token not in r.getMessage() for r in caplog.records)
    assert any(
        "oauth token revoked" in r.getMessage() and result.client_id in r.getMessage()
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# GET /api/v1/oauth/clients — admin connected-apps list
# ---------------------------------------------------------------------------


def test_admin_list_requires_session(tmp_engine: Engine) -> None:
    """No admin session cookie -> 401 §9 envelope `auth_required` — the admin router's
    `require_admin` gate, distinct from `/oauth/*`'s own bare OAuth error shape. RED today: 404 (the
    router doesn't exist), not 401."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get(_ADMIN_CLIENTS_PATH)

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "auth_required"


def test_admin_list_shape(tmp_engine: Engine) -> None:
    """After one full authorization + code-exchange flow, the list has exactly one item with the
    live-token summary the task brief pins: `active_access_tokens == 1`,
    `active_refresh_tokens == 1`, `consent_granted_at` set, `last_used_at` `None` before any MCP
    call and set after one `initialize`, `latest_expires_at` ≈ `created_at` + 30 days. RED today:
    404, not 200 — `response.json()["items"]` never even runs (asserted status first)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]

    response = client.get(_ADMIN_CLIENTS_PATH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"items"}
    items = body["items"]
    assert len(items) == 1
    item = items[0]
    assert set(item.keys()) == {
        "client_id",
        "client_name",
        "redirect_uris",
        "created_at",
        "consent_granted_at",
        "active_access_tokens",
        "active_refresh_tokens",
        "last_used_at",
        "latest_expires_at",
    }
    assert item["client_id"] == result.client_id
    assert item["client_name"] == "Claude"
    assert item["redirect_uris"] == [result.redirect_uri]
    assert item["active_access_tokens"] == 1
    assert item["active_refresh_tokens"] == 1
    assert item["consent_granted_at"] is not None
    assert item["last_used_at"] is None

    created_at = datetime.fromisoformat(item["created_at"])
    latest_expires_at = datetime.fromisoformat(item["latest_expires_at"])
    delta = (latest_expires_at - created_at).total_seconds()
    assert abs(delta - 30 * 86400) < 300, delta

    mcp_response = _mcp_initialize(client, access_token)
    assert mcp_response.status_code < 400, mcp_response.text

    second_response = client.get(_ADMIN_CLIENTS_PATH)
    assert second_response.status_code == 200, second_response.text
    second_item = second_response.json()["items"][0]
    assert second_item["last_used_at"] is not None


def test_admin_list_counts_exclude_expired_and_revoked(
    tmp_engine: Engine, db_session: Session
) -> None:
    """An expired access token and a revoked refresh token are excluded from the live counts, and
    `latest_expires_at` is `None` once no refresh row is active. RED today: 404, not 200."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]
    refresh_token = exchange.json()["refresh_token"]

    access_row = db_session.execute(
        select(ApiToken).where(ApiToken.token_hash == hash_token(access_token))
    ).scalar_one()
    access_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(refresh_token))
    ).scalar_one()
    refresh_row.revoked_at = datetime.now(UTC)
    db_session.commit()

    response = client.get(_ADMIN_CLIENTS_PATH)

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["active_access_tokens"] == 0
    assert item["active_refresh_tokens"] == 0
    assert item["latest_expires_at"] is None


def test_admin_list_includes_tokenless_client(tmp_engine: Engine) -> None:
    """A freshly registered client with no consent/token at all still appears, with every count
    zero and every timestamp `None`. RED today: 404, not 200."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")
    client_id = _register_client(client, _REDIRECT_URI)

    response = client.get(_ADMIN_CLIENTS_PATH)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["client_id"] == client_id
    assert item["redirect_uris"] == [_REDIRECT_URI]
    assert item["active_access_tokens"] == 0
    assert item["active_refresh_tokens"] == 0
    assert item["consent_granted_at"] is None
    assert item["last_used_at"] is None
    assert item["latest_expires_at"] is None


def test_admin_list_ordered_newest_first(tmp_engine: Engine, db_session: Session) -> None:
    """Items come back ordered by `created_at` DESC. Both clients' `created_at` are backdated
    directly (mirrors `tests/test_content_gaps.py::test_gaps_ordered_newest_first`'s own
    explicit-timestamp idiom) so ordering can never depend on two inserts landing in different DB
    ticks. RED today: 404, not 200."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")
    older_id = _register_client(client, _REDIRECT_URI)
    newer_id = _register_client(client, _REDIRECT_URI)

    now = datetime.now(UTC)
    older_row = db_session.get(OAuthClient, older_id)
    assert older_row is not None
    older_row.created_at = now - timedelta(days=1)
    newer_row = db_session.get(OAuthClient, newer_id)
    assert newer_row is not None
    newer_row.created_at = now
    db_session.commit()

    response = client.get(_ADMIN_CLIENTS_PATH)

    assert response.status_code == 200, response.text
    client_ids = [item["client_id"] for item in response.json()["items"]]
    assert client_ids == [newer_id, older_id]


# ---------------------------------------------------------------------------
# DELETE /api/v1/oauth/clients/{client_id} — admin revoke-a-client
# ---------------------------------------------------------------------------


def test_admin_revoke_client_204_and_cascade(tmp_engine: Engine, db_session: Session) -> None:
    """Deleting a client 204s and cascades: the client row, its consent, its refresh token, and
    its access token are all gone; the access token 401s at MCP; the refresh token 401s
    `invalid_client` at `/token` (client lookup fails before the refresh token is ever inspected).
    RED today: 404 (wrong reason — route doesn't exist), not 204."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]
    refresh_token = exchange.json()["refresh_token"]

    response = client.delete(f"{_ADMIN_CLIENTS_PATH}/{result.client_id}")

    assert response.status_code == 204, response.text

    db_session.expire_all()
    assert db_session.get(OAuthClient, result.client_id) is None
    assert (
        db_session.execute(
            select(OAuthConsent).where(OAuthConsent.client_id == result.client_id)
        ).first()
        is None
    )
    assert (
        db_session.execute(
            select(OAuthRefreshToken).where(OAuthRefreshToken.client_id == result.client_id)
        ).first()
        is None
    )
    assert (
        db_session.execute(select(ApiToken).where(ApiToken.client_id == result.client_id)).first()
        is None
    )

    mcp_response = _mcp_initialize(client, access_token)
    assert mcp_response.status_code == 401, mcp_response.text

    refresh_response = _refresh(client, refresh_token, result.client_id)
    assert refresh_response.status_code == 401, refresh_response.text
    assert refresh_response.json()["error"] == "invalid_client"


def test_admin_delete_logs_client_id_never_the_token(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Final fix round 1, P13: a successful admin `DELETE /oauth/clients/{client_id}` emits one
    INFO audit line naming `client_id` and neither the raw access token nor the raw refresh token
    appears in any emitted record. Same `caplog` pattern as `test_revoke_logs_client_id_never_the_
    token` above and `tests/test_auth_log_hygiene.py:123-131`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    exchange = _exchange(client, result)
    assert exchange.status_code == 200, exchange.text
    access_token = exchange.json()["access_token"]
    refresh_token = exchange.json()["refresh_token"]

    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = client.delete(f"{_ADMIN_CLIENTS_PATH}/{result.client_id}")
    assert response.status_code == 204, response.text

    assert all(access_token not in r.getMessage() for r in caplog.records)
    assert all(refresh_token not in r.getMessage() for r in caplog.records)
    assert any(
        "oauth client deleted" in r.getMessage() and result.client_id in r.getMessage()
        for r in caplog.records
    )


def test_admin_revoke_unknown_404(tmp_engine: Engine) -> None:
    """Deleting a `client_id` that was never registered is 404 §9 `not_found`, "Client not
    found." RED today: 404 too, but for the WRONG reason (the route itself is missing, rendered as
    `http_404`/"Not Found" — never `not_found`/"Client not found.")."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")

    response = client.delete(f"{_ADMIN_CLIENTS_PATH}/adkc_totally-unregistered")

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Client not found."


def test_admin_revoke_requires_session(tmp_engine: Engine) -> None:
    """No admin session cookie -> 401 §9 envelope `auth_required`. RED today: 404, not 401."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.delete(f"{_ADMIN_CLIENTS_PATH}/adkc_whatever")

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "auth_required"


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------


def test_openapi_has_revoke_and_admin_operations(tmp_engine: Engine) -> None:
    """`/openapi.json` lists `oauth_revoke`/`oauth_clients_list`/`oauth_client_revoke`, and
    `components.schemas` carries `ConnectedApp`/`ConnectedAppsResponse` — CONVENTIONS.md §5's
    "every route has a stable unique operation_id", codegen-visible for both frontend apps
    (task-08 brief acceptance: "task 09 can `components['schemas']['ConnectedApp']`"). RED today:
    all three operation ids and both schemas are absent from the baseline.

    Fix round 1 (review M-5, assertion added by the controller): `/oauth/revoke`'s 200 response
    declares no `content` — the route actually returns a bodyless `Response`
    (`response_class=Response` on the decorator), so the OpenAPI document must not claim an
    `"application/json"` body a generated client's `.json()` call would choke on."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    spec = response.json()
    operation_ids = {
        operation.get("operationId")
        for methods in spec["paths"].values()
        for operation in methods.values()
    }
    assert "oauth_revoke" in operation_ids
    assert "oauth_clients_list" in operation_ids
    assert "oauth_client_revoke" in operation_ids

    schemas = spec["components"]["schemas"]
    assert "ConnectedApp" in schemas
    assert "ConnectedAppsResponse" in schemas

    assert "content" not in spec["paths"]["/api/v1/oauth/revoke"]["post"]["responses"]["200"]
