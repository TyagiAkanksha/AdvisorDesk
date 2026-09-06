"""New (RED) test for t01-N2: MCP `Mount`/bare-path requests must bucket separately from genuine
404s in `LatencyTracker`, not share the `"unmatched"` key.

Task brief: docs/plans/phase-6-remediation/task-08-held-txn-agent-tests-metrics.md, t01-N2.

`app.routes.metrics._route_name` currently buckets ANY request whose `scope["route"]` isn't a
FastAPI `APIRoute` instance into the single `_UNMATCHED_ROUTE_KEY` ("unmatched") — its own
docstring says this covers "a 404 ... or a path inside a `Mount`". `app.mcp.server.
mount_mcp_http` registers `/api/v1/mcp` (`mcp_http_enabled=True`) two ways: a plain
`starlette.routing.Route` for the exact bare path (fix round 1, finding I1 — avoids a 307 before
the auth gate runs) and a `starlette.routing.Mount` for any sub-path. NEITHER sets
`scope["route"]` (only `fastapi.routing.APIRoute.matches` does that, per `_route_name`'s own
docstring) — so today, a request into either lands in the exact same `"unmatched"`/
`"request:unmatched"` bucket a genuine, unrouted 404 does, mixing their latency percentiles
(the concrete harm the task brief names).

This test hits the pinned bare MCP path (`POST /api/v1/mcp`, unauthenticated — a real, complete
401 response, no DB writes) exactly the way `tests/test_mcp_http_transport.py`'s own
`test_bare_path_unauthenticated_never_redirects` does, plus one genuinely unrouted path (a plain
404), then asserts the two land under DIFFERENT `LatencyTracker` keys — `"request:unmatched"`
counting only the real 404. It deliberately does NOT pin the exact key name the MCP request ends
up under (mirrors `tests/test_metrics.py`'s own judgment call #3 for the general per-request key)
since the brief only gives `mount:<path>` as an EXAMPLE, not a required literal.

CONVENTIONS.md §10: the one test below requests `tmp_engine`, so this module skips cleanly
without a DB (`TEST_DATABASE_URL` unset).
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app

# Verbatim shape of `tests/test_mcp_http_transport.py`'s own pinned path/headers/body (kept local
# per that file's own no-cross-test-file-dependency precedent — this file must never import from
# it, since 6R-07 owns `tests/test_mcp_ws_guard.py` and the whole `test_mcp_*` family in parallel).
_MCP_PATH = "/api/v1/mcp"
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


def _build_settings() -> Settings:
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails="mount-bucket-admin@example.com",
        mcp_http_enabled=True,
    )


def test_mcp_mount_request_buckets_separately_from_genuine_404(tmp_engine: Engine) -> None:
    """One MCP-mount request (`POST /api/v1/mcp`, unauthenticated -> 401 via the admin gate) and
    one genuinely unrouted request (-> 404) must NOT share `LatencyTracker`'s `"request:
    unmatched"` key. RED today: both currently land there (`unmatched["count"] == 2`). GREEN once
    `_route_name` gives Mount/bare-mount-path requests their own bucket, leaving
    `"request:unmatched"` counting only the real 404.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )
    client = TestClient(app)

    mcp_response = client.post(
        _MCP_PATH, json=_INITIALIZE_BODY, headers=_MCP_HEADERS, follow_redirects=False
    )
    not_found_response = client.get("/api/v1/this-path-does-not-exist-at-all")

    # Sanity: the two requests really are the two distinct cases under test, not both 404s (or
    # both something else) by accident.
    assert mcp_response.status_code == 401, mcp_response.text
    assert not_found_response.status_code == 404, not_found_response.text

    snapshot = app.state.latency_tracker.snapshot()

    unmatched = snapshot.get("request:unmatched")
    assert unmatched is not None, snapshot
    assert unmatched["count"] == 1, (
        f"expected 'request:unmatched' to count only the genuine 404, not the MCP mount "
        f"request too: {snapshot}"
    )

    other_keys = [key for key in snapshot if key != "request:unmatched"]
    assert other_keys, (
        f"expected the MCP mount request to bucket under a key distinct from "
        f"'request:unmatched': {snapshot}"
    )
    assert sum(snapshot[key]["count"] for key in other_keys) == 1, snapshot
