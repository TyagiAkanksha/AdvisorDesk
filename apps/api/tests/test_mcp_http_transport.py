"""Fix round 1 (Opus review of commit 08dd82a) — covering tests for C1 and I1.

Review: `.superpowers/sdd/reports/p5-t01-review.md`. This file is NEW (not a pinned test file).

Findings covered here:
  - I1: `POST /api/v1/mcp` (the pinned bare path, no trailing slash) now serves directly instead
    of 307-redirecting to `/api/v1/mcp/` — proven with `follow_redirects=False` (what a bare
    `httpx`/`requests`/`curl` client, or the pinned tests' own `TestClient` if it did NOT default
    to following redirects, would see).
  - C1: `_AdminGatedMcpApp.__call__`/`_handle_call_tool` no longer run blocking synchronous DB
    work inline on the event loop — proven with a deterministic, bounded concurrency test: a
    temporary "slow" tool (a plain synchronous `time.sleep`, not a real slow query, so the test
    has no dependency on DB connection-pool sizing) invoked N times concurrently over the real
    ASGI transport must finish in close to ONE slow call's duration, not N of them, and the whole
    test is wrapped in `anyio.fail_after` so a regression back to event-loop blocking fails fast
    with a clear timeout rather than hanging.

CONVENTIONS.md §10: the one DB-touching state (a real admin login) requests `tmp_engine`, skipped
by fixture name when `TEST_DATABASE_URL` is unset.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator

import anyio
import httpx
import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.mcp.runtime as runtime_module
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.mcp.tool_spec import ToolSpec

_MCP_PATH = "/api/v1/mcp"
_MCP_HEADERS = {"Accept": "application/json, text/event-stream"}

# Same minimal, real MCP JSON-RPC "initialize" body as the pinned `test_mcp_exposure.py` (kept
# local per that file's own no-cross-test-file-dependency precedent).
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


def _build_settings(*, mcp_http_enabled: bool) -> Settings:
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails="admin@example.com",
        mcp_http_enabled=mcp_http_enabled,
    )


# ---------------------------------------------------------------------------
# I1 — the pinned bare path serves directly; no redirect dependence
# ---------------------------------------------------------------------------


def test_bare_path_unauthenticated_never_redirects(tmp_engine: Engine) -> None:
    """`follow_redirects=False` at the exact pinned path (`/api/v1/mcp`, no trailing slash) with
    no session must answer 401 directly — never a 307. Before the I1 fix, Starlette's `Mount`
    regex (`path + "/{path:path}"`) never matched the bare path, so the router 307-redirected to
    `path + "/"` before `require_admin` ever ran."""
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(mcp_http_enabled=True),
        oauth_client=FakeGoogleOAuthClient(),
    )
    client = TestClient(app)

    response = client.post(
        _MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS, follow_redirects=False
    )

    assert response.status_code != 307
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_bare_path_authenticated_never_redirects(tmp_engine: Engine) -> None:
    """Same pin, authenticated: `follow_redirects=False` at the bare path must answer 2xx
    directly, not 307 (the review's own probe: a plain `httpx`/`requests` client, `curl` without
    `-L`, hitting the bare path exactly as documented got a bodyless 307 for every request)."""
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(mcp_http_enabled=True),
        oauth_client=FakeGoogleOAuthClient(),
    )
    client = TestClient(app)
    login_as(client, "admin@example.com")

    response = client.post(
        _MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS, follow_redirects=False
    )

    assert response.status_code != 307
    assert response.status_code < 400, (
        f"expected a non-4xx/non-5xx (2xx) response, got {response.status_code}: {response.text}"
    )


def test_bare_path_absent_with_default_settings_never_redirects(tmp_engine: Engine) -> None:
    """§3 state 1, re-pinned with `follow_redirects=False`: the bare path is a plain 404, not a
    307 hop toward a 404 at the slash path."""
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(mcp_http_enabled=False),
        oauth_client=FakeGoogleOAuthClient(),
    )
    client = TestClient(app)

    response = client.post(
        _MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS, follow_redirects=False
    )

    assert response.status_code != 307
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# C1 — concurrent MCP tool calls no longer block the event loop
# ---------------------------------------------------------------------------

_SLOW_SECONDS = 0.4
_CONCURRENCY = 6
_TEST_TIMEOUT_CEILING = 15.0  # anyio.fail_after ceiling — bounds the whole test deterministically


class _EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _sleepy_handler(
    args: _EmptyArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, object]:
    """A purely synchronous, blocking "tool" — simulates the blocking DB span C1 found, without
    depending on real DB connection-pool sizing (the review's own C1 probe used a real slow
    query; a plain `time.sleep` isolates the event-loop-blocking question from pool-exhaustion
    questions, which is a separate, already-improved-for-free consequence of scoping sessions to
    the tool call rather than the whole request — see this file's module docstring)."""
    time.sleep(_SLOW_SECONDS)
    return {"ok": True}


@pytest.fixture
def _sleepy_tool_registered(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    spec = ToolSpec(
        name="_test_sleepy_tool",
        description="test-only",
        args_model=_EmptyArgs,
        handler=_sleepy_handler,
    )
    monkeypatch.setitem(runtime_module._REGISTRY, spec.name, spec)
    yield


async def _call_sleepy_tool(client: httpx.AsyncClient, call_id: int) -> httpx.Response:
    body = {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {"name": "_test_sleepy_tool", "arguments": {}},
    }
    return await client.post(f"{_MCP_PATH}/", json=body, headers=_MCP_HEADERS)


def test_concurrent_mcp_tool_calls_run_in_parallel_not_serially(
    tmp_engine: Engine, _sleepy_tool_registered: None
) -> None:
    """The C1 regression test. Before the fix, `_handle_call_tool` ran the (here, simulated)
    blocking tool body directly on the coroutine that `manager.handle_request` awaits, which
    itself runs on the single event-loop thread `httpx.ASGITransport` drives — `_CONCURRENCY`
    concurrent calls would execute strictly one-at-a-time, taking roughly
    `_CONCURRENCY * _SLOW_SECONDS` wall-clock. After the fix (`anyio.to_thread.run_sync`), they
    run on separate worker threads and complete in close to one call's duration.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(mcp_http_enabled=True),
        oauth_client=FakeGoogleOAuthClient(),
    )
    sync_client = TestClient(app)
    login_as(sync_client, "admin@example.com")
    cookies = dict(sync_client.cookies)

    async def _run() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies, timeout=10.0
        ) as client:
            # `fail_after` is the "timeout ceiling" (binding rule 2): if a regression reintroduces
            # event-loop blocking, this raises `TimeoutError` deterministically instead of the
            # test hanging.
            with anyio.fail_after(_TEST_TIMEOUT_CEILING):
                async with anyio.create_task_group() as tg:
                    results: list[httpx.Response | None] = [None] * _CONCURRENCY

                    async def _worker(i: int) -> None:
                        results[i] = await _call_sleepy_tool(client, i)

                    for i in range(_CONCURRENCY):
                        tg.start_soon(_worker, i)
            assert all(r is not None for r in results)
            return [r for r in results if r is not None]

    start = time.monotonic()
    responses = anyio.run(_run)
    elapsed = time.monotonic() - start

    assert len(responses) == _CONCURRENCY
    for response in responses:
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["result"]["isError"] is False
        assert payload["result"]["content"][0]["text"] == '{"ok": true}'

    # Serial execution would take ~= _CONCURRENCY * _SLOW_SECONDS (2.4s at these constants).
    # Genuine parallelism finishes in close to one call's duration. The threshold sits well
    # between the two so this is deterministic, not a flaky race against exact timing.
    serial_baseline = _CONCURRENCY * _SLOW_SECONDS
    assert elapsed < serial_baseline * 0.6, (
        f"{_CONCURRENCY} concurrent MCP tool calls took {elapsed:.2f}s "
        f"(serial would be ~{serial_baseline:.2f}s) — looks like the event loop serialized them"
    )
