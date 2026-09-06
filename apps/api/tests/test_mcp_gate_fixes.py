"""Fixer-owned tests for phase-6 task-04 review round 1, findings I1/M2/M3.

Review: `.superpowers/sdd/reports/p6-t04-review.md`. This file is NEW (not a pinned test file) —
`tests/test_mcp_bearer_auth.py` and `tests/test_metrics.py` are pinned and untouched by this round.

Findings covered here:
  - I1 (`app.mcp.server._extract_bearer_token`): a present-but-malformed `Authorization` header
    (empty/missing value, a bad separator, or a non-`bearer` scheme) used to return `None` and
    silently fall through to `require_admin`'s cookie path — so a bad bearer header alongside a
    valid session cookie authenticated via the cookie instead of 401ing, contradicting the
    task-04 brief's "a present bearer commits the caller to the bearer path, no fall-through"
    pin. Fixed: any present `Authorization` header must now either resolve to a live token or the
    whole request 401s, with no cookie fallback. The matrix below proves both directions: the
    malformed/unresolvable cases 401 despite a valid cookie, and a well-formed-but-differently-cased
    scheme (`bearer ...`, RFC 7235 case-insensitive) still authenticates given a valid token.
  - M2 (`app.mcp.server._AdminGatedMcpApp.__call__`): `GET`/`DELETE`/etc. through the `Mount`'s
    sub-paths (e.g. `/api/v1/mcp/`) reached the streamable-HTTP transport, which opens a
    standalone SSE stream and hangs indefinitely — the bare path's `methods=["POST"]` never
    covered the `Mount`. Fixed: `__call__` now rejects any non-POST method with a 405
    (`Allow: POST`) BEFORE the auth gate, so it's fast and DB-less for every non-POST method on
    every path this app is mounted at. Each hang-shaped test below is wrapped in
    `anyio.fail_after` (same "deterministic timeout ceiling, not an indefinite hang" pattern
    `test_mcp_http_transport.py`'s C1 regression test uses) so a regression fails fast with
    `TimeoutError` instead of freezing the run.
  - M3 (`app.routes.errors._http_exception_handler`): the `exc.headers`-forwarding change (needed
    so the M2/bare-path 405's `Allow: POST` survives the §9 envelope rebuild) had no test of its
    own — it was only exercised indirectly through the MCP module. Covered directly here: the
    bare-path 405 still carries `Allow: POST`; an arbitrary header-bearing `HTTPException` keeps
    both its headers AND the envelope body shape; and an ordinary 404 (no headers on the raised
    exception) is unaffected — no stray header leaks onto it.

CONVENTIONS.md §10: every DB-touching test below requests `tmp_engine`, skipped by fixture name
when `TEST_DATABASE_URL` is unset. `auth_helpers.FakeGoogleOAuthClient`/`login_as` is the only
mocked collaborator, matching every other MCP test module.
"""

from __future__ import annotations

import anyio
import httpx
import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User
from app.routes.errors import register_error_handlers

_MCP_PATH = "/api/v1/mcp"
_MCP_MOUNT_PATH = _MCP_PATH + "/"
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


def _build_settings(*, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10).

    Phase-6 remediation task-09 (WR-02 residual, data-only fixture fix): `admin_emails`
    overridable (default unchanged) — see `test_mcp_bearer_auth.py::_build_settings`'s identical
    rationale.
    """
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        mcp_http_enabled=True,
    )


def _build_app(tmp_engine: Engine, *, admin_emails: str = "admin@example.com") -> FastAPI:
    """Build a real, DB-backed app with MCP HTTP enabled — mirrors `test_mcp_bearer_auth.py`."""
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
        oauth_client=FakeGoogleOAuthClient(),
    )


# ---------------------------------------------------------------------------
# I1 — a present-but-malformed/unresolvable Authorization header never falls through to a
# coincidentally-valid session cookie
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header_value",
    [
        pytest.param("Bearer", id="bearer-alone-no-value"),
        pytest.param("Bearer ", id="bearer-empty-value"),
        pytest.param("Bearer\tadk_x", id="bearer-htab-separator"),
        pytest.param("Basic xyz", id="basic-scheme-present"),
        pytest.param("Bearer  adk_x", id="bearer-double-space-separator"),
        pytest.param("Bearer garbage-unresolvable-token", id="bearer-wellformed-unresolvable"),
    ],
)
def test_malformed_or_unresolvable_bearer_with_valid_cookie_401s_no_fallthrough(
    tmp_engine: Engine, header_value: str
) -> None:
    """The gate-order pin (task-04 brief), re-verified with a VALID admin session cookie also
    present: every one of these `Authorization` header shapes must 401, never silently fall back
    to authenticating via the cookie. Before the fix, the four parse-malformed cases (all but the
    last) returned `None` from `_extract_bearer_token` and authenticated via the cookie (2xx)."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")

    headers = {**_MCP_HEADERS, "Authorization": header_value}
    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401, (
        f"expected 401 for Authorization: {header_value!r}, got {response.status_code}: "
        f"{response.text}"
    )
    assert response.json()["error"]["code"] == "auth_required"


def test_case_insensitive_bearer_scheme_with_valid_token_still_authenticates(
    tmp_engine: Engine,
) -> None:
    """RFC 7235's scheme match is case-insensitive: `bearer <token>` (lowercase scheme) with a
    REAL, resolvable token must still authenticate — proves the I1 fix's stricter parsing did not
    also break the pre-existing case-insensitivity the implementer deliberately built in (review
    finding M6 flagged this as verified-but-unpinned). A valid session cookie is also present, to
    match the brief's "with a VALID session cookie present" matrix framing."""
    from app.auth.tokens import mint_token
    from app.models.api_tokens import ApiToken

    app = _build_app(tmp_engine, admin_emails="admin@example.com,connector@example.com")
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
    login_as(client, "admin@example.com")
    headers = {**_MCP_HEADERS, "Authorization": f"bearer {raw}"}

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code < 400, f"expected 2xx, got {response.status_code}: {response.text}"


def test_absent_authorization_header_with_valid_cookie_still_200_regression(
    tmp_engine: Engine,
) -> None:
    """Regression: with NO `Authorization` header at all, a valid session cookie must keep
    authenticating exactly as before — the only case that still falls through to `require_admin`.
    Already pinned indirectly by `test_mcp_bearer_auth.py::test_session_cookie_still_works_...`;
    reproduced here as the explicit fourth leg of the I1 matrix."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")

    response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code < 400, f"expected 2xx, got {response.status_code}: {response.text}"


# ---------------------------------------------------------------------------
# M2 — a non-POST method on the MOUNT path (trailing-slash sub-paths) 405s fast, never hangs
# ---------------------------------------------------------------------------

# anyio.fail_after ceiling: bounds each test deterministically. Before the fix, the exact
# request shape below reached the streamable-HTTP transport and opened a standalone SSE stream
# that never completed — the review's own probe was killed at 120s. A regression here raises
# `TimeoutError` well before that, instead of freezing the whole test run.
_M2_TIMEOUT_CEILING = 10.0


@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("with_cookie", [False, True], ids=["unauthenticated", "with-valid-cookie"])
def test_mount_path_non_post_method_405s_fast_no_hang(
    tmp_engine: Engine, method: str, with_cookie: bool
) -> None:
    """`GET`/`DELETE /api/v1/mcp/` (the `Mount` path, trailing slash) must answer 405 with
    `Allow: POST` immediately, both unauthenticated and with a valid admin session cookie — never
    reach the streamable-HTTP transport. Before the fix, this hung indefinitely for either auth
    state (a GET with a valid cookie hung the same way as an unauthenticated one — review finding
    M2's own repro)."""
    app = _build_app(tmp_engine)
    sync_client = TestClient(app)
    cookies: dict[str, str] = {}
    if with_cookie:
        login_as(sync_client, "admin@example.com")
        cookies = dict(sync_client.cookies)

    async def _run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies, timeout=10.0
        ) as client:
            with anyio.fail_after(_M2_TIMEOUT_CEILING):
                return await client.request(method, _MCP_MOUNT_PATH, headers=_MCP_HEADERS)

    response = anyio.run(_run)

    assert response.status_code == 405
    assert "POST" in response.headers.get("allow", "")


def test_post_via_mount_path_still_works(tmp_engine: Engine) -> None:
    """The M2 fix must not disturb the one method the `Mount` path IS meant to serve: a real
    admin session's `POST /api/v1/mcp/` still round-trips `initialize` successfully."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    login_as(client, "admin@example.com")

    response = client.post(_MCP_MOUNT_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS)

    assert response.status_code < 400, f"expected 2xx, got {response.status_code}: {response.text}"


# ---------------------------------------------------------------------------
# M3 — app.routes.errors' exc.headers forwarding, tested directly rather than only indirectly
# through the MCP module
# ---------------------------------------------------------------------------


def test_bare_path_405_carries_allow_post_header() -> None:
    """(a) The MCP bare-path 405 (Starlette's own routing-layer method mismatch, rendered through
    `_http_exception_handler`) still carries `Allow: POST` and the §9 envelope body — DB-less,
    mirrors the pinned `test_mcp_bearer_auth.py::test_get_mcp_returns_405`, reproduced here as a
    direct M3 regression pin rather than an incidental side effect of that other test."""
    app = create_app(settings=_build_settings())
    client = TestClient(app)

    response = client.get(_MCP_PATH, headers=_MCP_HEADERS)

    assert response.status_code == 405
    assert response.headers.get("allow") == "POST"
    body = response.json()
    assert body["error"]["code"] == "http_405"
    assert body["error"]["message"] == "Method Not Allowed"


def test_http_exception_with_custom_headers_keeps_both_headers_and_envelope_shape() -> None:
    """(b) A header-bearing `HTTPException` — not necessarily a 405/`Allow`, any headers at all —
    keeps ALL of its headers on the rendered response AND the §9 envelope body shape. Minimal
    bare-`FastAPI()` repro (mirrors `test_routes_errors.py::test_unhandled_exception_returns_...`'s
    own scaffold for a different exception type), isolated from the MCP module entirely."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/custom-headers-boom")
    def boom() -> None:
        raise StarletteHTTPException(
            status_code=429,
            detail="Slow down.",
            headers={"Retry-After": "30", "X-Custom": "yes"},
        )

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/custom-headers-boom")

    assert response.status_code == 429
    assert response.headers.get("retry-after") == "30"
    assert response.headers.get("x-custom") == "yes"
    assert response.json() == {"error": {"code": "http_429", "message": "Slow down."}}


def test_404_envelope_has_no_stray_headers() -> None:
    """(c) An ordinary 404 (Starlette's router raises a plain `HTTPException(404)` with no
    `headers`, for an unmatched route) is unaffected by the forwarding change — no `Allow` or
    other exception-specific header leaks onto a response whose raised exception never carried
    any."""
    app = FastAPI()
    register_error_handlers(app)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"
    header_names = {name.lower() for name in response.headers.keys()}
    assert "allow" not in header_names
    assert "retry-after" not in header_names
