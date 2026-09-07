"""Failing (RED) tests for MCP bearer-token auth (phase-6 task-04 Step 1).

Task brief: docs/plans/phase-6-deployment/task-04-mcp-bearer-auth.md, Step 1.
Spec: advisordesk-prd.md §3 (MCP exposure), §9 (auth security).

The mounted `/api/v1/mcp` endpoint must accept EITHER the existing admin session cookie OR an
`Authorization: Bearer <token>` header minted by a not-yet-existing script, so a deployed Claude
connector (which can send a header but never a cookie) can call it. Today `app.auth.tokens` and
`app.models.api_tokens` do not exist at all, and `_AdminGatedMcpApp.__call__`
(`app/mcp/server.py`) only ever checks the cookie via `require_admin`, silently ignoring any
`Authorization` header. `GET /api/v1/mcp` also does not yet 405 (the bare-path `Route` has no
`methods=` restriction today, so an unauthenticated GET reaches `require_admin` and gets 401).

Deliberate RED-mode split (mirrors `test_mcp_exposure.py`'s own "collect cleanly, fail on
behavior" preference over a blanket import error, applied per-test here): every new interface
this task's implementer must add (`app.auth.tokens.mint_token`/`resolve_bearer_token`,
`app.models.api_tokens.ApiToken`, `scripts/mint_mcp_token.py`) is imported LOCALLY inside only
the test functions that need it, never at module scope. This keeps the three genuine regression
pins (no-credentials-401, cookie-still-works, and the mint_token-format pin needs no DB/app at
all) collecting and running today exactly as before, while every bearer-specific test fails for
one of two reasons: `ModuleNotFoundError`/`ImportError` (the new module doesn't exist yet), or a
real status-code mismatch (`GET` gets 401 today, not 405; a bad bearer alongside a valid cookie
gets 2xx today via silent fall-through, not the pinned no-fall-through 401) — see this file's RED
evidence in the test-author report for the itemized list of which test hits which failure mode.

INTERFACE ASSUMPTIONS beyond the brief's Interfaces section (test-author decisions, binding on
the implementer per the controller's brief — flagged here AND in the report for adjudication):
  - `scripts/mint_mcp_token.py` exposes two plain, DB-session-taking functions (not just a CLI
    `main()`) so this file can drive them directly: `mint(session: Session, *, email: str, name:
    str) -> str` (returns the raw token; raises `LookupError` for an unknown OR soft-deleted
    email — the brief's CLI-level "error message + exit 1" collapses to this at the function
    level) and `revoke(session: Session, token_id: uuid.UUID) -> None` (hard-deletes the
    `ApiToken` row; raises `LookupError` for an unknown id). The brief pins only the CLI flags,
    not these names/signatures/exception type.
  - Whether `mint`/`revoke` commit their own transaction internally is left open by the brief;
    tests that use them always call `session.commit()` themselves right after, defensively, so
    the assertions that follow work regardless of which way the implementer decides that.

CONVENTIONS.md §10: every DB-touching test below requests `tmp_engine`, skipped by fixture name
when `TEST_DATABASE_URL` is unset. `auth_helpers.FakeGoogleOAuthClient`/`login_as` is the only
mocked collaborator, matching every other MCP test module.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import Content, User

_MCP_PATH = "/api/v1/mcp"
_MCP_MOUNT_PATH = _MCP_PATH + "/"
# Streamable HTTP requires both of these on Accept or the transport 406s before ever reaching
# auth/dispatch — see `mcp.server.streamable_http.StreamableHTTPServerTransport
# ._validate_accept_header`. Copied from `test_mcp_exposure.py` (kept local per that file's own
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

# task-01 (search_content, count_content) + task-02 (create_draft, edit_content,
# delete_content, tag_content, publish, archive) + phase-7 task-01 (report_content_gaps) —
# the full registry as of this task.
_EXPECTED_TOOL_NAMES = {
    "search_content",
    "count_content",
    "create_draft",
    "edit_content",
    "delete_content",
    "tag_content",
    "publish",
    "archive",
    "report_content_gaps",
}

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _build_settings(*, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10).

    Always `mcp_http_enabled=True`: unlike `test_mcp_exposure.py`, this file has no
    "disabled" state to pin.

    Phase-6 remediation task-09 (WR-02 residual, data-only fixture fix): `admin_emails` is now
    overridable (default unchanged, `"admin@example.com"`) so a bearer-only test can allowlist its
    own token owner — `resolve_bearer_token` now re-checks the resolved user's email against the
    CURRENT `ADMIN_EMAILS` on every resolve, so a token minted for a user this file's fixture never
    allowlisted no longer authenticates purely by accident of that mismatch.
    """
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        mcp_http_enabled=True,
    )


def _build_app(tmp_engine: Engine, *, admin_emails: str = "admin@example.com") -> FastAPI:
    """Build a real, DB-backed app with MCP HTTP enabled — the shape every DB-touching test here
    shares."""
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
        oauth_client=FakeGoogleOAuthClient(),
    )


def _import_mint_script() -> object:
    """Import `scripts/mint_mcp_token.py` by inserting `scripts/` onto `sys.path`.

    `scripts/` is not an installed package (no `__init__.py`; `[tool.hatch.build.targets.wheel]`
    only declares `packages = ["app"]`) — this mirrors how pytest's own rootless "prepend" import
    mode already makes `tests/auth_helpers.py` importable as bare `auth_helpers` (every MCP test
    module's `from auth_helpers import ...`), rather than requiring a `scripts/__init__.py`
    addition (package-structure app code, out of a test-author's remit here).

    Called lazily, inside each test that needs it, so a missing `scripts/mint_mcp_token.py`
    (true today) raises `ModuleNotFoundError` only for THOSE tests, not at collection time for
    the whole file (see module docstring).
    """
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import mint_mcp_token

    return mint_mcp_token


# ---------------------------------------------------------------------------
# Regression pins: the existing cookie gate, and the route's unauth/method shape
# ---------------------------------------------------------------------------


def test_no_credentials_returns_401_envelope() -> None:
    """No cookie, no bearer -> 401 envelope. Already true today (`require_admin`'s
    missing-cookie branch) and must stay true — DB-less, mirrors `test_mcp_exposure.py`."""
    app = create_app(settings=_build_settings())
    client = TestClient(app)

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "auth_required"


def test_session_cookie_still_works_initialize_round_trip(tmp_engine: Engine) -> None:
    """The existing admin-session-cookie path must keep working unchanged once bearer auth is
    added — one `initialize` round-trip, mirroring `test_mcp_exposure.py`'s state-3 pin."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code < 400, (
        f"expected a non-4xx/non-5xx (2xx) response, got {response.status_code}: {response.text}"
    )


def test_get_mcp_returns_405() -> None:
    """§3 phase-5 final-review t01-M8 fix: `GET /api/v1/mcp` is 405 (method not allowed at the
    routing layer), not a 401 from `require_admin` — Starlette answers this before auth ever
    runs, so this is DB-less. RED today: the bare-path `Route` has no `methods=` restriction, so
    an unauthenticated GET reaches `require_admin` and gets 401 instead."""
    app = create_app(settings=_build_settings())
    client = TestClient(app)

    response = client.get(_MCP_PATH, headers=_MCP_HEADERS)

    assert response.status_code == 405
    assert "POST" in response.headers.get("allow", "")


# ---------------------------------------------------------------------------
# Bearer happy path
# ---------------------------------------------------------------------------


def test_bearer_token_initialize_succeeds_and_tools_list_returns_nine_tools(
    tmp_engine: Engine,
) -> None:
    """A minted bearer token opens the MCP endpoint with NO cookie at all: `initialize` succeeds
    and `tools/list` enumerates the full 9-tool registry, exactly as a cookie-authenticated caller
    sees. RED today: `app.auth.tokens` doesn't exist, so `mint_token()` raises
    `ModuleNotFoundError` before any HTTP call happens."""
    from app.auth.tokens import mint_token
    from app.models.api_tokens import ApiToken

    app = _build_app(tmp_engine, admin_emails="connector@example.com")
    session = make_session_factory(tmp_engine)()
    try:
        owner = User(email="connector@example.com", name="Claude Connector")
        session.add(owner)
        session.flush()
        raw, token_hash = mint_token()
        session.add(ApiToken(user_id=owner.id, token_hash=token_hash, name="ci-connector"))
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}

    init_response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)
    assert init_response.status_code < 400, (
        f"expected 2xx, got {init_response.status_code}: {init_response.text}"
    )

    list_body = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    list_response = client.post(_MCP_MOUNT_PATH, json=list_body, headers=headers)
    assert list_response.status_code < 400, list_response.text
    tool_names = {tool["name"] for tool in list_response.json()["result"]["tools"]}
    assert tool_names == _EXPECTED_TOOL_NAMES


def test_write_tool_via_bearer_stamps_token_owner_as_actor(tmp_engine: Engine) -> None:
    """PRD §4.1: a write tool invoked over bearer auth stamps the token's OWNING user as the
    acting admin — `create_draft`'s `author_id`/`updated_by`, verified via a fresh row read (row
    evidence), not just the tool's own return payload. RED today: same `mint_token`
    `ModuleNotFoundError` as above."""
    from app.auth.tokens import mint_token
    from app.models.api_tokens import ApiToken

    app = _build_app(tmp_engine, admin_emails="connector@example.com")
    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email="connector@example.com", name="Claude Connector")
        session.add(owner)
        session.flush()
        owner_id = owner.id
        raw, token_hash = mint_token()
        session.add(ApiToken(user_id=owner_id, token_hash=token_hash, name="ci-connector"))
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}
    call_body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "create_draft", "arguments": {"title": "Bearer-Authored Draft"}},
    }

    response = client.post(_MCP_MOUNT_PATH, json=call_body, headers=headers)
    assert response.status_code < 400, response.text
    payload = response.json()
    assert payload["result"]["isError"] is False, payload
    result = json.loads(payload["result"]["content"][0]["text"])

    verify_session = session_factory()
    try:
        content = verify_session.get(Content, uuid.UUID(result["id"]))
        assert content is not None
        assert content.author_id == owner_id
        assert content.updated_by == owner_id
    finally:
        verify_session.close()


# ---------------------------------------------------------------------------
# Bearer failure modes — including the no-fall-through pin
# ---------------------------------------------------------------------------


def test_unknown_garbage_bearer_returns_401(tmp_engine: Engine) -> None:
    """A syntactically-plausible but unknown bearer token, with no cookie, must 401 — real DB
    lookup (a real `tmp_engine`, not a DB-less app), so this exercises the actual
    `resolve_bearer_token` query path once it exists, not just today's "header ignored"
    behavior."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": "Bearer adk_not-a-real-token"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_bearer_for_soft_deleted_user_returns_401(tmp_engine: Engine) -> None:
    """A token minted for a user who is since soft-deleted must stop authenticating — mirrors
    `require_admin`'s own re-check-every-request rule (PRD §9), now for the bearer path too
    (`resolve_bearer_token` must load the owner via `get_active_user`). RED today: `mint_token`
    `ModuleNotFoundError`."""
    from app.auth.tokens import mint_token
    from app.models.api_tokens import ApiToken

    app = _build_app(tmp_engine)
    session = make_session_factory(tmp_engine)()
    try:
        owner = User(email="departed@example.com", name="Former Admin", is_deleted=True)
        session.add(owner)
        session.flush()
        raw, token_hash = mint_token()
        session.add(ApiToken(user_id=owner.id, token_hash=token_hash, name="stale"))
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_bad_bearer_with_valid_cookie_present_still_401_no_fallthrough(
    tmp_engine: Engine,
) -> None:
    """The brief's gate-order pin: an `Authorization: Bearer` header that fails to resolve must
    401 even when a VALID session cookie is also present on the same request — no falling
    through to the cookie path once a bearer header was offered. RED today: the current gate
    ignores `Authorization` entirely, so this request actually succeeds (2xx) via the valid
    cookie alone, the opposite of the pinned behavior."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")

    headers = {**_MCP_HEADERS, "Authorization": "Bearer garbage-token-value"}
    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


# ---------------------------------------------------------------------------
# mint_token() format pin
# ---------------------------------------------------------------------------


def test_mint_token_format_pin_raw_prefix_and_sha256_hash() -> None:
    """`mint_token()`'s exact contract (brief Interfaces): raw starts `"adk_"`; hash is the sha256
    hex digest of raw. Pure function — no app, no DB. RED today: `app.auth.tokens` doesn't
    exist."""
    from app.auth.tokens import mint_token

    raw, token_hash = mint_token()

    assert raw.startswith("adk_")
    assert token_hash == hashlib.sha256(raw.encode()).hexdigest()


def test_api_tokens_table_stores_only_hash_never_raw(tmp_engine: Engine) -> None:
    """A minted token's raw string must never appear in any `api_tokens` row — only its hash.
    RED today: `app.models.api_tokens` doesn't exist (also: no migration creates the table)."""
    from app.auth.tokens import mint_token
    from app.models.api_tokens import ApiToken

    session = make_session_factory(tmp_engine)()
    try:
        owner = User(email="connector@example.com", name="Claude Connector")
        session.add(owner)
        session.flush()
        raw, token_hash = mint_token()
        session.add(ApiToken(user_id=owner.id, token_hash=token_hash, name="ci-connector"))
        session.commit()

        rows = session.execute(select(ApiToken)).scalars().all()
        assert len(rows) == 1
        assert rows[0].token_hash == token_hash
        assert all(row.token_hash != raw for row in rows)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# scripts/mint_mcp_token.py behaviors (via its importable functions — see module docstring's
# "INTERFACE ASSUMPTIONS" for the `mint`/`revoke` signatures this section pins)
# ---------------------------------------------------------------------------


def test_script_mint_unknown_email_raises(tmp_engine: Engine) -> None:
    """Minting for an email with no matching `User` row fails loudly rather than silently
    creating a dangling token. RED today: `scripts/mint_mcp_token.py` doesn't exist
    (`ModuleNotFoundError`)."""
    mint_mcp_token = _import_mint_script()
    session = make_session_factory(tmp_engine)()
    try:
        with pytest.raises(LookupError):
            mint_mcp_token.mint(session, email="nobody@example.com", name="ci")
    finally:
        session.close()


def test_script_mint_soft_deleted_email_raises(tmp_engine: Engine) -> None:
    """Minting for a soft-deleted user's email fails the same way as an unknown one (the brief's
    "resolves the ACTIVE user" — a soft-deleted row is not active). RED today: same
    `ModuleNotFoundError`."""
    mint_mcp_token = _import_mint_script()
    session = make_session_factory(tmp_engine)()
    try:
        user = User(email="departed@example.com", name="Former Admin", is_deleted=True)
        session.add(user)
        session.commit()

        with pytest.raises(LookupError):
            mint_mcp_token.mint(session, email="departed@example.com", name="ci")
    finally:
        session.close()


def test_script_revoke_deletes_row_and_stops_authenticating(tmp_engine: Engine) -> None:
    """Revocation is immediate and real: the `ApiToken` row is hard-deleted, and a bearer call
    that succeeded with the token before revoke gets 401 afterward. RED today: same
    `ModuleNotFoundError` (also: `ApiToken` doesn't exist, needed to look up the minted row's
    id)."""
    mint_mcp_token = _import_mint_script()
    from app.models.api_tokens import ApiToken

    app = _build_app(tmp_engine, admin_emails="connector@example.com")
    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email="connector@example.com", name="Claude Connector")
        session.add(owner)
        session.commit()
        raw = mint_mcp_token.mint(session, email="connector@example.com", name="ci-revoke")
        session.commit()  # defensive: covers both a self-committing and a non-committing `mint`
    finally:
        session.close()

    client = TestClient(app)
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}
    pre_revoke = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)
    assert pre_revoke.status_code < 400, (
        f"setup assumption failed: a freshly minted token should authenticate before revoke, "
        f"got {pre_revoke.status_code}: {pre_revoke.text}"
    )

    lookup_session = session_factory()
    try:
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        token_row = lookup_session.execute(
            select(ApiToken).where(ApiToken.token_hash == token_hash)
        ).scalar_one()
        token_id = token_row.id
    finally:
        lookup_session.close()

    revoke_session = session_factory()
    try:
        mint_mcp_token.revoke(revoke_session, token_id)
        revoke_session.commit()  # defensive, see mint()'s own commit note above
    finally:
        revoke_session.close()

    verify_session: Session = session_factory()
    try:
        assert verify_session.get(ApiToken, token_id) is None
    finally:
        verify_session.close()

    post_revoke = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)
    assert post_revoke.status_code == 401
    assert post_revoke.json()["error"]["code"] == "auth_required"
