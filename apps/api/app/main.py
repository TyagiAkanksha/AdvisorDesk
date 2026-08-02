"""Wiring only: engine, session factory, create_app — nothing imports main (CONVENTIONS.md §2).

CONVENTIONS.md §5: `app/main.py` is the only wiring point — load settings,
build the engine + session factory, call `create_app(...)`, expose `app`.
It's also the only place that requires `DATABASE_URL` and `SESSION_SECRET`
to be non-empty, unconditionally, and `GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI`/`ADMIN_EMAILS`/`NVIDIA_API_KEY`
to be non-empty outside dev (phase-2 task-01 review round 1, finding I1;
narrowed in review round 2 — see below; `ADMIN_EMAILS` added by the phase-2
final review, finding C-6; `NVIDIA_API_KEY` added by phase-3 task-02, same
dev-exempt/production-required shape). A real deployment booted without one
of these would otherwise sign every session with an empty secret / talk to
Google with an empty client id / lock every admin out of `/auth/callback`
silently / publish content whose chunks never actually embed, which is far
worse than a boot-time crash.
`Settings`/`create_app` themselves stay DB-less and secret-less so tests and
the OpenAPI baseline export don't need either a database or real OAuth
credentials.

Review round 2: round 1 made all five guards unconditional, which broke the
documented offline dev path (README: `cp .env.example .env`, set
`DATABASE_URL`, `docker compose --profile local-db up`) — `.env.example`
ships the three `GOOGLE_*` vars empty, and Google credentials are
unobtainable offline by definition, so the api container crash-looped on
every fresh clone. `database_url`/`session_secret` stay unconditional (an
empty/known session-signing key is fail-open and never allowed, in any
environment); the three `GOOGLE_*` guards now fire only when
`not settings.is_dev` — in development the app boots without Google
credentials and admin login simply won't work until they're set, exactly as
`.env.example`'s comments now say.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agent.llm import OpenAICompatibleAgentLLM
from app.auth.oauth import GoogleOAuthClient, HttpxGoogleOAuthClient
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.factory import create_app
from app.models import embedding_column_dims
from app.rag.embeddings import OpenAICompatibleEmbedder
from app.rag.pipeline import EmbeddingChunkPipeline
from app.rag.synthesis import OpenAICompatibleChatLLM
from app.routes.ratelimit import RateLimiter

logger = logging.getLogger(__name__)


def _require_nonempty(value: str, env_var: str, settings_attr: str) -> None:
    """Raise `RuntimeError` naming `env_var` if `value` (read from `settings_attr`) is empty.

    The one guard idiom `app.main` applies to every required-at-boot secret
    (finding I1) — `Settings()` itself never enforces this so it stays
    zero-env-var constructible (CONVENTIONS.md §5) for DB-less tests/the
    OpenAPI export.

    Args:
        value: the resolved setting's plaintext value.
        env_var: the environment variable name to name in the error.
        settings_attr: the `Settings` attribute `value` came from, named in
            the error so the message points at both the env var to set and
            the field that read it back empty.

    Raises:
        RuntimeError: `value` is empty.
    """
    if not value:
        raise RuntimeError(
            f"{env_var} is required to run app.main but Settings().{settings_attr} "
            f"is empty. Set the {env_var} environment variable (PRD §9)."
        )


settings: Settings = Settings()
_require_nonempty(settings.database_url.get_secret_value(), "DATABASE_URL", "database_url")
_require_nonempty(settings.session_secret.get_secret_value(), "SESSION_SECRET", "session_secret")
if not settings.is_dev:
    # Google credentials are unobtainable offline by definition, so these
    # three guards are dev-exempt (review round 2) — an offline
    # `cp .env.example .env` + local-db boot must succeed with them empty;
    # admin login just won't work until real credentials are set. Every
    # other environment (anything where `is_dev` is False, i.e.
    # `ENVIRONMENT=production`) still fails fast on any of the three being
    # empty, same as before.
    _require_nonempty(settings.google_client_id, "GOOGLE_CLIENT_ID", "google_client_id")
    _require_nonempty(
        settings.google_client_secret.get_secret_value(),
        "GOOGLE_CLIENT_SECRET",
        "google_client_secret",
    )
    _require_nonempty(settings.google_redirect_uri, "GOOGLE_REDIRECT_URI", "google_redirect_uri")
    # Phase-3 task-02: an empty NVIDIA_API_KEY in production boots cleanly
    # but every publish/edit-of-published call fails at the first real
    # embedding request (EmbeddingFailedError, PRD §4 atomicity rolls the
    # whole transaction back) — never silently, but also never until an
    # admin actually tries to publish, which is worse than failing at boot.
    # Dev-exempt for the same reason as the three GOOGLE_* guards: the
    # offline dev path (`cp .env.example .env`, which ships this blank)
    # must still boot; publishing just won't work until it's set
    # (`OpenAICompatibleEmbedder.from_settings` tolerates the empty value at
    # construction time — see its docstring — so this is purely a
    # request-time failure, not a boot-time one, when left unset in dev).
    _require_nonempty(
        settings.nvidia_api_key.get_secret_value(), "NVIDIA_API_KEY", "nvidia_api_key"
    )
    # Final review, finding C-6: an empty ADMIN_EMAILS in production boots
    # cleanly but locks EVERY Google identity out of `/auth/callback`
    # (`ForbiddenError` on every login attempt, PRD §5.1) — no admin could
    # ever sign in, and nothing at boot said so. Dev-exempt for the same
    # reason as the three GOOGLE_* guards above: the offline dev path must
    # still boot with it empty; admin login just won't work until it's set.
    _require_nonempty(settings.admin_emails, "ADMIN_EMAILS", "admin_emails")

# Review round 1, finding M3: `settings.embedding_dimensions` and
# `Chunk.embedding`'s actual pgvector column width (migration 0002) are two
# independent sources of truth for the same number, reconciled nowhere —
# a config-only change to EMBEDDING_DIMENSIONS with no matching migration
# would boot cleanly and only fail on the first real publish, as a
# dimension-mismatch `EmbeddingFailedError` from `app.rag.pipeline`'s own
# defense-in-depth guard, which is a request-time surprise for what is
# really a deployment configuration error. Asserted here, at boot, instead.
# `embedding_column_dims()` (final review: promoted from a private copy of
# this same read that used to live here, near-identical to
# `app.rag.pipeline`'s own) raises `RuntimeError` itself if the column isn't
# a dimensioned `Vector`, so no separate guard is needed before comparing.
_chunk_embedding_dim = embedding_column_dims()
if settings.embedding_dimensions != _chunk_embedding_dim:
    raise RuntimeError(
        f"settings.embedding_dimensions is {settings.embedding_dimensions} but "
        f"Chunk.embedding is a {_chunk_embedding_dim}-dim pgvector column "
        "(migration 0002) — these must match. Set EMBEDDING_DIMENSIONS to the "
        "column's width, or write/run a migration that resizes the column to "
        "match EMBEDDING_DIMENSIONS."
    )

if not settings.cors_origin_list:
    # Final review, finding C-1: an empty CORS_ORIGINS silently killed every
    # cross-origin request from apps/admin/apps/client in dev (no
    # Access-Control-Allow-Origin header on any preflight, so the browser
    # blocked the response before the admin app's sign-in flow ever saw it —
    # DOA at the user checkpoint). This stays a WARNING, not a boot-time
    # failure: a same-origin deployment (frontend served from the same
    # origin as the API, or a reverse proxy that makes them look same-origin
    # to the browser) legitimately needs no CORS allowlist at all, so
    # crash-failing here would be wrong for that case.
    logger.warning(
        "CORS_ORIGINS is empty — every cross-origin request (e.g. from apps/admin or "
        "apps/client on a different origin) will be rejected by the browser. Set "
        "CORS_ORIGINS in .env, or ignore this if the API is deployed same-origin with "
        "its frontend(s)."
    )

engine: Engine = make_engine(settings.database_url.get_secret_value())
session_factory: sessionmaker[Session] = make_session_factory(engine)
oauth_client: GoogleOAuthClient = HttpxGoogleOAuthClient.from_settings(settings)

# Phase-4 task-02: one `OpenAICompatibleEmbedder` shared by `EmbeddingChunkPipeline` (publish-
# time chunk embedding, `input_type="passage"`) and the request-time `embedder` seam
# `app.rag.retrieval.retrieve()` uses to embed the user's question (`input_type="query"`) — the
# `Embedder` protocol's own asymmetric-model docstring already covers both call shapes on one
# client, so there is no reason to build two.
embedder: OpenAICompatibleEmbedder = OpenAICompatibleEmbedder.from_settings(settings)
chunk_pipeline: EmbeddingChunkPipeline = EmbeddingChunkPipeline(embedder)
chat_llm: OpenAICompatibleChatLLM = OpenAICompatibleChatLLM.from_settings(settings)
# Phase-5 task-03: the real agent LLM (PRD §5.4/§6, v1.5) — same `from_settings` construction
# pattern as `chat_llm`/`embedder` above, wired here so `app.state.agent_llm` is never left
# unset in production (`app.routes.deps.get_agent_llm`'s fail-loud guard only ever fires for a
# DB-less/schema-only `create_app()`, e.g. the OpenAPI baseline export).
agent_llm: OpenAICompatibleAgentLLM = OpenAICompatibleAgentLLM.from_settings(settings)
# Phase-4 task-03: one process-lifetime `RateLimiter` shared by every `/public/chat` request
# (PRD §9) — same explicit-wiring pattern as `chat_llm`/`embedder` above, even though
# `create_app`'s own `rate_limiter=None` default would already build an equivalent instance
# (`app.factory.create_app`'s docstring) — the real caps stay visibly, not implicitly, in force.
rate_limiter: RateLimiter = RateLimiter(settings)

app: FastAPI = create_app(
    session_factory=session_factory,
    settings=settings,
    oauth_client=oauth_client,
    chunk_pipeline=chunk_pipeline,
    chat_llm=chat_llm,
    embedder=embedder,
    rate_limiter=rate_limiter,
    agent_llm=agent_llm,
)
