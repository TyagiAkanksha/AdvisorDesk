"""Builds the low-level MCP `Server` and mounts it over streamable HTTP (PRD §3, §6).

`build_mcp_server()` is the single registration point: every tool module's
`ToolSpec`s already live in `app.mcp.runtime`'s registry (task-02's write
tools extend that registry, not this file) — `on_list_tools`/`on_call_tool`
below just delegate to `app.mcp.runtime.list_tool_schemas`/`call_tool`, so
this module never needs to change as tools are added.

`mount_mcp_http()` is `factory.py`'s only hook into this module: gated
behind the same `require_admin` dependency every REST admin route uses
(PRD §3 exposure rule — "the MCP route requires the same admin session auth
as §5.2"), mounting the official `mcp` SDK's streamable-HTTP transport, not
a stub.

Fix round 1 (Opus review of commit 08dd82a, findings C1/C2/I1/I2/I3): see
`_execute_tool_call`, `_AdminGatedMcpApp.__call__`, and `mount_mcp_http` for
the specifics of each fix.
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
from starlette.requests import Request
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app.auth.deps import require_admin
from app.mcp.runtime import call_tool, list_tool_schemas
from app.services.errors import AppError
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


class _AdminGatedMcpApp:
    """ASGI app mounted at the MCP HTTP path: `require_admin` gate + a per-request streamable
    HTTP transport.

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
        """Gate on `require_admin`, bind a request-scoped session factory + actor, then dispatch.

        `require_admin` runs first, so an unauthenticated call never binds a session factory or
        starts the transport (§3 pin: state 2 stays DB-less, mirroring every REST admin route). A
        raised `AuthRequiredError` propagates out of this ASGI callable uncaught, through the app's
        normal exception-handling middleware (`app.routes.errors.register_error_handlers`), the
        same path any `Depends(require_admin)` route failure takes — CONVENTIONS.md §4's "routes
        contain no try/except" extends here: this mount has no try/except around the auth check
        either.

        Fix round 1, finding C1: `require_admin` itself runs a synchronous DB query
        (`app/auth/deps.py`) — offloaded to a worker thread the same way tool execution is
        (`_handle_call_tool`), so this coroutine never blocks the event loop either.

        Fix round 1, finding C1 (session scoping): no `Session` is opened here at all — only a
        `sessionmaker` reference is bound to `_request_context`. `tools/list`/`initialize`
        HTTP requests (which touch no database) now never open a connection; a `tools/call`
        request opens one only for the duration of `_execute_tool_call`'s worker-thread span,
        never held across an `await`.

        Phase-5 task-02: also binds `request.app.state.chunk_pipeline` — the same resolved
        `ChunkPipeline` `app.routes.deps.get_chunk_pipeline` hands every REST route (`create_app`
        always resolves this to a concrete pipeline, `NoopChunkPipeline` by default — never
        `None`, so no fail-loud branch is needed here) — so an HTTP-invoked write tool embeds
        chunks for real, not through a request-local `NoopChunkPipeline`.
        """
        request = Request(scope, receive=receive)
        principal = await anyio.to_thread.run_sync(require_admin, request)

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
    """Mount the streamable-HTTP MCP transport at `path`, behind `require_admin` (PRD §3).

    Called by `factory.py` only when `settings.mcp_http_enabled` is `True` — when it's `False`
    (the default), this is never called and `path` simply doesn't exist (§3 exposure rule,
    state 1: a plain 404, not a deliberate guard here).

    Fix round 1, finding I1: Starlette's `Mount` compiles its match regex as
    `path + "/{path:path}"` (`starlette.routing.Mount.__init__`), which requires a literal `/`
    immediately after `path` — a bare request to `path` itself (no trailing segment) never matches
    `Mount`, so Starlette's router 307-redirects it to `path + "/"` before `require_admin` ever
    runs. An external client that doesn't auto-follow redirects (plain `httpx`/`requests`
    defaults, `curl` without `-L`, a browser `fetch`) gets a bodyless 307 instead of the MCP
    endpoint the controller pinned at exactly `path`. Registering an exact-match `Route` at `path`
    too closes the gap: Starlette treats a non-function/-method `endpoint` as already ASGI-shaped
    (`Route.__init__`: `self.app = endpoint` when `endpoint` isn't `inspect.isfunction`/
    `inspect.ismethod`), so the same `_AdminGatedMcpApp` instance is called the same way, with no
    method restriction (`methods=None`, matching `Mount`'s own no-method-restriction behavior) —
    `path` now answers directly, and `path + "/..."` still goes through `Mount` exactly as before.

    Args:
        app: the `FastAPI` app under construction.
        path: the full path to mount at (`factory.py` passes `/api/v1/mcp`).
    """
    gated_app = _AdminGatedMcpApp(build_mcp_server())
    app.router.routes.append(Route(path, endpoint=gated_app, name="mcp_http_bare_path"))
    app.mount(path, gated_app)
