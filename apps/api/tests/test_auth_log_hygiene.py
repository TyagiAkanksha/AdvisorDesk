"""Fix round 1 for task 6R-03 — review finding I1 (Important): two of the brief's five "never log"
classes had no test guard anywhere in the suite.

Review: `.superpowers/sdd/reports/p6r-t03-review.md`, §5 (mutation battery) + Important finding I1.
`tests/test_bearer_revocation.py` (pinned, untouched by this fix round) already pins absence for
two of design pin #4's five "never log" classes — the raw bearer token and the OAuth `state`
value. It does NOT pin absence for the remaining two reachable classes: the signed session cookie
value (logout's audit line) and the persisted token hash (all four bearer-resolution audit lines).
The review's mutation battery proved this gap is real, not theoretical: a mutant that appends
`cookie=%s` to the logout INFO line (M12), and a mutant that appends `hash=%s` to all four
`app.auth.tokens.resolve_bearer_token` lines (M13), both pass the entire 470/473-test suite
unmodified. This file closes exactly that gap — no application code changes with it.

Why these two classes matter more than the two already pinned: the signed session cookie is a
directly replayable, full-admin credential for the remainder of its 30-day lifetime (no further
compromise needed) if it ever reaches `docker logs` (WR-05's only forensic sink on this task's
target topology, per `p6-whole-repo-review.md:181-182` / `infra/deploy/ec2-single-host.md`); the
token hash is not directly replayable but is a persistent, secret-derived identifier the brief's
design pin #4 explicitly forbids logging.

Local helpers (`_build_settings`, `_build_client`, `_import_mint_script`, `_assert_hash_never_
logged`) are duplicated rather than imported from `tests/test_bearer_revocation.py` or `tests/
test_mcp_bearer_auth.py` — CONVENTIONS.md §10's established no-cross-test-file-import precedent,
already followed by `tests/test_metrics_fixes.py`, `tests/test_auth_hardening_fixes.py`, and
`tests/test_ratelimit_guards.py` for the same reason (fixer files may not depend on the internals
of a pinned file that a later fix round to THAT file could change out from under them).

Mutation-kill evidence (both mutants proven to bite, then the scratch edit reverted byte-clean —
never committed): recorded verbatim in `.superpowers/sdd/reports/p6r-t03-implementer.md`'s
"Fix round 1" section.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import sys
from pathlib import Path

import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.auth.sessions import COOKIE_NAME
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User

_MCP_PATH = "/api/v1/mcp"
_LOGOUT_PATH = "/api/v1/auth/logout"

# Copied from `test_mcp_bearer_auth.py`/`test_bearer_revocation.py` (kept local per those files'
# own no-cross-test-file-dependency precedent): Streamable HTTP 406s before ever reaching
# auth/dispatch without both of these on `Accept`.
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

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


# ---------------------------------------------------------------------------
# Local helpers (duplicated rather than shared/imported — see module docstring)
# ---------------------------------------------------------------------------


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
        mcp_http_enabled=True,
    )


def _build_client(
    tmp_engine: Engine,
    *,
    admin_emails: str = "admin@example.com",
    environment: str = "development",
) -> tuple[TestClient, FakeGoogleOAuthClient]:
    """Build a `TestClient` over a real, DB-backed, MCP-HTTP-enabled app with a fake OAuth seam."""
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails, environment=environment),
        oauth_client=oauth_client,
    )
    return TestClient(app), oauth_client


def _import_mint_script() -> object:
    """Import `scripts/mint_mcp_token.py` by inserting `scripts/` onto `sys.path` (it is not an
    installed package). Mirrors `tests/test_mcp_bearer_auth.py::_import_mint_script` exactly."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import mint_mcp_token

    return mint_mcp_token


def _assert_hash_never_logged(
    client: TestClient,
    headers: dict[str, str],
    raw_token: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Drive one MCP request with `headers` and assert `raw_token`'s sha256 hex digest — the ONLY
    form `app.auth.tokens.mint_token`/`ApiToken.token_hash` ever persists — appears in NO captured
    record, regardless of the outcome (resolved, or any rejection reason). Kills review finding
    I1/M13 (a mutant that adds `hash=%s` to all four `resolve_bearer_token` audit lines)."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)
    assert token_hash not in caplog.text


# ---------------------------------------------------------------------------
# The signed session cookie must never appear in any record across /auth/logout
# ---------------------------------------------------------------------------


def test_logout_never_logs_raw_session_cookie_value(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Kills review finding I1/M12: a mutant that appends `cookie=%s` (the raw signed session
    cookie value read straight off the request) to the `Logout: user_id=... epoch_bumped=...`
    INFO line passes every test in `test_bearer_revocation.py` — none of its 15 tests assert the
    cookie's absence, only the user id and `epoch_bumped` flag's presence. This test reads the
    real cookie value out of the client's own jar (the exact string a browser would send on the
    wire) before logging out, then asserts it is absent from every record captured during the
    logout call."""
    email = "log-hygiene-cookie@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)
    cookie_value = client.cookies.get(COOKIE_NAME)
    assert cookie_value

    with caplog.at_level(logging.INFO):
        response = client.post(_LOGOUT_PATH)

    assert response.status_code == 200
    assert cookie_value not in caplog.text


# ---------------------------------------------------------------------------
# The token hash must never appear in any record across all four bearer outcomes
# ---------------------------------------------------------------------------


def test_bearer_resolved_never_logs_token_hash(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 5 (bearer resolved) outcome of the shared hash-absence guard — see
    `_assert_hash_never_logged`."""
    mint_mcp_token = _import_mint_script()
    email = "log-hygiene-resolved@example.com"
    client, _ = _build_client(tmp_engine)

    session = make_session_factory(tmp_engine)()
    try:
        owner = User(email=email, name="Log Hygiene Resolved Owner")
        session.add(owner)
        session.commit()
        raw = mint_mcp_token.mint(session, email=email, name="log-hygiene-resolved")  # type: ignore[attr-defined]
        session.commit()
    finally:
        session.close()

    _assert_hash_never_logged(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}, raw, caplog
    )


def test_bearer_rejected_unknown_never_logs_token_hash(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 6, reason 'unknown' outcome of the shared hash-absence guard — see
    `_assert_hash_never_logged`."""
    client, _ = _build_client(tmp_engine)
    marker = "adk_LOG-HYGIENE-UNKNOWN-MARKER-" + secrets.token_hex(8)

    _assert_hash_never_logged(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {marker}"}, marker, caplog
    )


def test_bearer_rejected_revoked_never_logs_token_hash(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 6, reason 'revoked' outcome of the shared hash-absence guard — see
    `_assert_hash_never_logged`."""
    mint_mcp_token = _import_mint_script()
    email = "log-hygiene-revoked@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)

    session = make_session_factory(tmp_engine)()
    try:
        raw = mint_mcp_token.mint(session, email=email, name="log-hygiene-revoked")  # type: ignore[attr-defined]
        session.commit()
    finally:
        session.close()
    client.post(_LOGOUT_PATH)  # bumps session_epoch, revoking `raw`

    _assert_hash_never_logged(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}, raw, caplog
    )


def test_bearer_rejected_wrong_audience_never_logs_token_hash(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """mcp-oauth task 03 fix round 1, review finding M-4: the new `wrong-audience` reason
    (`app.auth.tokens.resolve_bearer_token`, mcp-oauth task 03) gets the same hash-absence guard
    as every other rejection reason in this file — see `_assert_hash_never_logged`.

    `wrong-audience` is only reachable via an OAuth-issued token (`client_id` set) scoped to the
    WRONG resource — `scripts/mint_mcp_token.py::mint` never sets `client_id` (see that function's
    own docstring: "this script mints directly for an admin, with no OAuth client in the
    picture"), so this test constructs the `OAuthClient`/`ApiToken` rows directly rather than
    going through `_import_mint_script()`/`mint()`, mirroring `tests/test_mcp_www_authenticate.py
    ::_insert_bearer_token`'s own construction (duplicated locally, not imported, per this file's
    own no-cross-test-file-dependency precedent — module docstring)."""
    from app.auth.tokens import mint_token
    from app.models.api_tokens import ApiToken
    from app.models.oauth import OAuthClient

    email = "log-hygiene-wrong-audience@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)

    session = make_session_factory(tmp_engine)()
    try:
        owner = User(email=email, name="Log Hygiene Wrong Audience Owner")
        session.add(owner)
        session.flush()
        session.add(
            OAuthClient(
                client_id="log-hygiene-wrong-audience-client",
                client_name="Log Hygiene Wrong Audience Client",
                redirect_uris=["https://example.com/callback"],
            )
        )
        session.flush()
        raw, token_hash = mint_token()
        session.add(
            ApiToken(
                user_id=owner.id,
                token_hash=token_hash,
                name="log-hygiene-wrong-audience",
                client_id="log-hygiene-wrong-audience-client",
                resource="https://other.example/api/v1/mcp",
                session_epoch=owner.session_epoch,
            )
        )
        session.commit()
    finally:
        session.close()

    _assert_hash_never_logged(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}, raw, caplog
    )


def test_bearer_rejected_inactive_user_never_logs_token_hash(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 6, reason 'inactive-user' outcome of the shared hash-absence guard — see
    `_assert_hash_never_logged`."""
    mint_mcp_token = _import_mint_script()
    email = "log-hygiene-inactive@example.com"
    client, _ = _build_client(tmp_engine)

    session = make_session_factory(tmp_engine)()
    try:
        owner = User(email=email, name="Log Hygiene Inactive Owner")
        session.add(owner)
        session.commit()
        raw = mint_mcp_token.mint(session, email=email, name="log-hygiene-inactive")  # type: ignore[attr-defined]
        session.commit()
        owner.is_deleted = True
        session.commit()
    finally:
        session.close()

    _assert_hash_never_logged(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}, raw, caplog
    )
