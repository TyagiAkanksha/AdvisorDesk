"""Request-scoped dependencies backing every route: DB session and settings.

CONVENTIONS.md §5: all shared state lives on `app.state`; routes read it
back through these dependencies rather than holding module-level globals.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session

from app.agent.loop import AgentLLM
from app.auth.oauth import GoogleOAuthClient
from app.config import Settings
from app.rag.embeddings import Embedder
from app.rag.synthesis import ChatLLM
from app.routes.metrics import LatencyTracker
from app.routes.ratelimit import RateLimiter
from app.services.errors import OAuthError
from app.services.lifecycle import ChunkPipeline


def get_session(request: Request) -> Iterator[Session]:
    """Yield a `Session` for one request; commit on success, rollback on error, always close.

    CONVENTIONS.md §3/§5: the transaction boundary belongs to the HTTP
    layer — services `flush()` but never `commit()`/`rollback()`
    themselves. Reads `request.app.state.session_factory`, set by
    `create_app`/`app/main.py`.

    Raises:
        RuntimeError: if the app was built without a session factory (a
            DB-less `create_app()`, e.g. for the OpenAPI export or
            config-only tests) — a route depending on `get_session` must
            fail loudly rather than silently operating on no database.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "get_session() requires app.state.session_factory, but none was "
            "configured — this app was built by create_app() without a "
            "session_factory (DB-less mode). Only app/main.py wires a real one."
        )

    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_oauth_token_session(request: Request) -> Iterator[Session]:
    """Session dependency for `POST /oauth/token` ONLY: commits on success AND on `OAuthError`.

    Identical to `get_session` above except for one widened branch (mcp-oauth plan, task 07;
    task-07 review round 1, findings M-1/M-2). Three raise sites reachable from `/token` commit a
    write that was `flush()`ed (never `commit()`ed — CONVENTIONS.md §3) before the `OAuthError`
    that follows it, and every one of them is fail-closed, which is what makes committing on
    `OAuthError` safe here:

    1. `app.services.oauth_codes.consume_authorization_code`'s REPLAY branch — a code presented a
       second time calls `app.services.oauth_tokens.revoke_family` (killing every token minted
       from it) before raising `"Authorization code already used."`. RFC 6749 §10.4: an attacker
       who triggers replay detection must not get to keep the very tokens this mechanism exists to
       kill, so this write MUST survive the 400 that reports it.
    2. `app.services.oauth_tokens.rotate_refresh_token`'s REUSE branch — an already-rotated
       refresh token presented again calls `revoke_family` on the whole rotation family before
       raising `"Refresh token has been revoked."`. Same reasoning as (1).
    3. `app.services.oauth_tokens.issue_token_pair`'s owner check (`"User is no longer
       authorized."`) — reached from BOTH grants only AFTER the code's `consumed_at` (code grant)
       or the old refresh token's `revoked_at` + deleted `ApiToken` (refresh grant) have already
       been flushed. Committing here is fail-closed either way: a spent code stays spent, and a
       dead-end refresh stays revoked with no replacement issued — never a live grant plus a
       silently-discarded revocation.

    Every OTHER `OAuthError` this endpoint raises (`invalid_request`/`invalid_client`/an ordinary
    `invalid_grant`/`invalid_target`/`invalid_scope` — an unknown code, an expired token, a PKCE
    mismatch, a wrong client/resource/scope) has flushed nothing at all by the time it's raised, so
    committing on those is a plain no-op: there is nothing to lose by not rolling back. A
    non-`OAuthError` exception (a genuine bug, or `RateLimitedError` from the rate-limit check that
    runs before any DB write) still rolls back, exactly like `get_session`.

    A narrower marker (e.g. an `OAuthError` subclass raised only by the three sites above, with
    this dependency committing only on that subclass) would be strictly safer hygiene — ledgered
    for the mcp-oauth final whole-branch review rather than done now, since today's blanket
    "commit on any `OAuthError`" is empirically not too wide (all three reachable pre-raise-write
    sites are fail-closed, and the other 15+ raise sites flush nothing at all).

    Raises:
        RuntimeError: same guard as `get_session` — the app was built without a session factory.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "get_oauth_token_session() requires app.state.session_factory, but none was "
            "configured — this app was built by create_app() without a session_factory "
            "(DB-less mode)."
        )

    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except OAuthError:
        session.commit()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    """Return the `Settings` instance `create_app` stored on `app.state`."""
    return cast(Settings, request.app.state.settings)


def get_oauth_client(request: Request) -> GoogleOAuthClient:
    """Return the `GoogleOAuthClient` `create_app` stored on `app.state` (PRD §5.1).

    `None` (a `create_app()` built without an `oauth_client`, e.g. the
    OpenAPI baseline export) is never dereferenced here — only routes that
    actually call a method on the returned client would fail, and no
    DB-less/schema-only caller does that.
    """
    return cast(GoogleOAuthClient, request.app.state.oauth_client)


def get_chunk_pipeline(request: Request) -> ChunkPipeline:
    """Return the `ChunkPipeline` `create_app` stored on `app.state` (PRD §4 lifecycle seam).

    `create_app` always resolves this to a concrete `ChunkPipeline`
    (`NoopChunkPipeline` by default, task-03's `RecordingChunkPipeline` fake
    in tests, the real phase-3 pipeline later) — never `None` — so, unlike
    `get_oauth_client`/`get_session`, there is no DB-less/unset case to
    document here.
    """
    return cast(ChunkPipeline, request.app.state.chunk_pipeline)


def get_chat_llm(request: Request) -> ChatLLM:
    """Return the `ChatLLM` `create_app` stored on `app.state` (PRD §7.5 synthesis seam).

    Raises:
        RuntimeError: the app was built by `create_app()` without a `chat_llm` (a DB-less/
            schema-only app, e.g. the OpenAPI baseline export) — mirrors `get_session`'s
            fail-loud guard rather than silently dereferencing `None` at the first real call.
    """
    chat_llm = getattr(request.app.state, "chat_llm", None)
    if chat_llm is None:
        raise RuntimeError(
            "get_chat_llm() requires app.state.chat_llm, but none was configured — this app "
            "was built by create_app() without a chat_llm. Only app/main.py wires a real one."
        )
    return cast(ChatLLM, chat_llm)


def get_embedder(request: Request) -> Embedder:
    """Return the `Embedder` `create_app` stored on `app.state` (phase-4 task-02).

    `app.rag.retrieval.retrieve()` needs a request-time `Embedder` to embed the user's question
    — `create_app`'s `embedder` parameter is the injectable seam for it, mirroring `chat_llm`'s
    own shape (test-author judgment call, controller-approved; `p4-t02-test-author.md`).

    Raises:
        RuntimeError: no `embedder` was configured — same fail-loud guard as `get_chat_llm`/
            `get_session`.
    """
    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise RuntimeError(
            "get_embedder() requires app.state.embedder, but none was configured — this app "
            "was built by create_app() without an embedder. Only app/main.py wires a real one."
        )
    return cast(Embedder, embedder)


def get_agent_llm(request: Request) -> AgentLLM:
    """Return a per-request `AgentLLM` (phase-5 task-03, PRD §5.4/§6).

    Fix round 1, finding C-3: prefers `app.state.agent_llm_factory` — a zero-argument callable
    that mints a FRESH `AgentLLM`-conforming object on every call (`app.main` wires
    `OpenAICompatibleAgentLLM.new_conversation`). Calling it fresh per request is what keeps an
    adapter's per-exchange state (a queued parallel tool call, or the "this turn already
    finished" flag) from leaking into a DIFFERENT admin's later request, or racing across
    threadpool workers on the same mutable object — both reproduced against the real provider
    before this fix (see `app.agent.llm`'s module docstring).

    Falls back to the legacy `app.state.agent_llm` — a single object returned as-is, unchanged
    across calls — when no factory is configured. Every test that calls
    `create_app(agent_llm=FakeAgentLLM(...))` directly relies on exactly this fallback (each
    such test drives at most one `/agent/chat` request per fake instance, so the fake's own lack
    of a `new_conversation()` method is never exercised); a DB-less/schema-only app (e.g. the
    OpenAPI baseline export) leaves both unset.

    Raises:
        RuntimeError: neither `app.state.agent_llm_factory` nor `app.state.agent_llm` is
            configured — this app was built by `create_app()` with no agent LLM seam at all.
            Only `app/main.py` wires a real one.
    """
    agent_llm_factory = getattr(request.app.state, "agent_llm_factory", None)
    if agent_llm_factory is not None:
        return cast(Callable[[], AgentLLM], agent_llm_factory)()
    agent_llm = getattr(request.app.state, "agent_llm", None)
    if agent_llm is None:
        raise RuntimeError(
            "get_agent_llm() requires app.state.agent_llm_factory or app.state.agent_llm, but "
            "neither was configured — this app was built by create_app() without an agent LLM "
            "seam. Only app/main.py wires a real one."
        )
    return cast(AgentLLM, agent_llm)


def get_rate_limiter(request: Request) -> RateLimiter:
    """Return the `RateLimiter` `create_app` stored on `app.state` (phase-4 task-03, PRD §9).

    `create_app` always resolves this to a concrete `RateLimiter` — never `None` — same
    always-resolved contract as `get_chunk_pipeline` (see `app.factory.create_app`'s
    `rate_limiter` docstring for why this seam, unlike `get_chat_llm`/`get_embedder`, has no
    fail-loud `RuntimeError` branch: a rate limiter has no external provider to fail without, so
    every app — including every pre-existing test that never passes `rate_limiter=` at all —
    gets a real, working default.
    """
    return cast(RateLimiter, request.app.state.rate_limiter)


def get_latency_tracker(request: Request) -> LatencyTracker:
    """Return the `LatencyTracker` `create_app` stored on `app.state` (phase-6 task-01, PRD §9.1).

    `create_app` always resolves this to a concrete `LatencyTracker` — never `None` — same
    always-resolved contract as `get_rate_limiter`/`get_chunk_pipeline`: nothing external can
    fail at construction time, so every app, including every pre-phase-6 test that never touches
    this seam at all, gets a real, working instance.
    """
    return cast(LatencyTracker, request.app.state.latency_tracker)
