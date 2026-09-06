"""Test-author RED for phase-6-remediation task 6R-07 / t04-M7 (`app.mcp.server`).

`_AdminGatedMcpApp.__call__` currently constructs `Request(scope, receive=receive)` for EVERY
scope it's called with — `Request.__init__` asserts `scope["type"] == "http"` (see
`starlette.requests.Request.__init__`), so a `ws://` upgrade routed to the MCP mount's sub-path
(Starlette's `Mount` matches both `"http"` and `"websocket"` scope types — unlike the bare-path
`Route`, which only ever matches `"http"`, see `starlette.routing.Route.matches`) raises a bare
`AssertionError` instead of being rejected. The existing method-guard (t04 fix, same `__call__`)
already rejects a bad HTTP method BEFORE the auth gate; t04-M7 adds the mirror-image guard for a
non-`"http"` scope, placed the same way, BEFORE `Request(scope)` is ever constructed.

Judgment call — this test drives a raw ASGI websocket-type scope DIRECTLY against
`_AdminGatedMcpApp`, not through the full app + `TestClient.websocket_connect`
(`tests/test_mcp_gate_fixes.py`'s pattern for the sibling M2 method-guard tests). Reason: going
through the full app means the scope also passes through Starlette's `ExceptionMiddleware`
(`starlette._exception_handler.wrap_app_handling_exceptions`), and for a `"websocket"`-type scope
that middleware only ever *awaits* a matched handler — it never sends the handler's returned
`Response` on the ASGI `send` channel the way the `"http"` branch does. Both this module's current
bare `AssertionError` AND a plausible fix that raises `StarletteHTTPException` (rather than
Starlette's own `WebSocketException`, which — uniquely — Starlette's `ExceptionMiddleware` handles
with a real default `websocket.close`) get routed to `app.routes.errors._http_exception_handler`/
`_unhandled_exception_handler`, both plain functions returning an (unsent) `JSONResponse`: nothing
is ever written to `send`, so `WebSocketTestSession.__enter__`'s blocking `queue.get()` hangs
forever waiting for a message that will never arrive. That's a real, separate gap in
`app.routes.errors` (out of this task's scope — 6R-07 pins only the `_AdminGatedMcpApp` guard, not
the app-wide websocket-exception-rendering path) but it makes `TestClient.websocket_connect`
unsuitable as a RED driver here: a regression in the fix's exact exception choice would hang the
test process rather than fail it, which the "a parallel task must be able to run the full suite
without your file aborting collection" constraint rules out. Calling `_AdminGatedMcpApp.__call__`
directly sidesteps `ExceptionMiddleware` entirely, pins the guard itself, and fails fast either way
a fix might reject the connection (a raised `WebSocketException`/`StarletteHTTPException`, or a
`send`d `websocket.close`/`websocket.http.response.start` message).
"""

from __future__ import annotations

from typing import Any

import anyio
import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.exceptions import WebSocketException

from app.mcp.server import _AdminGatedMcpApp, build_mcp_server

# Mirrors tests/test_mcp_gate_fixes.py's `_MCP_MOUNT_PATH`: the `Mount`'s sub-path shape a real
# ASGI server would route a `ws://.../api/v1/mcp/` upgrade to (the bare-path `Route` never matches
# a `"websocket"`-type scope at all — `Route.matches` only matches `"http"` — so only the `Mount`
# side of this mount can ever reach `_AdminGatedMcpApp.__call__` with one).
_MCP_MOUNT_PATH = "/api/v1/mcp/"

# ASGI "clean rejection" message types the fix may legitimately choose between: a pre-accept
# close, or an HTTP-response-style denial (both valid per the ASGI websocket spec).
_CLEAN_REJECTION_MESSAGE_TYPES = {"websocket.close", "websocket.http.response.start"}

# Defensive ceiling only — the current bug fails synchronously with no `await` in between, so this
# never actually waits; it exists so a future change that adds a stray blocking `await` fails fast
# instead of hanging the suite (same rationale as test_mcp_gate_fixes.py's `_M2_TIMEOUT_CEILING`).
_TIMEOUT_CEILING = 5.0


def _websocket_scope(path: str) -> dict[str, Any]:
    """A minimal-but-realistic ASGI websocket-type scope for `path`, mirroring what a real ASGI
    server hands an app for a `ws://` upgrade request (RFC 6455 handshake fields omitted — nothing
    this guard is expected to read needs them)."""
    return {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "subprotocols": [],
    }


def test_websocket_scope_rejected_cleanly_not_via_assertion_error() -> None:
    """t04-M7 RED: a `"websocket"`-type scope to the MCP mount must be rejected cleanly — a typed
    `WebSocketException`/`StarletteHTTPException`, or a `send`d close/denial ASGI message — NEVER
    the bare `AssertionError` `Request(scope)` raises today for any non-`"http"` scope.

    Today: `_AdminGatedMcpApp.__call__`'s method-guard only fires `if scope["type"] == "http"`, so
    it's skipped entirely for a websocket scope; execution falls straight through to
    `Request(scope, receive=receive)`, whose `assert scope["type"] == "http"` fails — this test
    currently fails with that `AssertionError` surfacing as a `pytest.fail()`, a runtime test
    failure (not a collection error): the module imports cleanly and every other test in this
    file/suite is unaffected.
    """
    gated_app = _AdminGatedMcpApp(build_mcp_server())
    scope = _websocket_scope(_MCP_MOUNT_PATH)
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def _call() -> None:
        with anyio.fail_after(_TIMEOUT_CEILING):
            await gated_app(scope, receive, send)

    try:
        anyio.run(_call)
    except AssertionError as exc:
        pytest.fail(
            "websocket-type scope raised AssertionError from Request(scope) instead of a clean "
            f"rejection — t04-M7 guard missing in _AdminGatedMcpApp.__call__: {exc!r}"
        )
    except (WebSocketException, StarletteHTTPException):
        # A typed, intentional rejection - the real deployment's ExceptionMiddleware/router turns
        # this into an actual close/response; acceptable here since we call `__call__` directly.
        return

    assert sent, (
        "expected _AdminGatedMcpApp.__call__ to either raise a typed rejection or send a clean "
        "close/denial ASGI message, but it returned having sent nothing"
    )
    assert sent[0]["type"] in _CLEAN_REJECTION_MESSAGE_TYPES, (
        f"expected one of {_CLEAN_REJECTION_MESSAGE_TYPES!r} as the first sent message, "
        f"got {sent[0]!r}"
    )
