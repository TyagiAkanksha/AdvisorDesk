"""One narrative end-to-end test walking the full mcp-oauth Connect lifecycle in-process, plus two
OpenAPI coverage tests (mcp-oauth plan, task 10: docs/plans/mcp-oauth/task-10-wiring-e2e.md).

Spec: docs/plans/mcp-oauth/DESIGN.md §"End-to-end flow" (steps 1-8). This test's numbered
comments (1-12) follow the task-10 brief's own more granular breakdown of that same flow — the
brief's 12 steps expand DESIGN.md's 8 into: no-auth 401, RS metadata, AS metadata (parsed and
reused), DCR, authorize+login+consent, code exchange, first MCP call, refresh rotation (old token
dies), a SECOND authorize for the same client (consent remembered, no HTML hop), the admin
connected-apps list, admin revoke (client + cascade), and the CLI-mint fallback path surviving all
of the above untouched.

Per the task-10 brief's own Interfaces line ("the e2e test imports no app.* module except
Settings, create_app, the models for assertions, and hash_token"): every OAuth endpoint is driven
through HTTP only. `_build_settings`/`_build_app` are copied (not imported) from
`tests/test_oauth_token.py`, mirroring that file's and `tests/test_oauth_revoke_admin.py`'s own
established no-cross-test-file-import precedent. `tests.oauth_helpers.complete_authorization` is
importable (task-10 brief) but this narrative deliberately does NOT call it for the first
authorization: `complete_authorization` always drives `login_as` immediately after `/authorize`,
skipping past the interior "pending cookie present, no admin session yet -> 307 to
/api/v1/auth/login" hop this test's step 5 must observe directly. Everything from step 6 onward
(a second, already-consented authorize; a token exchange; a refresh) is hand-rolled the same way,
so every request past step 3 is built from the URLs this test itself parsed out of the
`/.well-known/oauth-authorization-server` response body — never a hardcoded path literal — proving
the discovery document is truthful, not merely internally consistent with itself (steps 3, 4, 5,
6, 8).

Rate-limit accounting (task-10 brief's "Facts the brief cannot know"): the default
`oauth_rate_limit_per_min=30` is a single per-IP budget shared across every `/oauth/*` call (the
admin `/oauth/clients...` router is a separate, session-gated surface with no such budget — see
`app.routes.oauth_admin_routes`, which never calls `RateLimiter.check_oauth_request`). This
narrative drives exactly 10 rate-limited `/oauth/*` calls: register (1), first authorize (2), the
pre-login continue (3), the post-login continue (4), the consent decision (5), the code exchange
(6), the refresh (7), the second authorize (8), the second continue (9), and the post-revoke
refresh attempt (10) — comfortably under the 30/min default, so this test keeps the production
default rather than overriding it (unlike several other mcp-oauth test files that deliberately
tighten it to provoke a 429).

Ambiguity note (test-author decision): `/.well-known/oauth-authorization-server`'s
`revocation_endpoint` is parsed alongside the other three endpoint URLs (task-10 brief step 3
names all four explicitly), but the brief's own 12 numbered steps never call RFC 7009's
`POST /revoke` — step 11's admin action is `DELETE /api/v1/oauth/clients/{client_id}`
(`oauth_client_revoke`), a different, already separately-tested route
(`tests/test_oauth_revoke_admin.py`). This test therefore only asserts `revocation_endpoint`
resolves to the expected path (proving that one field truthful too) rather than inventing an
un-itemized extra `/revoke` call into the narrative.
"""

from __future__ import annotations

import re
import secrets
import urllib.parse

import httpx
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User
from app.models.api_tokens import ApiToken
from app.services.token_hashing import hash_token

_ISSUER = "https://api.example"
_ADMIN_EMAIL = "admin@example.com"
_MCP_PATH = "/api/v1/mcp"
_REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"

#: RFC 7636 Appendix B's worked example: `S256(_CODE_VERIFIER) == _CODE_CHALLENGE` — reused
#: verbatim (mirrors `tests/oauth_helpers.py`'s own module constant) so this file needs no extra
#: crypto import.
_CODE_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
_CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

#: Streamable HTTP requires both of these on Accept or the transport 406s before ever reaching
#: auth/dispatch — copied from `tests/test_mcp_bearer_auth.py`/`tests/test_oauth_token.py` (kept
#: local per those files' own no-cross-test-file-dependency precedent).
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
_TOOLS_LIST_BODY = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

#: task-01 (search_content, count_content) + task-02 (create_draft, edit_content, delete_content,
#: tag_content, publish, archive) + phase-7 task-01 (report_content_gaps) + phase-9 task-15
#: (report_weak_queries) — the full registry, copied from
#: `tests/test_mcp_bearer_auth.py::_EXPECTED_TOOL_NAMES`.
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
    "report_weak_queries",
}

_EXPECTED_OAUTH_OPERATION_IDS = {
    "oauth_protected_resource_metadata",
    "oauth_protected_resource_metadata_mcp_path",
    "oauth_authorization_server_metadata",
    "oauth_register",
    "oauth_authorize",
    "oauth_authorize_continue",
    "oauth_authorize_decision",
    "oauth_token",
    "oauth_revoke",
    "oauth_clients_list",
    "oauth_client_revoke",
}


def _build_settings(*, oauth_rate_limit_per_min: int = 30) -> Settings:
    """Build a `Settings` explicitly for the test — never read the real `.env` (CONVENTIONS §10).

    Mirrors `tests/test_oauth_token.py::_build_settings`'s own shape exactly.
    """
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=_ADMIN_EMAIL,
        mcp_http_enabled=True,
        oauth_issuer_url=_ISSUER,
        oauth_rate_limit_per_min=oauth_rate_limit_per_min,
    )


def _build_app(tmp_engine: Engine) -> FastAPI:
    """Build a real, DB-backed app with a fake Google OAuth seam injected — mirrors `tests/
    test_oauth_token.py::_build_app`."""
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )


def _authorize_params(client_id: str, *, state: str) -> dict[str, str]:
    """A full, valid `/authorize` query dict for `client_id` — RFC 7636 Appendix B's vector,
    `resource` set to the canonical MCP resource URI for `_ISSUER`."""
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _REDIRECT_URI,
        "code_challenge": _CODE_CHALLENGE,
        "code_challenge_method": "S256",
        "scope": "mcp",
        "resource": f"{_ISSUER}/api/v1/mcp",
        "state": state,
    }


def _path(url: str) -> str:
    """Return the path component of a full discovery-metadata URL.

    Step 3's own point: every OAuth endpoint call past discovery uses the URL the metadata
    document itself advertised, not a hardcoded literal — proving the metadata is truthful.
    """
    return urllib.parse.urlsplit(url).path


def _redirect_query(location: str) -> dict[str, list[str]]:
    """Parse a redirect `Location`'s query string into `{name: [values]}`."""
    return urllib.parse.parse_qs(urllib.parse.urlsplit(location).query)


def _tools_list(client: TestClient, access_token: str) -> httpx.Response:
    """POST an MCP `tools/list` call authenticated with `access_token` as a bearer header."""
    headers = {**_MCP_HEADERS, "Authorization": f"Bearer {access_token}"}
    return client.post(_MCP_PATH, json=_TOOLS_LIST_BODY, headers=headers)


def _operation_ids(app: FastAPI) -> set[object]:
    """Fetch `/openapi.json` off a live `TestClient` and return its full set of operation ids."""
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    spec = response.json()
    return {
        operation.get("operationId")
        for methods in spec["paths"].values()
        for operation in methods.values()
    }


def test_full_connect_lifecycle(tmp_engine: Engine, db_session: Session) -> None:
    """Walk DESIGN.md's entire end-to-end flow once, in-process: no-auth 401 -> discovery -> DCR
    -> authorize/login/consent -> code exchange -> MCP tools/list -> refresh rotation ->
    consent-remembered re-authorize -> admin list/revoke -> CLI-mint fallback survives.

    Acceptance proof, not a defect: this test is expected GREEN on first run against the built
    t01-t09 branch (task-10 brief).
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    # 1. POST /api/v1/mcp with no credentials at all -> 401 + the exact RFC 9728 §5.1
    #    WWW-Authenticate challenge (DESIGN.md step 1).
    no_auth_response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)
    assert no_auth_response.status_code == 401, no_auth_response.text
    assert no_auth_response.json()["error"]["code"] == "auth_required"
    assert no_auth_response.headers["www-authenticate"] == (
        'Bearer resource_metadata="https://api.example/.well-known/oauth-protected-resource"'
    )

    # 2. GET /.well-known/oauth-protected-resource -> authorization_servers names our own issuer
    #    (DESIGN.md step 2).
    resource_metadata_response = client.get("/.well-known/oauth-protected-resource")
    assert resource_metadata_response.status_code == 200, resource_metadata_response.text
    resource_metadata = resource_metadata_response.json()
    assert resource_metadata["authorization_servers"] == [_ISSUER]
    assert resource_metadata["resource"] == f"{_ISSUER}/api/v1/mcp"

    # 3. GET /.well-known/oauth-authorization-server -> parse the real endpoint URLs out of the
    #    body and use THEM (path part) for every following OAuth call (DESIGN.md step 3).
    as_metadata_response = client.get("/.well-known/oauth-authorization-server")
    assert as_metadata_response.status_code == 200, as_metadata_response.text
    as_metadata = as_metadata_response.json()
    assert as_metadata["issuer"] == _ISSUER
    register_path = _path(as_metadata["registration_endpoint"])
    authorize_path = _path(as_metadata["authorization_endpoint"])
    token_path = _path(as_metadata["token_endpoint"])
    revoke_path = _path(as_metadata["revocation_endpoint"])
    assert revoke_path == "/api/v1/oauth/revoke"

    # 4. POST <registration_endpoint> (DCR) -> a fresh client_id (DESIGN.md step 4).
    register_response = client.post(
        register_path, json={"redirect_uris": [_REDIRECT_URI], "client_name": "Claude"}
    )
    assert register_response.status_code == 201, register_response.text
    client_id = register_response.json()["client_id"]

    # 5. Authorize -> 303 park; continue with no session yet -> 307 to the Google-login bridge;
    #    login_as; continue again -> 200 HTML consent (first time for this user/client pair);
    #    POST approve -> 302 with code + state (DESIGN.md steps 5-6).
    first_state = "state-1"
    authorize_response = client.get(
        authorize_path,
        params=_authorize_params(client_id, state=first_state),
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text

    continue_before_login = client.get("/api/v1/oauth/authorize/continue", follow_redirects=False)
    assert continue_before_login.status_code == 307, continue_before_login.text
    assert continue_before_login.headers["location"] == "/api/v1/auth/login"

    login_as(client, _ADMIN_EMAIL)

    consent_response = client.get("/api/v1/oauth/authorize/continue", follow_redirects=False)
    assert consent_response.status_code == 200, consent_response.text
    assert consent_response.headers["content-type"].startswith("text/html")
    nonce_match = re.search(r'name="nonce" value="([^"]+)"', consent_response.text)
    assert nonce_match is not None, consent_response.text

    decision_response = client.post(
        "/api/v1/oauth/authorize/decision",
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )
    assert decision_response.status_code == 302, decision_response.text
    first_redirect = _redirect_query(decision_response.headers["location"])
    code = first_redirect["code"][0]
    assert first_redirect["state"][0] == first_state

    # 6. POST <token_endpoint> (authorization_code grant) -> a working access + refresh pair
    #    (DESIGN.md step 7).
    exchange_response = client.post(
        token_path,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT_URI,
            "code_verifier": _CODE_VERIFIER,
            "client_id": client_id,
        },
    )
    assert exchange_response.status_code == 200, exchange_response.text
    tokens = exchange_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    assert access_token.startswith("adk_")
    assert refresh_token.startswith("adkr_")

    # 7. POST /api/v1/mcp tools/list with the access token -> 200 and exactly the registered
    #    tool set (DESIGN.md step 8).
    tools_response = _tools_list(client, access_token)
    assert tools_response.status_code == 200, tools_response.text
    tool_names = {tool["name"] for tool in tools_response.json()["result"]["tools"]}
    assert tool_names == _EXPECTED_TOOL_NAMES

    # 8. Refresh -> a new access/refresh pair; the OLD access token is hard-deleted (401 at MCP);
    #    the NEW access token still opens MCP, no user interaction (DESIGN.md step 8).
    refresh_response = client.post(
        token_path,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    )
    assert refresh_response.status_code == 200, refresh_response.text
    new_tokens = refresh_response.json()
    new_access_token = new_tokens["access_token"]
    assert new_access_token != access_token

    old_access_after_refresh = _tools_list(client, access_token)
    assert old_access_after_refresh.status_code == 401, old_access_after_refresh.text

    new_access_tools_response = _tools_list(client, new_access_token)
    assert new_access_tools_response.status_code == 200, new_access_tools_response.text

    # 9. A second /authorize for the SAME client -> continue answers 302 DIRECTLY (consent already
    #    on file for this user/client pair) — no HTML hop this time.
    second_state = "state-2"
    second_authorize_response = client.get(
        authorize_path,
        params=_authorize_params(client_id, state=second_state),
        follow_redirects=False,
    )
    assert second_authorize_response.status_code == 303, second_authorize_response.text

    second_continue_response = client.get(
        "/api/v1/oauth/authorize/continue", follow_redirects=False
    )
    assert second_continue_response.status_code == 302, second_continue_response.text
    second_redirect = _redirect_query(second_continue_response.headers["location"])
    assert second_redirect["state"][0] == second_state
    assert "code" in second_redirect

    # 10. Admin GET /api/v1/oauth/clients (the admin session cookie login_as minted at step 5 is
    #     still live on `client`) -> one item; live counts reflect the single surviving
    #     access/refresh pair from the step-8 rotation; last_used_at was already stamped by the
    #     step-8 tools/list call.
    admin_list_response = client.get("/api/v1/oauth/clients")
    assert admin_list_response.status_code == 200, admin_list_response.text
    items = admin_list_response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["client_id"] == client_id
    assert item["active_access_tokens"] == 1
    assert item["active_refresh_tokens"] == 1
    assert item["last_used_at"] is not None

    # 11. Admin DELETE the client -> 204; the access token 401s (WWW-Authenticate still present —
    #     the cascade-deleted ApiToken row now reads as "unknown"); the refresh token 401s
    #     invalid_client at the token endpoint (the client itself no longer exists).
    revoke_response = client.delete(f"/api/v1/oauth/clients/{client_id}")
    assert revoke_response.status_code == 204, revoke_response.text

    revoked_access_response = _tools_list(client, new_access_token)
    assert revoked_access_response.status_code == 401, revoked_access_response.text
    assert "resource_metadata=" in revoked_access_response.headers.get("www-authenticate", "")

    revoked_refresh_response = client.post(
        token_path,
        data={
            "grant_type": "refresh_token",
            "refresh_token": new_tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    assert revoked_refresh_response.status_code == 401, revoked_refresh_response.text
    assert revoked_refresh_response.json()["error"] == "invalid_client"

    # 12. The CLI-mint fallback path is untouched by any of the above: a bearer token minted the
    #     OLD way (no OAuth client at all — client_id=None, resource=None) still opens
    #     /api/v1/mcp (DESIGN.md non-goals: "CLI mint ... is kept as an ops/CI fallback").
    db_session.expire_all()
    admin_user = db_session.execute(select(User).where(User.email == _ADMIN_EMAIL)).scalar_one()
    raw_cli_token = f"adk_{secrets.token_urlsafe(32)}"
    db_session.add(
        ApiToken(
            user_id=admin_user.id,
            token_hash=hash_token(raw_cli_token),
            name="ci-cli-fallback",
            client_id=None,
            resource=None,
        )
    )
    db_session.commit()

    cli_fallback_response = _tools_list(client, raw_cli_token)
    assert cli_fallback_response.status_code == 200, cli_fallback_response.text


def test_openapi_lists_every_oauth_operation(tmp_engine: Engine) -> None:
    """`/openapi.json` lists every OAuth operation id this plan introduced, on a fully DB-backed
    app — CONVENTIONS.md §5's "every route has a stable unique operation_id"."""
    app = _build_app(tmp_engine)

    assert _EXPECTED_OAUTH_OPERATION_IDS <= _operation_ids(app)


def test_create_app_without_db_registers_oauth_routes() -> None:
    """`create_app()` with NO arguments (no DB, no settings, no oauth_client) — CONVENTIONS.md
    §5's "must succeed with no database and no env vars" — still registers every OAuth route: DCR,
    authorize, and the admin list/revoke routers are unconditional in `app.factory.create_app`,
    unlike the MCP HTTP mount itself, which stays gated on `mcp_http_enabled` (default `False`)."""
    app = create_app()

    assert _EXPECTED_OAUTH_OPERATION_IDS <= _operation_ids(app)
