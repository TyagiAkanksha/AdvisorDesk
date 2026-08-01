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
"""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from typing import cast

import mcp_types as types
from fastapi import FastAPI
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request
from starlette.types import Receive, Scope, Send

from app.auth.deps import require_admin
from app.mcp.runtime import call_tool, list_tool_schemas
from app.services.errors import ToolInputError, ToolNotFoundError

_SERVER_NAME = "advisordesk-mcp"

# Set by `_AdminGatedMcpApp.__call__` for the duration of exactly one HTTP request, read by
# `_handle_call_tool` below. Judgment call (task-01 implementer report): the low-level `Server`'s
# `on_call_tool` hook is registered once at server-build time and has no other route to the
# request-scoped `Session`/admin identity `require_admin` resolves per call — a `ContextVar`
# bound right before delegating into the SDK's request handling, and reset in the same
# request's `finally`, is the narrowest seam that doesn't thread a session through the SDK's own
# handler-signature contract (`Callable[[ServerRequestContext, ...], Awaitable[...]]`, which this
# codebase doesn't own).
_request_context: ContextVar[tuple[Session, uuid.UUID] | None] = ContextVar(
    "app_mcp_server_request_context", default=None
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


async def _handle_call_tool(
    ctx: ServerRequestContext[dict[str, object]],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    """MCP `tools/call`: dispatches through `app.mcp.runtime.call_tool` using the bound request
    context (`_request_context`, set by `_AdminGatedMcpApp` before the SDK ever reaches this
    handler).

    PRD §6: "on a tool error, surface the error to the model once for self-correction" — a
    `ToolNotFoundError`/`ToolInputError` is reported as an `is_error=True` `CallToolResult`
    (an in-band MCP tool error the calling model/client sees), not raised as a transport-level
    exception, which the MCP spec reserves for "the tool itself couldn't be dispatched at all"
    (module `CallToolResult` docstring: "errors that originate from the tool SHOULD be reported
    inside the result... so the LLM can see and self-correct").
    """
    bound = _request_context.get()
    if bound is None:  # pragma: no cover - defensive; `_AdminGatedMcpApp` always binds first
        raise RuntimeError("MCP call_tool invoked with no bound request context.")
    session, actor_id = bound
    try:
        result = call_tool(
            params.name, dict(params.arguments or {}), session=session, actor_id=actor_id
        )
    except (ToolNotFoundError, ToolInputError) as exc:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(exc))], is_error=True
        )
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result))])


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
        """Gate on `require_admin`, bind a request-scoped `Session`+actor, then dispatch.

        `require_admin` runs first and un-wrapped, so an unauthenticated call never opens a
        session or starts the transport (§3 pin: state 2 stays DB-less, mirroring every REST
        admin route). A raised `AuthRequiredError` propagates out of this ASGI callable
        uncaught, through the app's normal exception-handling middleware
        (`app.routes.errors.register_error_handlers`), the same path any `Depends(require_admin)`
        route failure takes — CONVENTIONS.md §4's "routes contain no try/except" extends here:
        this mount has no try/except around the auth check either.
        """
        request = Request(scope, receive=receive)
        principal = require_admin(request)

        session_factory = cast(sessionmaker[Session], request.app.state.session_factory)
        session = session_factory()
        token = _request_context.set((session, principal.user_id))
        try:
            manager = StreamableHTTPSessionManager(
                app=self._server, stateless=True, json_response=True
            )
            async with manager.run():
                await manager.handle_request(scope, receive, send)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            _request_context.reset(token)
            session.close()


def mount_mcp_http(app: FastAPI, *, path: str) -> None:
    """Mount the streamable-HTTP MCP transport at `path`, behind `require_admin` (PRD §3).

    Called by `factory.py` only when `settings.mcp_http_enabled` is `True` — when it's `False`
    (the default), this is never called and `path` simply doesn't exist (§3 exposure rule,
    state 1: a plain 404, not a deliberate guard here).

    Args:
        app: the `FastAPI` app under construction.
        path: the full path to mount at (`factory.py` passes `/api/v1/mcp`).
    """
    app.mount(path, _AdminGatedMcpApp(build_mcp_server()))
