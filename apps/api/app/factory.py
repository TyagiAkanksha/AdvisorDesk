"""`create_app()` — the single FastAPI application constructor (CONVENTIONS.md §5).

Must succeed with no database and no env vars, so DB-less tests and the
`openapi.json` baseline export (CONVENTIONS.md §8) can both build a real
app. Every later route task includes its router here.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.agent.loop import AgentLLM
from app.auth.oauth import GoogleOAuthClient
from app.config import Settings
from app.mcp.server import mount_mcp_http
from app.rag.embeddings import Embedder
from app.rag.synthesis import ChatLLM
from app.routes.agent_routes import router as agent_router
from app.routes.auth_routes import router as auth_router
from app.routes.content_routes import router as content_router
from app.routes.discovery_routes import router as discovery_router
from app.routes.errors import register_error_handlers
from app.routes.health_routes import router as health_router
from app.routes.metrics import LatencyMiddleware, LatencyTracker
from app.routes.oauth_routes import router as oauth_router
from app.routes.public_routes import router as public_router
from app.routes.ratelimit import RateLimiter
from app.services.lifecycle import ChunkPipeline, NoopChunkPipeline

_API_PREFIX = "/api/v1"


def create_app(
    session_factory: sessionmaker[Session] | None = None,
    settings: Settings | None = None,
    oauth_client: GoogleOAuthClient | None = None,
    chunk_pipeline: ChunkPipeline | None = None,
    chat_llm: ChatLLM | None = None,
    embedder: Embedder | None = None,
    rate_limiter: RateLimiter | None = None,
    agent_llm: AgentLLM | None = None,
    agent_llm_factory: Callable[[], AgentLLM] | None = None,
) -> FastAPI:
    """Build the AdvisorDesk FastAPI application.

    CONVENTIONS.md §5: no module-level engine/session/settings globals —
    everything request-scoped is stashed on `app.state` and read back
    through `app.routes.deps` (`get_session`, `get_settings`,
    `get_oauth_client`). The `/api/v1` prefix (PRD §5) is applied exactly
    here, once, so route modules declare bare paths.

    Args:
        session_factory: an optional SQLAlchemy session factory (from
            `app.db.make_session_factory`). `None` means DB-less: routes
            that depend on `get_session` raise `RuntimeError` at request
            time rather than silently working. `app/main.py` is the only
            caller that wires a real one.
        settings: an optional `Settings` instance. `None` builds
            `Settings()` from the environment, which itself succeeds with
            zero env vars set (PRD §9 defaults).
        oauth_client: an optional `GoogleOAuthClient` (real
            `HttpxGoogleOAuthClient` or a test fake). `None` means no auth
            route that dereferences it may be exercised — mirrors
            `session_factory`'s DB-less mode; `app/main.py` is the only
            caller that wires a real one.
        chunk_pipeline: an optional `app.services.lifecycle.ChunkPipeline`.
            `None` wires `NoopChunkPipeline` instead — content lifecycle
            transitions (publish/archive/delete/update) all run end to end
            with no real embedding provider; this is still what DB-less
            tests and the OpenAPI baseline export get by omitting the
            argument. `app/main.py` (the real caller, since phase-3
            task-02) passes `EmbeddingChunkPipeline` instead — the
            parameter existed from phase-2 onward so that swap needed no
            signature change here.
        chat_llm: an optional `app.rag.synthesis.ChatLLM` (the real
            `OpenAICompatibleChatLLM` or a test fake, phase-4 task-02).
            `None` leaves `app.state.chat_llm` unset — DB-less/OpenAPI-
            export builds never dereference it; `app.routes.deps.
            get_chat_llm` raises `RuntimeError` if a real request ever
            tries. `app/main.py` is the only caller that wires a real one.
        embedder: an optional `app.rag.embeddings.Embedder` for
            `app.rag.retrieval.retrieve()`'s request-time query embedding
            (phase-4 task-02; test-author judgment call, controller-
            approved — mirrors `chat_llm`'s shape since nothing else on
            `app.state` supplies one testably). Same `None`/fail-loud
            contract as `chat_llm` above.
        rate_limiter: an optional `app.routes.ratelimit.RateLimiter` (phase-4 task-03, PRD §9).
            Unlike `chat_llm`/`embedder` above, `None` does NOT mean "unconfigured, fail loud at
            request time" — a `RateLimiter` has no external provider to fail without, so `None`
            resolves to a real, working `RateLimiter(resolved_settings)` right here, mirroring
            `chunk_pipeline`'s `NoopChunkPipeline` default instead. Deliberate: every phase-4
            task-02 test (`test_public_chat.py`, `test_public_chat_guards.py`) already calls
            `create_app()` with no `rate_limiter=` argument, predating this task — a fail-loud
            default would turn every `POST /public/chat` call in those pinned suites into an
            unhandled `RuntimeError`. An always-real default instead means rate limiting is
            simply always on, at the PRD §9 default caps, unless a caller injects a different
            (e.g. tightly-capped, test-only) instance — every cap-tripping test in
            `test_ratelimit.py` does exactly that. `app/main.py` still wires one built from the
            real `Settings` explicitly (same pattern as `chat_llm`/`embedder`) so the production
            caps are visibly, not implicitly, in force.
        agent_llm: an optional `app.agent.loop.AgentLLM` (a test fake — every pinned
            `tests/test_agent_endpoint.py` test forwards its own `FakeAgentLLM` here, phase-5
            task-03, PRD §5.4/§6) — returned AS-IS, unchanged, on every request that resolves it
            (`app.routes.deps.get_agent_llm`'s fallback branch). `None` leaves
            `app.state.agent_llm` unset; a real `/agent/chat` request then falls through to
            `agent_llm_factory` below, or raises `RuntimeError` if that is unset too.
        agent_llm_factory: an optional zero-argument callable returning a fresh
            `app.agent.loop.AgentLLM` on every call (fix round 1, finding C-3) — `app/main.py`
            is the only caller that wires a real one (`OpenAICompatibleAgentLLM.
            new_conversation`, bound to one boot-time instance sharing its `client`/`model`
            across every call). `app.routes.deps.get_agent_llm` prefers this over `agent_llm`
            whenever both are set, and calls it FRESH on every request — the fix for a
            process-lifetime singleton's per-exchange state (a queued parallel tool call, or an
            already-finished-turn flag) leaking into a different admin's later request. `None`
            (every pinned test's own path, and the OpenAPI baseline export) falls back to
            `agent_llm` above.

    Returns:
        A configured `FastAPI` app instance.
    """
    resolved_settings = settings if settings is not None else Settings()

    app = FastAPI(title="AdvisorDesk API")
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.oauth_client = oauth_client
    # Annotated so mypy checks `NoopChunkPipeline` (and any caller-supplied
    # `chunk_pipeline`) against the `ChunkPipeline` Protocol here, statically —
    # `app.state` is untyped, so without this the assignment below is the only
    # place Protocol drift could be caught, and mypy skips it silently
    # (review finding F6).
    resolved_pipeline: ChunkPipeline = (
        chunk_pipeline if chunk_pipeline is not None else NoopChunkPipeline()
    )
    app.state.chunk_pipeline = resolved_pipeline
    app.state.chat_llm = chat_llm
    app.state.embedder = embedder
    app.state.agent_llm = agent_llm
    app.state.agent_llm_factory = agent_llm_factory
    # `None` -> a real, working default (docstring above) — unlike `chat_llm`/`embedder`, never
    # left unset: `app.routes.deps.get_rate_limiter` has no fail-loud RuntimeError branch at all.
    app.state.rate_limiter = (
        rate_limiter if rate_limiter is not None else RateLimiter(resolved_settings)
    )
    # Phase-6 task-01 (PRD §9/§9.1): one process-lifetime `LatencyTracker`, always real (no
    # injection point in `create_app`'s own signature — unlike `rate_limiter`, nothing needs to
    # override it: no test asserts on a specific window/clock, only on `app.state.latency_tracker`
    # existing and accumulating real samples). Read directly off `app.state` by
    # `app.routes.public_routes.public_chat`'s `on_first_event` closure and by tests; never
    # exposed through any route (§5 surface stays frozen).
    app.state.latency_tracker = LatencyTracker()

    # `LatencyMiddleware` is added BEFORE `CORSMiddleware` below so CORS ends up OUTERMOST in the
    # resulting stack (`Starlette.add_middleware` prepends — the most-recently-added middleware
    # wraps everything else) — the conventional ordering: CORS headers must reach every response,
    # including ones `LatencyMiddleware`'s own inner layers never see (e.g. a CORS-intercepted
    # preflight `OPTIONS` never reaches the router, so it never gets a meaningless timing line
    # either).
    app.add_middleware(LatencyMiddleware, tracker=app.state.latency_tracker)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    # mcp-oauth task-02: the ONE sanctioned exception to "all routes live under /api/v1"
    # (CONVENTIONS.md §5) — RFC 9728 §3 / RFC 8414 §3 mandate these two discovery documents at
    # the domain root. No prefix; unconditional (unlike `mount_mcp_http` below, NOT gated on
    # `mcp_http_enabled` — a client must be able to discover this server's OAuth wiring even
    # before the MCP endpoint itself is turned on).
    app.include_router(discovery_router)

    app.include_router(health_router, prefix=_API_PREFIX)
    app.include_router(auth_router, prefix=_API_PREFIX)
    app.include_router(content_router, prefix=_API_PREFIX)
    app.include_router(public_router, prefix=_API_PREFIX)
    app.include_router(agent_router, prefix=_API_PREFIX)
    # mcp-oauth plan, task 04: unconditional, unlike `mount_mcp_http` below — DCR must be
    # reachable even before the MCP HTTP endpoint itself is turned on (mirrors `discovery_router`
    # above, which is unconditional for the same "a client must be able to discover/register
    # before the resource is live" reason).
    app.include_router(oauth_router, prefix=_API_PREFIX)

    # PRD §3 MCP exposure rule: OFF by default: the route doesn't exist at all unless
    # explicitly enabled, and even then sits behind the same `require_admin` gate as every
    # REST admin route (`app.mcp.server.mount_mcp_http`, phase-5 task-01).
    if resolved_settings.mcp_http_enabled:
        mount_mcp_http(app, path=f"{_API_PREFIX}/mcp")

    return app
