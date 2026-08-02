"""Failing (RED) tests for the §3 MCP HTTP-exposure rule (task-01 Step 5).

Task brief: docs/plans/phase-5-mcp-agent/task-01-mcp-server-read-tools.md,
Step 5. PRD §3: "Exposing the MCP server over HTTP (for external MCP
clients) is OFF by default (`MCP_HTTP_ENABLED=false`); if enabled, the MCP
route requires the same admin session auth as §5.2." Controller pin: the
route is mounted at `/api/v1/mcp`.

Deliberately imports NOTHING from `app.mcp` — unlike `test_mcp_read_tools.py`
(which exercises the in-process `call_tool` seam directly and so fails at
collection with `ModuleNotFoundError` until `app.mcp.runtime` exists), this
file is "precisely about HTTP" (brief): it only needs `app.factory.create_app`
and a `TestClient`, so it collects cleanly today and instead fails on real
HTTP-behavior assertions (binding rule 3) — `app/factory.py` does not yet
mount anything at `/api/v1/mcp` under any `Settings`, so:

  - `test_mcp_route_absent_with_default_settings` already PASSES today
    (the route is absent under every current `Settings`, by construction)
    — a permanent, both-before-and-after-implementation invariant, not RED
    itself; the other two tests below are what makes this module's overall
    `pytest` run RED.
  - `test_mcp_route_unauthenticated_returns_401_envelope_when_enabled` FAILS
    today: it asserts 401, but gets 404 (the route doesn't exist yet).
  - `test_mcp_route_reachable_with_admin_session_when_enabled` FAILS today:
    it asserts a non-4xx/non-5xx status, but gets 404.

CONVENTIONS.md §10: the one test needing a real login (`login_as`, which
calls `/api/v1/auth/callback`) requests `tmp_engine`, and is skipped by
fixture name when `TEST_DATABASE_URL` is unset; the other two are DB-less
(`app.factory.create_app()`'s own CONVENTIONS.md §5 contract: it must
succeed with no database) and always run. The fake Google OAuth client
(`auth_helpers.FakeGoogleOAuthClient`, driven via `login_as`) is the only
mocked collaborator, matching every other route-test module in this suite.
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app

_MCP_PATH = "/api/v1/mcp"

# A minimal, real MCP JSON-RPC "initialize" request — the first message any
# real MCP HTTP client sends (mcp.types.InitializeRequestParams requires
# exactly these three params: protocolVersion/capabilities/clientInfo).
# Used ONLY so a conformant transport (state 3 below) has something valid
# to accept; this file asserts nothing about the JSON-RPC response body or
# the negotiated protocol version — controller decision: "don't over-pin
# the MCP protocol body — pin reachability + auth gating only." The exact
# version string is an arbitrary, syntactically-valid one (the field is a
# free-form `str` in the SDK, not a closed enum) chosen so this test has no
# dependency on which `mcp` SDK version the implementer pins.
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
# Streamable HTTP (the SDK's default, non-JSON-only response mode) requires
# both of these on Accept, or the transport itself 406s before ever
# reaching `require_admin`/dispatch — see
# `mcp.server.streamable_http.StreamableHTTPServerTransport._validate_accept_header`.
_MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def _build_settings(*, mcp_http_enabled: bool, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10).

    `mcp_http_enabled` is always passed explicitly here (never left to
    `Settings`' own default) so this file's "disabled" vs. "enabled" states
    stay correct regardless of whatever a sourced `.env` happens to set for
    `MCP_HTTP_ENABLED` in the RED-evidence run (today: absent from `.env`,
    so `Settings()`'s bare default would agree anyway — this just doesn't
    depend on that staying true).
    """
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        mcp_http_enabled=mcp_http_enabled,
    )


# ---------------------------------------------------------------------------
# State 1: default settings -> route absent (404)
# ---------------------------------------------------------------------------


def test_mcp_route_absent_with_default_settings() -> None:
    """§3 pin, state 1: `MCP_HTTP_ENABLED=false` (the default) -> `/api/v1/mcp` does not exist.

    DB-less: this state needs no session/user, only that nothing was
    mounted at the path.
    """
    app = create_app(settings=_build_settings(mcp_http_enabled=False))
    client = TestClient(app)

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_404"


# ---------------------------------------------------------------------------
# State 2: enabled, no session -> route exists but 401s
# ---------------------------------------------------------------------------


def test_mcp_route_unauthenticated_returns_401_envelope_when_enabled() -> None:
    """§3 pin, state 2: enabled + no session -> the route exists but 401s with the §9 envelope
    (write surface unreachable unauthenticated).

    DB-less: `require_admin` raises `AuthRequiredError` from its
    missing-cookie branch alone, never touching `app.state.session_factory`
    (`app/auth/deps.py::require_admin`) — so this state needs no database
    either, only `mcp_http_enabled=True`.
    """
    app = create_app(settings=_build_settings(mcp_http_enabled=True))
    client = TestClient(app)

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "auth_required"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


# ---------------------------------------------------------------------------
# State 3: enabled, valid admin session -> reachable (non-4xx/non-5xx)
# ---------------------------------------------------------------------------


def test_mcp_route_reachable_with_admin_session_when_enabled(tmp_engine: Engine) -> None:
    """§3 pin, state 3: enabled + a valid admin session -> reachable, 2xx.

    Only this state needs a real database (`login_as` drives the real
    `/api/v1/auth/callback`, which reads/writes a `User` row).
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(mcp_http_enabled=True),
        oauth_client=FakeGoogleOAuthClient(),
    )
    client = TestClient(app)
    login_as(client, "admin@example.com")

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code < 400, (
        f"expected a non-4xx/non-5xx (2xx) response, got {response.status_code}: {response.text}"
    )
