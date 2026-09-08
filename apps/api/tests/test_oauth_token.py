"""Failing (RED) tests for `POST /api/v1/oauth/token` (mcp-oauth plan, task 07): the
authorization-code grant (with PKCE), refresh-token rotation, and reuse detection.

Task brief: docs/plans/mcp-oauth/task-07-token-refresh-rotation.md. Spec:
docs/plans/mcp-oauth/DESIGN.md §"End-to-end flow" steps 7-8, §"Token & data model", §"Security /
threat model" (rotation, reuse, audience), §"Decisions pinned" (lifetimes); RFC 6749 §4.1.3/§4.1.4
(code grant), §6 (refresh grant); RFC 7636 (PKCE); RFC 8707 (resource indicators).

Today `app.routes.oauth_routes` declares only `POST /register`, `GET /authorize`, and
`GET /authorize/continue` (tasks 04/05) — there is no `/token` route at all, so every request this
file posts to `/api/v1/oauth/token` 404s at the Starlette router, rendered as the generic §9
`http_404` envelope (`app.routes.errors._http_exception_handler`) rather than the bare
`{"error": "...", "error_description": "..."}` OAuth shape this file pins throughout. That 404
happens BEFORE any form-body parsing, so this file's RED does not depend on `python-multipart`
being installed yet (task brief: it isn't) — a nonexistent route never reaches the point where
FastAPI would need it to decode `Form(...)` fields. No not-yet-existing module is imported at
module scope: every collaborator this file imports (`app.models.oauth`, `app.models.api_tokens`,
`app.services.token_hashing`, `tests.oauth_helpers.complete_authorization`) already exists as of
task 05/t01 — only `app.services.oauth_tokens` and the `/token` ROUTE itself are new this task, and
this file never imports the former, driving everything through the HTTP surface instead. So this
module collects cleanly and every test fails at ASSERTION time (a 404 where a 200/400/401/429 was
expected), never at collection.

CONVENTIONS.md §10: every test below requests `tmp_engine`/`db_session` (skipped by fixture name
when `TEST_DATABASE_URL` is unset). `_build_app`/`_build_settings` mirror `tests/
test_oauth_authorize.py`'s own shape exactly (same `_ISSUER`/`_RESOURCE`/rate-limit-override
pattern). Every `/token` exchange in this file is driven through the shared `tests/
oauth_helpers.py::complete_authorization` seam (register -> authorize -> Google-bridge login ->
continue -> a real, redeemable `adkac_` code) rather than hand-rolling a code — the same seam task
06/08/10 will reuse.

Ambiguity note (test-author decision): the controller's dispatch referenced
`app.services.tokens.hash_token`; the actual module (verified against the real source, and
against `tests/test_oauth_authorize.py`'s own import) is `app.services.token_hashing.hash_token`.
This file imports the real name.

Per-test notes for the less self-explanatory cases:

- `test_token_rate_limited` mirrors `test_oauth_authorize.py::test_authorize_rate_limited`'s own
  isolation trick exactly: the redeemable code is obtained via `complete_authorization` against a
  SEPARATE app/limiter instance (default 30/min) sharing the same `tmp_engine`/schema, so that
  setup traffic never consumes the tight `oauth_rate_limit_per_min=1` budget the app-under-test is
  built with — only the two `/token` POSTs against the tight-limit client do. `check_oauth_request`
  runs before any grant-type dispatch (task brief's route pseudocode), so the second POST 429s
  before its own (by-then-already-consumed) code is ever inspected again. Per the controller's
  dispatch, a 429 on `/oauth/*` carries the repo's §9 `ErrorEnvelope`
  (`{"error": {"code": "rate_limited", ...}}`) — NOT the bare OAuth `{"error": "..."}` string
  shape `OAuthError` itself renders; `RateLimitedError` is a plain `AppError`, not an `OAuthError`.
- `test_non_ascii_verifier_is_invalid_grant` / `test_short_ascii_verifier_is_invalid_grant` are the
  t05 review M-3 carry-over: `app.services.pkce.verify_s256` calls `.encode("ascii")` on the
  verifier and would raise `UnicodeEncodeError` on non-ASCII input if it were ever reached with one
  — the brief's own pinned `consume_authorization_code` check order
  (`not is_valid_code_verifier(...) or not verify_s256(...)`) short-circuits before `verify_s256`
  ever runs for a verifier that already fails the regex (both a non-ASCII and a too-short verifier
  do), so a CORRECT implementation never actually exercises the crash through this path. These
  tests still pin the OBSERVABLE contract at the API boundary — 400 `invalid_grant`, never a 500 —
  precisely so an implementation that gets the order wrong (or calls `verify_s256` from a second,
  unguarded path) is caught by a real assertion failure (500 vs. 400) rather than silently passing.
  Both also assert the code survives unconsumed and a subsequent correct redemption still succeeds,
  mirroring `test_wrong_verifier_invalid_grant`'s own non-consumption pin.
- FK behavior (t01 carry-over, `OAuthRefreshToken.access_token_id`/`rotated_from_id` both
  `ondelete="SET NULL"`) is tested separately in `tests/test_oauth_token_fk.py` — pure ORM/DB,
  no HTTP, no dependency on this task's route. Both of ITS tests are expected to ALREADY PASS
  today: migration 0007 (task 01) already created those constraints; see that file's own docstring.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from auth_helpers import FakeGoogleOAuthClient
from fastapi import FastAPI
from fastapi.testclient import TestClient
from oauth_helpers import AuthorizationResult, complete_authorization
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User
from app.models.api_tokens import ApiToken
from app.models.oauth import OAuthAuthorizationCode, OAuthRefreshToken
from app.services.token_hashing import hash_token

_ISSUER = "https://api.example"
#: The MCP resource indicator for `_ISSUER` (`Settings.mcp_resource_url`, mcp-oauth task 01) —
#: identical value `tests/oauth_helpers.py`'s own `_RESOURCE` module constant hardcodes, since
#: every app this file builds shares the same `oauth_issuer_url`.
_RESOURCE = f"{_ISSUER}/api/v1/mcp"
_MCP_PATH = "/api/v1/mcp"
_TOKEN_PATH = "/api/v1/oauth/token"
_REGISTER_PATH = "/api/v1/oauth/register"

#: Streamable HTTP requires both of these on Accept or the transport 406s before ever reaching
#: auth/dispatch — copied from `tests/test_mcp_bearer_auth.py`/`tests/test_oauth_authorize.py`
#: (kept local per those files' own no-cross-test-file-dependency precedent).
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
    test_oauth_authorize.py::_build_app` exactly.
    """
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=settings if settings is not None else _build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )


def _register_client(client: TestClient, redirect_uri: str) -> str:
    """Register a second OAuth client (`POST /oauth/register`) against `redirect_uri`; return its
    `client_id` — used by the wrong-client tests below, which need a REAL, registered-but-wrong
    client id (an unregistered one would hit the earlier `invalid_client`/401 branch instead of
    the `invalid_grant` branch these tests pin)."""
    response = client.post(_REGISTER_PATH, json={"redirect_uris": [redirect_uri]})
    assert response.status_code == 201, response.text
    client_id: str = response.json()["client_id"]
    return client_id


def _exchange(
    client: TestClient, result: AuthorizationResult, **overrides: str | None
) -> httpx.Response:
    """POST a code-grant `/token` request built from `result`, with any `overrides` applied.

    An override set to `None` OMITS that form field entirely (mirrors `test_oauth_authorize.py::
    _authorize_params`'s identical convention) — matching the route's `Annotated[str | None,
    Form()] = None` field shape, where an absent field reads back as `None`, not empty string.
    """
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": result.code,
        "redirect_uri": result.redirect_uri,
        "code_verifier": result.code_verifier,
        "client_id": result.client_id,
        "resource": _RESOURCE,
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
    """POST a refresh-grant `/token` request for `refresh_token`/`client_id`, with `overrides`
    applied the same way `_exchange` applies them."""
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
    """POST an MCP `initialize` call authenticated with `access_token` as a bearer header."""
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {access_token}"}
    return client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)


# ---------------------------------------------------------------------------
# The full Connect: code grant happy path, ending in a working MCP call.
# ---------------------------------------------------------------------------


def test_code_grant_happy_path_and_mcp_round_trip(tmp_engine: Engine, db_session: Session) -> None:
    """A valid code grant mints a working `adk_`/`adkr_` pair, no-store headers, and a minted
    access token that actually opens `/api/v1/mcp` — the full register -> authorize -> login ->
    code -> token -> MCP Connect this task's acceptance criterion names.

    RED today: `/token` doesn't exist -> 404, not 200; `response.json()["access_token"]` raises
    `KeyError` before any DB assertion runs.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result)

    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("pragma") == "no-cache"
    body = response.json()
    assert set(body.keys()) == {
        "access_token",
        "token_type",
        "expires_in",
        "refresh_token",
        "scope",
    }
    assert body["access_token"].startswith("adk_")
    assert body["refresh_token"].startswith("adkr_")
    assert body["expires_in"] == 3600
    assert body["scope"] == "mcp"
    assert body["token_type"] == "Bearer"

    mcp_response = _mcp_initialize(client, body["access_token"])
    assert mcp_response.status_code < 400, mcp_response.text

    code_row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    assert code_row.consumed_at is not None

    access_row = db_session.execute(
        select(ApiToken).where(ApiToken.token_hash == hash_token(body["access_token"]))
    ).scalar_one()
    assert access_row.client_id == result.client_id
    assert access_row.resource == _RESOURCE
    assert access_row.name == f"oauth:{result.client_id}"
    owner = db_session.get(User, code_row.user_id)
    assert owner is not None
    assert access_row.session_epoch == owner.session_epoch
    assert access_row.expires_at is not None
    access_ttl = (access_row.expires_at - access_row.created_at).total_seconds()
    assert 3590 <= access_ttl <= 3610

    refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(
            OAuthRefreshToken.token_hash == hash_token(body["refresh_token"])
        )
    ).scalar_one()
    assert refresh_row.family_id == code_row.id
    assert refresh_row.access_token_id == access_row.id
    assert refresh_row.token_hash == hash_token(body["refresh_token"])
    refresh_ttl = (refresh_row.expires_at - refresh_row.created_at).total_seconds()
    assert 30 * 86400 - 10 <= refresh_ttl <= 30 * 86400 + 10


# ---------------------------------------------------------------------------
# Code-grant failure modes
# ---------------------------------------------------------------------------


def test_wrong_verifier_invalid_grant(tmp_engine: Engine, db_session: Session) -> None:
    """A well-formed but WRONG `code_verifier` (doesn't hash to the code's `code_challenge`) is
    400 `invalid_grant` "PKCE verification failed." — and (task brief's own pinned decision) the
    code is left UNCONSUMED, unlike a replay. RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, code_verifier="a" * 43)

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "invalid_grant"
    assert body["error_description"] == "PKCE verification failed."

    code_row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    assert code_row.consumed_at is None


def test_redirect_mismatch_invalid_grant(tmp_engine: Engine) -> None:
    """A `redirect_uri` not matching the one recorded on the code is 400 `invalid_grant` (RFC 6749
    §4.1.3's exact-match requirement). RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, redirect_uri="https://claude.ai/api/mcp/other_callback")

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"


def test_wrong_client_invalid_grant(tmp_engine: Engine) -> None:
    """A DIFFERENT, but validly registered, `client_id` presenting someone else's code is 400
    `invalid_grant` — distinct from the 401 `invalid_client` an UNREGISTERED id gets. RED today:
    404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)
    other_client_id = _register_client(client, result.redirect_uri)

    response = _exchange(client, result, client_id=other_client_id)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"


def test_unknown_client_401_invalid_client(tmp_engine: Engine) -> None:
    """A `client_id` that was never registered at all is 401 `invalid_client` — checked before any
    grant-type-specific field, per the task brief's own pinned route order. RED today: 404, not
    401."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, client_id="adkc_totally-unregistered")

    assert response.status_code == 401, response.text
    assert response.json()["error"] == "invalid_client"


def test_missing_grant_type_invalid_request(tmp_engine: Engine) -> None:
    """An absent `grant_type` is 400 `invalid_request` — checked before even the client_id lookup.
    RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, grant_type=None)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"


def test_unsupported_grant_type(tmp_engine: Engine) -> None:
    """A `grant_type` other than `authorization_code`/`refresh_token` is 400
    `unsupported_grant_type`. RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, grant_type="client_credentials")

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "unsupported_grant_type"


def test_missing_code_invalid_request(tmp_engine: Engine) -> None:
    """An `authorization_code` grant missing `code` is 400 `invalid_request`. RED today: 404, not
    400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, code=None)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"


def test_expired_code_invalid_grant(tmp_engine: Engine, db_session: Session) -> None:
    """A code whose `expires_at` has already passed is 400 `invalid_grant`, even though it was
    never consumed. RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    code_row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    code_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    response = _exchange(client, result)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"


def test_code_replay_kills_issued_tokens(
    tmp_engine: Engine, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """Replaying an already-consumed code is 400 `invalid_grant` "Authorization code already
    used." AND kills every token that first (successful) exchange minted: the access token 401s at
    MCP, and the refresh row is revoked. Also pins the WARNING log line (`reason=code-replay`)
    never carries the raw code/token values. RED today: BOTH exchanges 404 identically (no 200 to
    even set up the replay), so `first.json()["access_token"]` raises `KeyError`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    first = _exchange(client, result)
    assert first.status_code == 200, first.text
    access_token = first.json()["access_token"]
    refresh_token = first.json()["refresh_token"]

    with caplog.at_level(logging.WARNING):
        second = _exchange(client, result)

    assert second.status_code == 400, second.text
    body = second.json()
    assert body["error"] == "invalid_grant"
    assert body["error_description"] == "Authorization code already used."

    mcp_response = _mcp_initialize(client, access_token)
    assert mcp_response.status_code == 401, mcp_response.text

    db_session.expire_all()
    refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(refresh_token))
    ).scalar_one()
    assert refresh_row.revoked_at is not None

    matches = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "code-replay" in record.getMessage().lower()
    ]
    assert matches, [record.getMessage() for record in caplog.records]
    assert result.code not in caplog.text
    assert access_token not in caplog.text
    assert refresh_token not in caplog.text


def test_resource_mismatch_invalid_target(tmp_engine: Engine) -> None:
    """A `resource` other than the one the code was authorized for is 400 `invalid_target` (RFC
    8707). RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, resource="https://other.example/api/v1/mcp")

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_target"


def test_absent_resource_defaults_to_canonical(tmp_engine: Engine) -> None:
    """Omitting `resource` entirely still succeeds — the route defaults it to
    `settings.mcp_resource_url`, which is exactly what the code itself was authorized for. RED
    today: 404, not 200."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, resource=None)

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# PKCE robustness carry-over (t05 review M-3)
# ---------------------------------------------------------------------------


def test_non_ascii_verifier_is_invalid_grant(tmp_engine: Engine, db_session: Session) -> None:
    """A non-ASCII `code_verifier` must answer 400 `invalid_grant`, never a 500 — module
    docstring's carry-over note. The code is left unconsumed, and a subsequent CORRECT redemption
    still succeeds. RED today: 404, not 400 (and not yet provably not-a-500 either, since the
    route doesn't exist to crash)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, code_verifier="ü" * 43)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"

    code_row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    assert code_row.consumed_at is None

    retry = _exchange(client, result)
    assert retry.status_code == 200, retry.text


def test_short_ascii_verifier_is_invalid_grant(tmp_engine: Engine, db_session: Session) -> None:
    """A well-formed-ASCII but too-short (RFC 7636 §4.1 requires 43-128 chars) `code_verifier` is
    also 400 `invalid_grant`, never a 500. Same non-consumption + successful-retry pins as the
    non-ASCII case above. RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _exchange(client, result, code_verifier="short-code")

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"

    code_row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    assert code_row.consumed_at is None

    retry = _exchange(client, result)
    assert retry.status_code == 200, retry.text


# ---------------------------------------------------------------------------
# Refresh grant: rotation, reuse, and the remaining failure modes
# ---------------------------------------------------------------------------


def test_refresh_happy_path_rotates(tmp_engine: Engine, db_session: Session) -> None:
    """A refresh grant mints a NEW access+refresh pair, revokes the OLD refresh row, chains
    `rotated_from_id`/`family_id`, and inherits the remaining expiry window verbatim. The OLD
    access token stops working at MCP; the NEW one works. RED today: 404, not 200 — both the
    initial code exchange AND the refresh call fail identically."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    first = _exchange(client, result)
    assert first.status_code == 200, first.text
    old_access = first.json()["access_token"]
    old_refresh = first.json()["refresh_token"]

    old_refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(old_refresh))
    ).scalar_one()
    old_refresh_id = old_refresh_row.id
    old_family_id = old_refresh_row.family_id
    old_expires_at = old_refresh_row.expires_at

    response = _refresh(client, old_refresh, result.client_id)

    assert response.status_code == 200, response.text
    body = response.json()
    new_access = body["access_token"]
    new_refresh = body["refresh_token"]
    assert new_access != old_access
    assert new_refresh != old_refresh

    db_session.expire_all()
    revoked_old_row = db_session.get(OAuthRefreshToken, old_refresh_id)
    assert revoked_old_row is not None
    assert revoked_old_row.revoked_at is not None

    new_refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(new_refresh))
    ).scalar_one()
    assert new_refresh_row.rotated_from_id == old_refresh_id
    assert new_refresh_row.family_id == old_family_id
    assert abs((new_refresh_row.expires_at - old_expires_at).total_seconds()) < 1

    old_mcp = _mcp_initialize(client, old_access)
    assert old_mcp.status_code == 401, old_mcp.text
    new_mcp = _mcp_initialize(client, new_access)
    assert new_mcp.status_code < 400, new_mcp.text


def test_refresh_reuse_revokes_family(
    tmp_engine: Engine, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """Presenting an ALREADY-ROTATED (and therefore revoked) refresh token again is 400
    `invalid_grant` "Refresh token has been revoked." AND kills the ENTIRE rotation family: the
    newest refresh row is revoked too, and the newest access token 401s at MCP. Also pins the
    WARNING log line (`reason=refresh-reuse`) never carries either raw refresh-token value. RED
    today: 404 at every step (initial exchange, rotation, and the reuse attempt)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    first = _exchange(client, result)
    assert first.status_code == 200, first.text
    old_refresh = first.json()["refresh_token"]

    rotate_response = _refresh(client, old_refresh, result.client_id)
    assert rotate_response.status_code == 200, rotate_response.text
    new_access = rotate_response.json()["access_token"]
    new_refresh = rotate_response.json()["refresh_token"]

    with caplog.at_level(logging.WARNING):
        reuse_response = _refresh(client, old_refresh, result.client_id)

    assert reuse_response.status_code == 400, reuse_response.text
    body = reuse_response.json()
    assert body["error"] == "invalid_grant"
    assert body["error_description"] == "Refresh token has been revoked."

    db_session.expire_all()
    new_refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(new_refresh))
    ).scalar_one()
    assert new_refresh_row.revoked_at is not None

    family_rows = (
        db_session.execute(
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.family_id == new_refresh_row.family_id
            )
        )
        .scalars()
        .all()
    )
    assert len(family_rows) >= 2
    assert all(row.revoked_at is not None for row in family_rows)

    new_mcp = _mcp_initialize(client, new_access)
    assert new_mcp.status_code == 401, new_mcp.text

    matches = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "refresh-reuse" in record.getMessage().lower()
    ]
    assert matches, [record.getMessage() for record in caplog.records]
    assert old_refresh not in caplog.text
    assert new_refresh not in caplog.text


def test_refresh_expired_invalid_grant(tmp_engine: Engine, db_session: Session) -> None:
    """A refresh token whose `expires_at` has already passed is 400 `invalid_grant`. RED today:
    404 at both the initial exchange and the refresh attempt."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    first = _exchange(client, result)
    assert first.status_code == 200, first.text
    refresh_token = first.json()["refresh_token"]

    refresh_row = db_session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_token(refresh_token))
    ).scalar_one()
    refresh_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    response = _refresh(client, refresh_token, result.client_id)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"


def test_refresh_wrong_client_invalid_grant(tmp_engine: Engine) -> None:
    """A DIFFERENT, but validly registered, `client_id` presenting someone else's refresh token is
    400 `invalid_grant`. RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    first = _exchange(client, result)
    assert first.status_code == 200, first.text
    refresh_token = first.json()["refresh_token"]
    other_client_id = _register_client(client, result.redirect_uri)

    response = _refresh(client, refresh_token, other_client_id)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"


def test_refresh_resource_mismatch_invalid_target(tmp_engine: Engine) -> None:
    """A `resource` other than the refresh token's original grant is 400 `invalid_target`. RED
    today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    first = _exchange(client, result)
    assert first.status_code == 200, first.text
    refresh_token = first.json()["refresh_token"]

    response = _refresh(
        client, refresh_token, result.client_id, resource="https://other.example/api/v1/mcp"
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_target"


def test_refresh_scope_escalation_invalid_scope(tmp_engine: Engine) -> None:
    """A `scope` exceeding the refresh token's original grant is 400 `invalid_scope`. RED today:
    404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    first = _exchange(client, result)
    assert first.status_code == 200, first.text
    refresh_token = first.json()["refresh_token"]

    response = _refresh(client, refresh_token, result.client_id, scope="admin")

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_scope"


def test_refresh_unknown_token_invalid_grant(tmp_engine: Engine) -> None:
    """A syntactically-plausible but unknown refresh token, presented against a real registered
    client, is 400 `invalid_grant`. RED today: 404, not 400."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    result = complete_authorization(client)

    response = _refresh(client, "adkr_totally-unknown-value", result.client_id)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"


# ---------------------------------------------------------------------------
# Rate limiting, OpenAPI
# ---------------------------------------------------------------------------


def test_token_rate_limited(tmp_engine: Engine) -> None:
    """`oauth_rate_limit_per_min=1`: the second `/token` call from the same IP 429s, with the §9
    `ErrorEnvelope` shape (not the bare OAuth error shape) — module docstring's per-test note. RED
    today: both calls 404 identically (the tight-limit app's own `/token` doesn't exist either),
    so neither reaches 429."""
    setup_app = _build_app(tmp_engine)
    result = complete_authorization(TestClient(setup_app))

    app = _build_app(tmp_engine, settings=_build_settings(oauth_rate_limit_per_min=1))
    client = TestClient(app)

    first = _exchange(client, result)
    assert first.status_code != 429, first.text

    second = _exchange(client, result)

    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "rate_limited"


def test_openapi_has_token_operation(tmp_engine: Engine) -> None:
    """`/openapi.json` lists the new `oauth_token` `operation_id` — CONVENTIONS.md §5's "every
    route has a stable unique operation_id", codegen-visible for both frontend apps. RED today:
    `oauth_token` is absent from the baseline."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    operation_ids = {
        operation.get("operationId")
        for methods in response.json()["paths"].values()
        for operation in methods.values()
    }
    assert "oauth_token" in operation_ids
