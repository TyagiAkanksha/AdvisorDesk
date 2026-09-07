"""Failing (RED) tests for the MCP `WWW-Authenticate` 401 challenge + bearer audience rule
(mcp-oauth plan, task 03).

Task brief: docs/plans/mcp-oauth/task-03-mcp-challenge-audience.md. Spec: DESIGN.md
§"Security / threat model" (audience binding) + RFC 9728 §5.1 (the challenge this file pins,
`WWW-Authenticate: Bearer resource_metadata="<issuer>/.well-known/oauth-protected-resource"`).

Today (pre-task-03) `app.services.errors.AppError` carries no `headers`, so nothing on any 401
response path — MCP or REST — ever sets `WWW-Authenticate`; `app.auth.tokens.resolve_bearer_token`
has no audience check at all (a token's `client_id`/`resource` columns exist since task 01 but are
never read), and it never stamps `ApiToken.last_used_at`. Every header-asserting test below is RED
for the SAME underlying reason (the header is simply absent from the response), and every
audience-rule test below is RED because today's `resolve_bearer_token` accepts a
wrong-audience/null-resource token that task 03's rule must reject — see each test's own
docstring for which failure mode it exercises today, and this file's test-author report for the
literal RED command output.

Two tests are expected to pass ALREADY, by accident of today's behavior, and are kept as
regression guards rather than dropped: `test_cli_token_null_resource_accepted` (a
`client_id=None, resource=None` token is already legacy-compatible with no audience check at all
— task 03's rule must keep accepting it, not merely happen to today) and
`test_rest_401_has_no_www_authenticate` (a REST 401 has never carried this header and must keep
not carrying it — the challenge is MCP-only per DESIGN.md's resource-server bullets).

The exact header string this file pins — `'Bearer resource_metadata="https://api.example/
.well-known/oauth-protected-resource"'` for `oauth_issuer_url="https://api.example"` — is built
by `_expected_www_authenticate` below from plain string formatting, never by calling
`app.auth.oauth_discovery.www_authenticate_challenge` (the function GREEN's implementation is
expected to call): the assertion must not trust the code it is meant to gate.

CONVENTIONS.md §10: every DB-touching test below requests `tmp_engine`/`db_session`, skipped by
fixture name when `TEST_DATABASE_URL` is unset; three tests need no database at all (the
no-credentials, malformed-bearer, live-settings, and REST-401 cases all fail — or, for REST, would
succeed — before any DB lookup is possible) and are written DB-less, mirroring
`tests/test_mcp_bearer_auth.py`'s own split between DB-less and `tmp_engine`-backed tests.
`auth_helpers.FakeGoogleOAuthClient`/`login_as` is the only mocked collaborator, matching every
other MCP test module.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.tokens import mint_token
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User
from app.models.api_tokens import ApiToken
from app.models.oauth import OAuthClient

_MCP_PATH = "/api/v1/mcp"
_ME_PATH = "/api/v1/auth/me"
# Streamable HTTP requires both of these on Accept or the transport 406s before ever reaching
# auth/dispatch — copied from `test_mcp_bearer_auth.py` (kept local per that file's own
# no-cross-test-file-dependency precedent).
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

#: The issuer every test in this file builds its `Settings` with unless it says otherwise —
#: `_expected_www_authenticate` and the two literal resource URLs below are all pinned relative
#: to this one value.
_ISSUER = "https://api.example"
#: RFC 8707 resource indicator that MATCHES `_ISSUER` (`Settings.mcp_resource_url` = `{issuer}/
#: api/v1/mcp`, task 01) — an OAuth-issued token scoped to this resource must be accepted.
_RIGHT_RESOURCE = "https://api.example/api/v1/mcp"
#: A resource indicator for a DIFFERENT protected resource entirely — any token scoped to this
#: must be rejected, regardless of `client_id`.
_WRONG_RESOURCE = "https://other.example/api/v1/mcp"


def _expected_www_authenticate(issuer: str) -> str:
    """Build the RFC 9728 §5.1 challenge string by hand — never via
    `app.auth.oauth_discovery.www_authenticate_challenge`, so this assertion never trusts the
    code under test."""
    return f'Bearer resource_metadata="{issuer}/.well-known/oauth-protected-resource"'


_EXPECTED_WWW_AUTHENTICATE = _expected_www_authenticate(_ISSUER)


def _build_settings(
    *, admin_emails: str = "admin@example.com", oauth_issuer_url: str = _ISSUER
) -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10).

    Always `mcp_http_enabled=True` (this file has no "disabled" state to pin, mirroring
    `test_mcp_bearer_auth.py`'s own `_build_settings`); `oauth_issuer_url` defaults to `_ISSUER`
    so `_EXPECTED_WWW_AUTHENTICATE` and `_RIGHT_RESOURCE`/`_WRONG_RESOURCE` stay valid for every
    test that doesn't override it.
    """
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        mcp_http_enabled=True,
        oauth_issuer_url=oauth_issuer_url,
    )


def _build_app(
    tmp_engine: Engine,
    *,
    admin_emails: str = "admin@example.com",
    oauth_issuer_url: str = _ISSUER,
) -> FastAPI:
    """Build a real, DB-backed app with MCP HTTP enabled (copied from
    `test_mcp_bearer_auth.py::_build_app`, `oauth_issuer_url` passthrough added)."""
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails, oauth_issuer_url=oauth_issuer_url),
        oauth_client=FakeGoogleOAuthClient(),
    )


def _insert_bearer_token(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    client_id: str | None,
    resource: str | None,
    name: str = "audience-test-token",
) -> str:
    """Insert a fresh `User` (+ an `OAuthClient` row when `client_id` is given, satisfying
    `api_tokens.client_id`'s FK) and one `ApiToken` scoped by `(client_id, resource)`, returning
    the raw bearer value.

    `session_epoch` is stamped to the fresh owner's own current value (0) and `expires_at` a
    comfortably future timestamp, exactly as `test_mcp_bearer_auth.py`'s own token-insert helpers
    do — so `client_id`/`resource` are the ONLY variable under test; expiry/revocation are never
    the reason one of these calls resolves or doesn't.
    """
    session = session_factory()
    try:
        owner = User(email=email, name="Audience Test Owner")
        session.add(owner)
        session.flush()
        if client_id is not None:
            session.add(
                OAuthClient(
                    client_id=client_id,
                    client_name="Audience Test Client",
                    redirect_uris=["https://example.com/callback"],
                )
            )
            session.flush()
        raw, token_hash = mint_token()
        session.add(
            ApiToken(
                user_id=owner.id,
                token_hash=token_hash,
                name=name,
                client_id=client_id,
                resource=resource,
                session_epoch=owner.session_epoch,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        session.commit()
        return raw
    finally:
        session.close()


# ---------------------------------------------------------------------------
# The three unauthenticated-MCP paths (no credentials, malformed bearer, unknown bearer, stale
# cookie) must all carry the challenge header.
# ---------------------------------------------------------------------------


def test_no_credentials_401_carries_www_authenticate() -> None:
    """POST `/api/v1/mcp` with neither a cookie nor an `Authorization` header must 401 with the
    RFC 9728 challenge. DB-less: `require_admin`'s missing-cookie branch (`app/auth/deps.py`)
    raises before any session-factory/DB access, exactly like `test_mcp_bearer_auth.py::
    test_no_credentials_returns_401_envelope`. RED today: `AuthRequiredError` carries no
    `headers`, so the response has no `WWW-Authenticate` at all."""
    app = create_app(settings=_build_settings())
    client = TestClient(app)

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert response.headers.get("www-authenticate") == _EXPECTED_WWW_AUTHENTICATE


def test_malformed_bearer_401_carries_www_authenticate() -> None:
    """An `Authorization: Bearer` header with an empty value is malformed
    (`_extract_bearer_token`'s three-way split, `app/mcp/server.py`) and must 401 with the
    challenge. DB-less: the malformed branch raises directly from `_extract_bearer_token`,
    before any DB access. RED today: same missing-`headers` reason as above."""
    app = create_app(settings=_build_settings())
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": "Bearer"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert response.headers.get("www-authenticate") == _EXPECTED_WWW_AUTHENTICATE


def test_unknown_bearer_401_carries_www_authenticate(tmp_engine: Engine) -> None:
    """A syntactically well-formed but unknown bearer token must 401 with the challenge. Needs a
    real `tmp_engine`-backed app (unlike the two DB-less cases above): a well-formed `Bearer`
    value routes into `_resolve_bearer_principal`, which requires `app.state.session_factory` to
    exist at all (a DB-less app raises `RuntimeError` here instead of 401). RED today: same
    missing-`headers` reason."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": "Bearer adk_nope"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert response.headers.get("www-authenticate") == _EXPECTED_WWW_AUTHENTICATE


def test_stale_cookie_401_carries_www_authenticate(tmp_engine: Engine, db_session: Session) -> None:
    """A session cookie whose owner's `session_epoch` has since moved (mirrors
    `require_admin`'s cookie-epoch-stale branch, `app/auth/deps.py`) must 401 with the challenge
    too — the cookie path's `_require_admin_with_challenge` wrapper (task-03 GREEN) must attach
    the SAME header the bearer paths get, not merely re-raise `require_admin`'s headerless
    `AuthRequiredError`. RED today: same missing-`headers` reason."""
    email = "stale-cookie-challenge@example.com"
    app = _build_app(tmp_engine, admin_emails=email)
    client = TestClient(app)
    login_as(client, email)

    owner = db_session.execute(select(User).where(User.email == email)).scalar_one()
    owner.session_epoch += 1
    db_session.commit()

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert response.headers.get("www-authenticate") == _EXPECTED_WWW_AUTHENTICATE


# ---------------------------------------------------------------------------
# The audience rule (RFC 8707): a `client_id IS NOT NULL` token must match
# `settings.mcp_resource_url` exactly; a `client_id IS NULL` token accepts `NULL` or a match.
# ---------------------------------------------------------------------------


def test_oauth_token_wrong_audience_rejected(tmp_engine: Engine) -> None:
    """An OAuth-issued token (`client_id` set) scoped to a DIFFERENT resource must 401 with the
    challenge, even though its owner is allowlisted and the token is otherwise fully valid. RED
    today: `resolve_bearer_token` never reads `client_id`/`resource` at all, so this token
    resolves and the call succeeds (2xx) instead of 401 — a real behavioral mismatch, not just a
    missing header."""
    email = "wrong-audience@example.com"
    app = _build_app(tmp_engine, admin_emails=email)
    raw = _insert_bearer_token(
        make_session_factory(tmp_engine),
        email=email,
        client_id="client-wrong-audience",
        resource=_WRONG_RESOURCE,
    )
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert response.headers.get("www-authenticate") == _EXPECTED_WWW_AUTHENTICATE


def test_oauth_token_right_audience_accepted(tmp_engine: Engine) -> None:
    """An OAuth-issued token scoped to EXACTLY `settings.mcp_resource_url` must succeed —
    the audience rule's accept side, not just its reject side. This should already pass today
    (nothing rejects a matching resource), but is written here as the paired positive case
    alongside `test_oauth_token_wrong_audience_rejected` so a future regression on the accept
    side (e.g. an overly strict rewrite) is caught too."""
    email = "right-audience@example.com"
    app = _build_app(tmp_engine, admin_emails=email)
    raw = _insert_bearer_token(
        make_session_factory(tmp_engine),
        email=email,
        client_id="client-right-audience",
        resource=_RIGHT_RESOURCE,
    )
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code < 400, response.text
    assert "result" in response.json()


def test_cli_token_null_resource_accepted(tmp_engine: Engine) -> None:
    """A legacy CLI-minted token (`client_id IS NULL`, `resource IS NULL`) must keep
    authenticating — the audience rule's explicit legacy-compatibility carve-out (Global
    Constraints: "a token with `client_id IS NULL` ... must have `resource IS NULL OR resource ==
    settings.mcp_resource_url`"). Expected to ALREADY pass today (nothing checks audience yet) —
    kept as a regression guard so task 03's GREEN implementation cannot accidentally start
    rejecting every pre-migration-0007 token."""
    email = "cli-null-resource@example.com"
    app = _build_app(tmp_engine, admin_emails=email)
    raw = _insert_bearer_token(
        make_session_factory(tmp_engine),
        email=email,
        client_id=None,
        resource=None,
    )
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code < 400, response.text


def test_cli_token_wrong_resource_rejected(tmp_engine: Engine) -> None:
    """A `client_id IS NULL` token whose `resource` is set to a DIFFERENT resource (not `NULL`,
    not a match) must 401 with the challenge — the Global Constraints table's "anything else ->
    401" clause applied to the CLI-token half of the rule. RED today: `resolve_bearer_token`
    never reads `resource` at all, so this succeeds (2xx) instead of 401."""
    email = "cli-wrong-resource@example.com"
    app = _build_app(tmp_engine, admin_emails=email)
    raw = _insert_bearer_token(
        make_session_factory(tmp_engine),
        email=email,
        client_id=None,
        resource=_WRONG_RESOURCE,
    )
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert response.headers.get("www-authenticate") == _EXPECTED_WWW_AUTHENTICATE


def test_oauth_token_null_resource_rejected(tmp_engine: Engine) -> None:
    """An OAuth-issued token (`client_id` set) whose `resource` is `NULL` must 401 with the
    challenge — the Global Constraints table's `client_id IS NOT NULL` branch requires an EXACT
    match, with no `NULL`-is-ok carve-out (that carve-out is only for the `client_id IS NULL`
    side, per `test_cli_token_null_resource_accepted`). RED today: `resolve_bearer_token` never
    reads `client_id`/`resource`, so this succeeds (2xx) instead of 401."""
    email = "oauth-null-resource@example.com"
    app = _build_app(tmp_engine, admin_emails=email)
    raw = _insert_bearer_token(
        make_session_factory(tmp_engine),
        email=email,
        client_id="client-null-resource",
        resource=None,
    )
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert response.headers.get("www-authenticate") == _EXPECTED_WWW_AUTHENTICATE


# ---------------------------------------------------------------------------
# `last_used_at` stamping on a successful resolve.
# ---------------------------------------------------------------------------


def test_successful_resolve_stamps_last_used_at(tmp_engine: Engine) -> None:
    """A successful bearer resolve (2xx `initialize`) must stamp `ApiToken.last_used_at`,
    committed by the MCP gate (not the service — the brief's "the CALLER commits" rule). Re-reads
    the row through a BRAND NEW session (never the one used to insert it) after the call, so a
    stale identity map can't produce a false pass — mirrors task-01's own
    `test_deleting_client_cascades_to_dependents`'s "the identity map doesn't know" caution, using
    a fresh session instead of `expire_all()` since the inserting session is already closed by the
    time the HTTP call runs. RED today: nothing in `resolve_bearer_token` ever writes
    `last_used_at`, so it stays `NULL` forever."""
    email = "stamps-last-used-at@example.com"
    app = _build_app(tmp_engine, admin_emails=email)
    session_factory = make_session_factory(tmp_engine)
    raw = _insert_bearer_token(
        session_factory,
        email=email,
        client_id=None,
        resource=None,
    )
    token_hash = hashlib.sha256(raw.encode()).hexdigest()

    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}
    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)
    assert response.status_code < 400, response.text

    verify_session = session_factory()
    try:
        token_row = verify_session.execute(
            select(ApiToken).where(ApiToken.token_hash == token_hash)
        ).scalar_one()
        assert token_row.last_used_at is not None
    finally:
        verify_session.close()


# ---------------------------------------------------------------------------
# The challenge header always reflects the LIVE `Settings`, and only the MCP endpoint carries it.
# ---------------------------------------------------------------------------


def test_www_authenticate_uses_live_settings() -> None:
    """Mutating `app.state.settings.oauth_issuer_url` AFTER the app is built must change the
    `WWW-Authenticate` value on the very next request — mirrors `test_bearer_expiry_allowlist.py`
    mutating `client.app.state.settings.admin_emails` live, applied here to `oauth_issuer_url`
    instead. DB-less: the no-credentials path never touches the database. RED today: same
    missing-`headers` reason as every other header test in this file — there is no header to
    reflect anything, live or not."""
    app = create_app(settings=_build_settings())
    client = TestClient(app)
    new_issuer = "https://issuer-two.example"
    client.app.state.settings.oauth_issuer_url = new_issuer  # type: ignore[attr-defined]

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == _expected_www_authenticate(new_issuer)


def test_rest_401_has_no_www_authenticate() -> None:
    """A REST 401 (`GET /api/v1/auth/me` with no cookie) must NOT carry `WWW-Authenticate` — the
    challenge is MCP-only (DESIGN.md's resource-server bullets scope it to the MCP endpoint; a
    REST client has no use for an OAuth-protected-resource pointer). DB-less: `require_admin`'s
    missing-cookie branch raises before any DB access. Expected to ALREADY pass today (there is no
    header anywhere yet) — kept as a regression guard so task 03's GREEN implementation, which
    touches the SHARED `AppError`/`_make_handler` header-forwarding plumbing, cannot accidentally
    leak the MCP-only header onto every other route's 401 too."""
    app = create_app(settings=_build_settings())
    client = TestClient(app)

    response = client.get(_ME_PATH)

    assert response.status_code == 401
    assert "www-authenticate" not in response.headers
