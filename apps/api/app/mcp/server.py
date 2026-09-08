"""Builds the low-level MCP `Server` and mounts it over streamable HTTP (PRD §3, §6).

`build_mcp_server()` is the single registration point: every tool module's
`ToolSpec`s already live in `app.mcp.runtime`'s registry (task-02's write
tools extend that registry, not this file) — `on_list_tools`/`on_call_tool`
below just delegate to `app.mcp.runtime.list_tool_schemas`/`call_tool`, so
this module never needs to change as tools are added.

`mount_mcp_http()` is `factory.py`'s only hook into this module: gated
behind `require_admin` OR a resolvable `Authorization: Bearer` token (PRD
§3 exposure rule — "the MCP route requires the same admin session auth as
§5.2", extended by phase-6 task-04 so a deployed Claude connector, which
can send a bearer header but never a cookie, can also reach it), mounting
the official `mcp` SDK's streamable-HTTP transport, not a stub.

Fix round 1 (Opus review of commit 08dd82a, findings C1/C2/I1/I2/I3): see
`_execute_tool_call`, `_AdminGatedMcpApp.__call__`, and `mount_mcp_http` for
the specifics of each fix.

Phase-6 task-04: `_AdminGatedMcpApp.__call__` gained the bearer-token gate
(`_extract_bearer_token`/`_resolve_bearer_principal`, both new here), and
`mount_mcp_http`'s bare-path `Route` gained `methods=["POST"]` so an
unauthenticated `GET` answers 405 at the routing layer instead of 401 from
`require_admin` (phase-5 final-review t01-M8 fix).

Phase-6 task-04, fix round 1 (review findings I1/M2): `_extract_bearer_token` now raises
`AuthRequiredError` itself for a present-but-malformed `Authorization` header instead of
returning `None` and silently falling through to the cookie path (I1); `_AdminGatedMcpApp.__call__`
now rejects any non-POST method with a 405 (`Allow: POST`) BEFORE the auth gate, closing the same
hole for the `Mount`'s sub-paths that `methods=["POST"]` already closed for the bare path — a
`GET`/etc. through `path + "/..."` previously reached the streamable-HTTP transport and hung
indefinitely instead of returning (M2).

Phase-6-remediation task 6R-07 (t04-M7): `_AdminGatedMcpApp.__call__` now also rejects any
non-`"http"` scope (a `"websocket"`-type scope, reachable only via the `Mount`'s sub-paths) with a
`WebSocketException` BEFORE `Request(scope)` is ever constructed — see `__call__`'s own docstring
for why `WebSocketException` is still preferred over `StarletteHTTPException` here (portability,
not — as an earlier, incorrect version of that docstring claimed — to avoid a hang; fix round 1
review disproved the hang claim for the installed starlette version).

Phase-6-remediation task 6R-09 (WR-02 residual): `_resolve_bearer_principal` now also threads
`request.app.state.settings` (the LIVE `Settings` instance, read fresh per request) into
`resolve_bearer_token`, so a bearer token's owner is re-checked against the CURRENT `ADMIN_EMAILS`
allowlist on every call, not just at mint time — see that function's own docstring.

mcp-oauth plan, task 03 (RFC 9728 §5.1, DESIGN.md §"Security / threat model" + §"End-to-end flow"
step 1): every one of this module's three 401 paths — `_extract_bearer_token`'s malformed-header
branch, `_resolve_bearer_principal`'s unresolved-bearer branch, and the cookie path's
`_require_admin_with_challenge` wrapper — now raises `AuthRequiredError` via the shared
`_auth_required(request)` helper, which attaches a `WWW-Authenticate: Bearer resource_metadata=...`
header built from the LIVE `request.app.state.settings` (task 02's `www_authenticate_challenge`).
This lets a claude.ai connector, or any RFC 9728-aware client, discover the protected-resource
metadata document straight from a bare 401 instead of needing prior out-of-band knowledge of this
server's OAuth wiring. `_resolve_bearer_principal` also now commits its session on a successful
resolve, persisting `resolve_bearer_token`'s `last_used_at` stamp (the service itself only
`flush()`es — CONVENTIONS.md §3: the caller commits).
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any, cast

import anyio.to_thread
import mcp_types as types
from fastapi import FastAPI
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.exceptions import WebSocketException
from starlette.requests import Request
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app.auth.deps import AdminPrincipal, resolve_admin
from app.auth.oauth_discovery import www_authenticate_challenge
from app.auth.tokens import resolve_bearer_token
from app.config import Settings
from app.mcp.runtime import call_tool, list_tool_schemas
from app.services.errors import AppError, AuthRequiredError
from app.services.lifecycle import ChunkPipeline

_SERVER_NAME = "advisordesk-mcp"

logger = logging.getLogger(__name__)

# Set by `_AdminGatedMcpApp.__call__` for the duration of exactly one HTTP request, read by
# `_handle_call_tool` below. Judgment call (task-01 implementer report): the low-level `Server`'s
# `on_call_tool` hook is registered once at server-build time and has no other route to the
# request-scoped identity `require_admin` resolves per call — a `ContextVar` bound right before
# delegating into the SDK's request handling, and reset in the same request's `finally`, is the
# narrowest seam that doesn't thread state through the SDK's own handler-signature contract
# (`Callable[[ServerRequestContext, ...], Awaitable[...]]`, which this codebase doesn't own).
#
# Fix round 1, finding C1: holds a `sessionmaker`, not an open `Session` — the request no longer
# opens one session and holds it across the whole HTTP request/`await` boundary. Each tool call
# opens (and closes) its own session, scoped to exactly the synchronous span that needs it, inside
# a worker thread (`_execute_tool_call`).
#
# Phase-5 task-02: also carries the real `ChunkPipeline` (`request.app.state.chunk_pipeline`,
# resolved once by `create_app` — see `app.routes.deps.get_chunk_pipeline`'s identical read) so
# an HTTP-invoked write tool (`app.mcp.tools_write`) embeds through the same pipeline a REST
# `PATCH`/`publish`/`archive`/`DELETE` call would, not a `NoopChunkPipeline` default.
_request_context: ContextVar[tuple[sessionmaker[Session], uuid.UUID, ChunkPipeline] | None] = (
    ContextVar("app_mcp_server_request_context", default=None)
)


def build_mcp_server() -> Server[dict[str, object]]:
    """Build the in-process MCP `Server`, wired to `app.mcp.runtime`'s tool registry.

    Returns:
        A `Server` whose `tools/list` and `tools/call` handlers delegate to
        `list_tool_schemas()`/`call_tool()` — the exact same seam the agent
        loop (task-03) calls in-process.
    """
    return Server(_SERVER_NAME, on_list_tools=_handle_list_tools, on_call_tool=_handle_call_tool)


async def _handle_list_tools(
    ctx: ServerRequestContext[dict[str, object]],
    params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    """MCP `tools/list`: every registered tool's `Tool` wire shape, from `list_tool_schemas()`."""
    tools = [
        types.Tool(
            name=cast(str, schema["name"]),
            description=cast(str, schema["description"]),
            input_schema=cast(dict[str, object], schema["inputSchema"]),
        )
        for schema in list_tool_schemas()
    ]
    return types.ListToolsResult(tools=tools)


def _tool_error_result(code: str, message: str) -> types.CallToolResult:
    """Build an in-band `CallToolResult(is_error=True)` carrying a structured `{code, message}`.

    Fix round 1, finding I3: PRD §6 "surface the error to the model once for self-correction"
    means every business error (`NotFoundError`, `ConflictError`, ... — the full `AppError`
    family, not just `ToolNotFoundError`/`ToolInputError`) must reach the model in-band, not as a
    transport-level exception. `{code, message}` (JSON-encoded into the `TextContent`) mirrors the
    PRD §9 REST envelope shape (`app/routes/errors.py`'s `{"error": {"code", "message"}}`) so a
    model that has already learned to read one error shape recognizes the other.
    """
    payload = json.dumps({"code": code, "message": message})
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=payload)], is_error=True
    )


def _execute_tool_call(
    session_factory: sessionmaker[Session],
    name: str,
    arguments: dict[str, Any],
    actor_id: uuid.UUID,
    pipeline: ChunkPipeline | None = None,
) -> types.CallToolResult:
    """Run one tool call to completion — session open, `call_tool`, commit/rollback, close.

    Fix round 1: this whole function is the synchronous span `_handle_call_tool` offloads to a
    worker thread (finding C1) — the seam is a plain sync function precisely so it has a single,
    obvious boundary to hand to `anyio.to_thread.run_sync`.

    The commit/rollback decision is made HERE, in-band with whether `call_tool` actually raised —
    never by relying on an exception escaping `manager.handle_request()` (finding C2: the SDK's
    JSON-RPC dispatcher catches a handler exception, converts it to a JSON-RPC error, and returns
    `handle_request` normally, so a `try/except` wrapped around that await never observes a failed
    tool call; `session.commit()` fired even after a failing handler under the previous design).

    `AppError` (finding I3) — `ToolNotFoundError`/`ToolInputError` from `call_tool` itself, and any
    business error a tool's service call raises (`NotFoundError`, `ConflictError`, ...) — becomes a
    structured in-band tool error. Any other exception (finding I2) is logged with full detail
    server-side only and answered with a generic message, matching
    `app/routes/errors.py::_unhandled_exception_handler`'s "never `str(exc)` to the caller"
    invariant — an uncaught driver/DB error must not hand SQL text or bind parameters to an MCP
    client the way `str(exc)` would.

    Args:
        session_factory: opens this call's own `Session`.
        name: the tool name (PRD §6 tool table).
        arguments: the tool's raw, caller-supplied arguments.
        actor_id: the authenticated admin driving this call.
        pipeline: phase-5 task-02 — the `ChunkPipeline` threaded through to `call_tool` for a
            write tool to embed chunks through. `None` (the default — every caller that
            existed before task-02, including `tests/test_mcp_runtime_guards.py`'s pinned
            4-positional-argument calls) lets `call_tool` fall back to its own
            `NoopChunkPipeline()` default, so this parameter is purely additive.
    """
    session = session_factory()
    try:
        result = call_tool(name, arguments, session=session, actor_id=actor_id, pipeline=pipeline)
    except AppError as exc:
        session.rollback()
        return _tool_error_result(exc.code, str(exc))
    except Exception:
        session.rollback()
        logger.exception("Unhandled exception executing MCP tool %r", name)
        return _tool_error_result("internal_error", "Internal server error.")
    else:
        session.commit()
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result))]
        )
    finally:
        session.close()


async def _handle_call_tool(
    ctx: ServerRequestContext[dict[str, object]],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    """MCP `tools/call`: dispatch to `_execute_tool_call` on a worker thread.

    Fix round 1, finding C1: the previous body called `app.mcp.runtime.call_tool` (synchronous
    SQLAlchemy work) directly inline on this coroutine, which runs on the uvicorn event loop —
    one slow tool call froze every other request the process was serving (measured: a 3s tool call
    stalled `/health` for 2.2s; 20 concurrent MCP calls against a 15-connection pool left 19 stuck
    on a synchronous pool checkout that only the blocked event-loop thread could ever resolve).
    `anyio.to_thread.run_sync` moves the whole span — session open, `call_tool`, commit/rollback,
    close — onto a worker thread, mirroring how FastAPI itself runs `def` (non-`async def`) route
    handlers off the loop for exactly this reason.
    """
    bound = _request_context.get()
    if bound is None:  # pragma: no cover - defensive; `_AdminGatedMcpApp` always binds first
        raise RuntimeError("MCP call_tool invoked with no bound request context.")
    session_factory, actor_id, pipeline = bound
    return await anyio.to_thread.run_sync(
        _execute_tool_call,
        session_factory,
        params.name,
        dict(params.arguments or {}),
        actor_id,
        pipeline,
    )


def _auth_required(request: Request) -> AuthRequiredError:
    """Build the 401 `AuthRequiredError` for an unauthenticated `/api/v1/mcp` request, carrying
    the RFC 9728 §5.1 `WWW-Authenticate` challenge built from the LIVE settings.

    mcp-oauth plan, task 03 (DESIGN.md §"Security / threat model", §"End-to-end flow" step 1):
    the single construction site for every 401 this module raises, so the challenge header is
    identical across all three unauthenticated paths (`_extract_bearer_token`'s malformed-header
    branch, `_resolve_bearer_principal`'s unresolved-bearer branch, and
    `_require_admin_with_challenge`'s failed-cookie branch below) — a caller cannot distinguish
    which path rejected it from the header alone, matching the existing "byte-identical 401
    envelope" invariant `resolve_bearer_token`'s own docstring already pins for its rejection
    reasons.

    Reads `request.app.state.settings` fresh on every call (never a value captured at
    app-build/factory time) so a live settings mutation — an operator editing `OAUTH_ISSUER_URL`,
    or a test mutating `app.state.settings.oauth_issuer_url` directly
    (`test_www_authenticate_uses_live_settings`) — is reflected on the very next request, the same
    "live, not captured" guarantee `require_admin`/`_resolve_bearer_principal` already give the
    admin-email allowlist.

    Args:
        request: the incoming request; reads `request.app.state.settings` directly.

    Returns:
        An `AuthRequiredError("Sign in required.")` with `headers={"WWW-Authenticate": ...}` set
        — the caller raises it (this function only builds it, mirroring `str`/exception-factory
        helpers elsewhere in this codebase that build-but-don't-raise so the caller's own `raise`
        statement stays visible at the call site).
    """
    settings = cast(Settings, request.app.state.settings)
    return AuthRequiredError(
        "Sign in required.",
        headers={"WWW-Authenticate": www_authenticate_challenge(settings)},
    )


def _extract_bearer_token(request: Request) -> str | None:
    """Return the raw token from an `Authorization: Bearer <token>` header, or `None`.

    Fix round 1, finding I1: three cases, not two.
      - No `Authorization` header at all -> `None`. This is the ONLY case that still falls back
        to the unchanged `require_admin` cookie path (`_AdminGatedMcpApp.__call__`).
      - A well-formed `Bearer` credential — scheme `bearer` (case-insensitive per RFC 7235),
        exactly one separating space, a non-empty, single-token value (no embedded whitespace) —
        returns that raw value, routing the caller into the bearer-first, no-fall-through gate.
      - An `Authorization` header IS present but does not parse as a well-formed `Bearer`
        credential (missing/empty value, a non-space or doubled separator such as a tab or two
        spaces, or any scheme other than `bearer` — including `Basic ...`) -> raises
        `AuthRequiredError` directly, from here. The controller's binding rule (review round 1):
        OFFERING any `Authorization` header at all commits the caller to the bearer path — there
        is no header value that is silently ignored and falls through to the cookie. Previously
        this branch returned `None` like the absent-header case, which let a malformed bearer
        header authenticate via a coincidentally-present valid session cookie.

    Phase-6 remediation task-03 (WR-05, audit logging): the malformed-header rejection branch
    logs WARNING with reason `malformed` — never the header's value (the presented credential is
    never well-formed enough to be a real secret, but it is never logged regardless).

    mcp-oauth plan, task 03: this branch's raise now goes through `_auth_required(request)`, so
    the response carries the RFC 9728 `WWW-Authenticate` challenge — see that helper's docstring.
    """
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, sep, value = header.partition(" ")
    if sep == " " and scheme.lower() == "bearer" and value and " " not in value:
        return value
    logger.warning("Bearer token rejected: reason=malformed")
    raise _auth_required(request)


def _resolve_bearer_principal(request: Request, raw_token: str) -> AdminPrincipal:
    """Resolve `raw_token` to its owning `AdminPrincipal`, or raise `AuthRequiredError`.

    Opens/closes its OWN short-lived session from `app.state.session_factory` — mirrors
    `require_admin`'s own session lifecycle (`app.auth.deps`'s module docstring: "a second, ad
    hoc, read-only session per admin request") rather than reusing the request-scoped
    `sessionmaker` `_request_context` later binds for tool execution. Runs synchronously;
    `_AdminGatedMcpApp.__call__` offloads it to a worker thread via `anyio.to_thread.run_sync`,
    exactly like `require_admin` itself.

    Task-04 brief: a present-but-unresolvable bearer token must 401 WITHOUT falling through to
    the cookie path — this is that "resolve or raise" seam; the caller never re-tries
    `require_admin` after this raises.

    Phase-6 remediation task-09 (WR-02 residual): also passes `request.app.state.settings` —
    the LIVE `Settings` instance `create_app` stashed there, not a value captured earlier — into
    `resolve_bearer_token` so its allowlist re-check always sees the CURRENT `ADMIN_EMAILS`, even
    if an operator edits it (or a test mutates `app.state.settings` directly) after the app was
    built.

    mcp-oauth plan, task 03: a `None` return now raises via `_auth_required(request)` (the RFC
    9728 `WWW-Authenticate` challenge), and a non-`None` return now `session.commit()`s before
    closing — `resolve_bearer_token` itself only `flush()`es its `last_used_at` stamp
    (CONVENTIONS.md §3: services never commit), so this is the one call site that persists it, on
    the success path only. A rejected token never mutates the row, so committing an empty/rejected
    transaction has no effect either way — the commit is gated on success purely to keep the
    "only a successful resolve is observable" contract explicit at the call site.

    Args:
        request: the incoming request; reads `app.state.session_factory`/`app.state.settings`
            directly (see `app.auth.deps.require_admin`'s identical read for why this layer
            doesn't go through `app.routes.deps.get_session`/`get_settings`).
        raw_token: the bearer value, already stripped of its `"Bearer "` scheme prefix by
            `_extract_bearer_token`.

    Raises:
        AuthRequiredError: `raw_token` doesn't resolve to an active, allowlisted user (unknown,
            garbage, a soft-deleted account's token, one revoked by a since-run `/auth/logout`
            epoch bump — phase-6 remediation task-03, WR-02 — one whose `expires_at` has passed,
            one whose owner's email is no longer in `ADMIN_EMAILS` — phase-6 remediation task-09,
            WR-02 residual — or one that fails the mcp-oauth task-03 audience rule) — carries the
            RFC 9728 `WWW-Authenticate` challenge (`_auth_required`).
        RuntimeError: the app was built without a `session_factory` (a DB-less `create_app()`) —
            mirrors `require_admin`'s own guard.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "_resolve_bearer_principal() requires app.state.session_factory, but none was "
            "configured — this app was built by create_app() without a session_factory "
            "(DB-less mode)."
        )
    settings = cast(Settings, request.app.state.settings)

    session = session_factory()
    try:
        principal = resolve_bearer_token(session, raw_token, settings)
        if principal is not None:
            session.commit()
    finally:
        session.close()

    if principal is None:
        raise _auth_required(request)
    return principal


def _require_admin_with_challenge(request: Request) -> AdminPrincipal:
    """Resolve the admin session cookie, raising with the RFC 9728 `WWW-Authenticate` challenge
    attached when it doesn't resolve.

    mcp-oauth plan, task 03 (DESIGN.md §"Security / threat model", §"End-to-end flow" step 1):
    `require_admin` (`app.auth.deps`) is the shared cookie-auth dependency every REST admin route
    also depends on, and its `AuthRequiredError` must stay headerless there — a REST 401 has no
    use for an MCP-specific discovery pointer (`test_rest_401_has_no_www_authenticate`). This
    thin wrapper is `app.mcp`'s own seam, mirroring `require_admin`'s own resolve-or-raise shape
    but attaching the challenge only for the MCP caller.

    mcp-oauth plan, task 05: now calls `resolve_admin(request)` directly (rather than wrapping
    `require_admin` in a `try/except AuthRequiredError`, this function's own earlier shape) and
    raises `_auth_required(request)` on `None` — a simplification enabled by `resolve_admin`
    existing as its own seam (`app.auth.deps`, split out of `require_admin` for
    `GET /oauth/authorize/continue`'s Google-bridge branch), with byte-identical observable
    behavior: same WARNING logs, same rejection reasons, same `RuntimeError` DB-less guard
    (`resolve_admin` raises it exactly where `require_admin` did).

    Args:
        request: the incoming request; forwarded to both `resolve_admin` and `_auth_required`.

    Raises:
        AuthRequiredError: no/invalid/expired cookie, unknown or soft-deleted user, or a stale
            session epoch (see `resolve_admin`'s own docstring) — always carries the
            `WWW-Authenticate` challenge here, unlike `require_admin`'s own headerless raise.
        RuntimeError: the app was built without a `session_factory` (`resolve_admin`'s own
            DB-less guard) — propagates unchanged, not wrapped.
    """
    principal = resolve_admin(request)
    if principal is None:
        raise _auth_required(request)
    return principal


class _AdminGatedMcpApp:
    """ASGI app mounted at the MCP HTTP path: bearer-or-cookie admin gate + a per-request
    streamable HTTP transport.

    A fresh `StreamableHTTPSessionManager` is built and `.run()` per call, scoped to exactly
    this one request, rather than one long-lived manager started once at mount time. Judgment
    call (task-01 implementer report): verified empirically that a manager `.run()`'d lazily on
    first request and left open does not survive past that single request under
    `starlette.testclient.TestClient` used without a `with` block (the shape both pinned
    exposure tests use) — `TestClient` spins up (and tears down) a fresh `anyio` portal/event
    loop per call when not used as a context manager, and a `StreamableHTTPSessionManager`'s
    `anyio` task group cannot outlive the portal that started it; the next call's teardown
    corrupts it with a cross-task cancel-scope error. Scoping `.run()` to one request instead
    means it starts and fully tears down inside the same portal call that created it — which
    also matches `stateless=True`'s own contract ("a completely fresh transport for each
    request with no session tracking... between requests").
    """

    def __init__(self, server: Server[dict[str, object]]) -> None:
        self._server = server

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject a non-`"http"` scope, then a non-POST method, fast, then gate on a bearer
        token (if offered) or `require_admin`'s cookie, bind a request-scoped session factory +
        actor, and dispatch.

        Phase-6-remediation task 6R-07, t04-M7: the `Mount`'s sub-paths (e.g. `/api/v1/mcp/`)
        match BOTH `"http"` and `"websocket"` scope types (`starlette.routing.Mount.matches`) —
        unlike the bare-path `Route` below, which only ever matches `"http"`
        (`starlette.routing.Route.matches`), so only the `Mount` side can ever hand this
        `__call__` a `"websocket"`-type scope. Before this guard, such a scope sailed past the
        method-guard below (which only fires `if scope["type"] == "http"`) straight into
        `Request(scope, receive=receive)`, whose `assert scope["type"] == "http"`
        (`starlette.requests.Request.__init__`) raised a bare, uncaught `AssertionError` — a
        crash, not a clean rejection. This guard runs FIRST, before `Request(scope)` is ever
        constructed, mirroring the method-guard's own placement/style (an early `if`, raising
        before any further work). It raises `WebSocketException`, not `StarletteHTTPException`,
        by choice, though on the installed `starlette==0.38.6` NEITHER hangs — both close a
        `"websocket"`-scope connection cleanly (verified empirically, 6R-07 fix round 1 review,
        against a full `create_app()` + `TestClient.websocket_connect` probe on the real mounted
        app; an earlier version of this comment incorrectly claimed the `StarletteHTTPException`
        alternative would hang, which the review disproved). `WebSocketException` is handled by
        `ExceptionMiddleware`'s own `websocket_exception` method, which calls a real
        `websocket.close(code=exc.code, reason=exc.reason)` directly
        (`starlette.middleware.exceptions.ExceptionMiddleware.websocket_exception`).
        `StarletteHTTPException`, mapped by `register_error_handlers` to `_http_exception_handler`
        (a plain function returning a `JSONResponse`), instead goes through
        `wrap_app_handling_exceptions`'s generic `await response(scope, receive, sender)` call —
        and `starlette.responses.Response.__call__` auto-detects a `"websocket"`-type scope and
        wraps `send` into the ASGI websocket-denial-response extension
        (`websocket.http.response.start`/`.body`) rather than the plain `http.response.*` pair, so
        the `JSONResponse` IS sent, just via that extension's message shape, not discarded.
        `WebSocketException` is still the better choice here, on portability grounds: it emits the
        plain `websocket.close` ASGI message every ASGI server supports, with no dependency on an
        ASGI server implementing the newer websocket-denial-response extension the
        `StarletteHTTPException` path relies on.

        Phase-6 task-04 fix round 1, finding M2: this ASGI app is reachable two ways — the
        bare-path `Route` (`mount_mcp_http`, method-restricted to POST at the routing layer, so a
        non-POST request there never reaches this `__call__` at all) AND the `Mount`'s sub-paths
        (`path + "/..."`, e.g. `/api/v1/mcp/`), which Starlette's `Mount` does not method-restrict.
        A `GET`/`DELETE`/etc. through the `Mount` used to reach the streamable-HTTP transport
        directly, which opens a standalone SSE stream and never returns — the request hangs
        indefinitely. The check below runs BEFORE the auth gate (so it's also DB-less, matching
        the bare path's routing-layer 405) and raises the same `StarletteHTTPException(405,
        headers={"Allow": "POST"})` shape Starlette's own router raises for the bare path's
        method mismatch, so `register_error_handlers` renders both through the identical §9
        envelope + `Allow` header.

        Phase-6 task-04: `_extract_bearer_token` checks for an `Authorization: Bearer <token>`
        header FIRST. When one is present, it must resolve via `_resolve_bearer_principal` or the
        whole request 401s right there — no fall-through to `require_admin`'s cookie check, even
        when a valid cookie also happens to be present on the same request (task-04 brief's
        explicit no-fall-through pin: offering a bearer header commits the caller to the bearer
        path). Only when NO bearer header is present at all does this fall back to the unchanged
        `require_admin` cookie path — everything below this auth step is exactly as it was before
        task-04, for either path. Fix round 1, finding I1: a present-but-malformed `Authorization`
        header (empty/missing value, a bad separator, or a non-`bearer` scheme) now raises
        `AuthRequiredError` from inside `_extract_bearer_token` itself, before this method ever
        considers the cookie path — see that function's docstring for the exact three-way split.

        Either way, auth runs first, so an unauthenticated call never binds a session factory or
        starts the transport (§3 pin: state 2 stays DB-less, mirroring every REST admin route). A
        raised `AuthRequiredError` (or the `StarletteHTTPException` above) propagates out of this
        ASGI callable uncaught, through the app's normal exception-handling middleware
        (`app.routes.errors.register_error_handlers`), the same path any `Depends(require_admin)`
        route failure takes — CONVENTIONS.md §4's "routes contain no try/except" extends here:
        this method itself has no try/except around the auth check either. (mcp-oauth task 03:
        the cookie path now calls `_require_admin_with_challenge`, a separate module-level
        function that DOES wrap `require_admin` in a `try/except AuthRequiredError` to attach the
        RFC 9728 challenge — see that function's own docstring for why living in `app.mcp` rather
        than `app.routes` makes that a sanctioned exception to the same rule, not a violation of
        it.)

        Fix round 1, finding C1: `require_admin` (via `_require_admin_with_challenge` since
        mcp-oauth task 03) runs a synchronous DB query (`app/auth/deps.py`) — offloaded to a
        worker thread the same way tool execution is (`_handle_call_tool`), so this coroutine
        never blocks the event loop either.
        Phase-6 task-04: `_resolve_bearer_principal` is offloaded to a worker thread the same way,
        for the same reason — it also runs a synchronous DB query.

        Fix round 1, finding C1 (session scoping): no `Session` is opened here at all — only a
        `sessionmaker` reference is bound to `_request_context`. `tools/list`/`initialize`
        HTTP requests (which touch no database) now never open a connection; a `tools/call`
        request opens one only for the duration of `_execute_tool_call`'s worker-thread span,
        never held across an `await`. (The bearer path's own auth-time lookup, if taken, opens
        and closes ITS OWN separate session inside `_resolve_bearer_principal` — same "ad hoc,
        short-lived" shape `require_admin` already uses for the cookie path, never the
        `_request_context` sessionmaker.)

        Phase-5 task-02: also binds `request.app.state.chunk_pipeline` — the same resolved
        `ChunkPipeline` `app.routes.deps.get_chunk_pipeline` hands every REST route (`create_app`
        always resolves this to a concrete pipeline, `NoopChunkPipeline` by default — never
        `None`, so no fail-loud branch is needed here) — so an HTTP-invoked write tool embeds
        chunks for real, not through a request-local `NoopChunkPipeline`.
        """
        if scope["type"] != "http":
            raise WebSocketException(
                code=1008, reason="This endpoint does not accept WebSocket connections."
            )

        if scope["type"] == "http" and scope["method"] != "POST":
            raise StarletteHTTPException(status_code=405, headers={"Allow": "POST"})

        request = Request(scope, receive=receive)
        bearer_token = _extract_bearer_token(request)
        principal: AdminPrincipal
        if bearer_token is not None:
            principal = await anyio.to_thread.run_sync(
                _resolve_bearer_principal, request, bearer_token
            )
        else:
            principal = await anyio.to_thread.run_sync(_require_admin_with_challenge, request)

        session_factory = cast(sessionmaker[Session], request.app.state.session_factory)
        pipeline = cast(ChunkPipeline, request.app.state.chunk_pipeline)
        token = _request_context.set((session_factory, principal.user_id, pipeline))
        try:
            manager = StreamableHTTPSessionManager(
                app=self._server, stateless=True, json_response=True
            )
            async with manager.run():
                await manager.handle_request(scope, receive, send)
        finally:
            _request_context.reset(token)


def mount_mcp_http(app: FastAPI, *, path: str) -> None:
    """Mount the streamable-HTTP MCP transport at `path`, behind the bearer-or-cookie admin gate
    (PRD §3).

    Called by `factory.py` only when `settings.mcp_http_enabled` is `True` — when it's `False`
    (the default), this is never called and `path` simply doesn't exist (§3 exposure rule,
    state 1: a plain 404, not a deliberate guard here).

    Fix round 1, finding I1: Starlette's `Mount` compiles its match regex as
    `path + "/{path:path}"` (`starlette.routing.Mount.__init__`), which requires a literal `/`
    immediately after `path` — a bare request to `path` itself (no trailing segment) never matches
    `Mount`, so Starlette's router 307-redirects it to `path + "/"` before the auth gate ever
    runs. An external client that doesn't auto-follow redirects (plain `httpx`/`requests`
    defaults, `curl` without `-L`, a browser `fetch`) gets a bodyless 307 instead of the MCP
    endpoint the controller pinned at exactly `path`. Registering an exact-match `Route` at `path`
    too closes the gap: Starlette treats a non-function/-method `endpoint` as already ASGI-shaped
    (`Route.__init__`: `self.app = endpoint` when `endpoint` isn't `inspect.isfunction`/
    `inspect.ismethod`), so the same `_AdminGatedMcpApp` instance is called the same way — `path`
    now answers directly, and `path + "/..."` still goes through `Mount` exactly as before.

    Phase-6 task-04 (phase-5 final-review t01-M8 fix): the bare-path `Route` now also declares
    `methods=["POST"]` (`Mount`'s own sub-path matching is untouched — still no method
    restriction there). Starlette's router treats a path match with a disallowed method as a
    "partial match" (`starlette.routing.Route.matches`) and answers 405 with an `Allow` header
    BEFORE `Route.app` (this mount's `_AdminGatedMcpApp.__call__`, i.e. the whole auth gate) is
    ever invoked — so an unauthenticated `GET /api/v1/mcp` is a routing-layer 405, not a 401 from
    `require_admin`/`_resolve_bearer_principal`. (This surfaced a pre-existing gap in
    `app.routes.errors._http_exception_handler` — it rebuilt the §9 envelope from a caught
    `StarletteHTTPException` but dropped `exc.headers`, which would have silently discarded this
    very `Allow: POST` header; fixed alongside this change since nothing about a 405 with no
    `Allow` header would have satisfied PRD §9's general "framework-native errors still carry
    their real HTTP semantics" intent, even though no route raised a header-bearing
    `HTTPException` before this task.)

    Args:
        app: the `FastAPI` app under construction.
        path: the full path to mount at (`factory.py` passes `/api/v1/mcp`).
    """
    gated_app = _AdminGatedMcpApp(build_mcp_server())
    app.router.routes.append(
        Route(path, endpoint=gated_app, name="mcp_http_bare_path", methods=["POST"])
    )
    app.mount(path, gated_app)
