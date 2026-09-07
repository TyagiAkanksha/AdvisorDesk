"""Typed application settings — the single config surface (CONVENTIONS.md §7).

PRD §9 defines the full env-var roster and defaults; every later task reads
configuration through `Settings` rather than `os.environ` directly.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# P7 remediation (fresh-review F2): each provider's own well-known default `llm_base_url` —
# used ONLY to detect the one unambiguous misconfiguration shape (an operator flipped
# `llm_provider` but left `llm_base_url` at the OTHER provider's default), never to validate a
# legitimate custom/self-hosted OpenAI-compatible endpoint. Mirrors the literal values already
# documented on `llm_base_url`'s own field docstring below.
_PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}


class Settings(BaseSettings):
    """Application configuration sourced from environment variables (PRD §9).

    Field names are the lower-cased env-var names; pydantic-settings matches
    them case-insensitively by default, so `DATABASE_URL` populates
    `database_url` with no extra configuration.

    `Settings()` must succeed with **zero** environment variables set
    (CONVENTIONS.md §5) — this is what lets `create_app()` build a DB-less
    app for tests and the OpenAPI baseline export. `database_url` therefore
    defaults to `""` rather than being a required field; `app/main.py` is
    the only place that enforces it is non-empty before wiring a real
    engine.

    `nvidia_api_key`/`google_client_secret`/`session_secret`/`database_url`
    are `SecretStr` (phase-2 task-01 Settings hardening; `database_url`
    added in the phase-2 final review, finding C-5 — a Postgres DSN embeds
    the connection password, e.g. `postgresql://user:pw@host/db`, so a naive
    `repr(Settings(...))`/structured-log line leaked it exactly like the
    other three) so a naive `repr(Settings(...))` — e.g. via structured
    logging — never leaks a secret value; call sites read the plaintext via
    `.get_secret_value()`. Empty-string defaults become `SecretStr("")`,
    preserving the zero-env-vars constructibility guarantee above.

    `nvidia_api_key` (v1.5; phase-3 task-02) replaces the earlier
    `openai_api_key` field name: PRD §7.2 pins the NVIDIA NIM
    OpenAI-compatible endpoint (`https://integrate.api.nvidia.com/v1`,
    `NVIDIA_API_KEY`) as the live chat-completion/embedding provider, not
    OpenAI itself — `app.rag.embeddings.OpenAICompatibleEmbedder` talks to
    it via the `openai` SDK purely because that SDK speaks the compatible
    wire protocol, hence the class name staying provider-neutral while the
    settings field name reflects the actual provider.

    `llm_provider`/`openai_api_key` (v1.6; task 6R-14 — production-outage
    remediation) reintroduce a real provider switch: both NVIDIA NIM models
    this app was pinned to (`nvidia/nv-embedqa-e5-v5` embeddings,
    `meta/llama-3.1-8b-instruct` chat) went end-of-life (410 Gone) on
    2026-08-25/26, so OpenAI is now the default live provider (PRD §7.2
    v1.6). `llm_provider: Literal["openai", "nvidia"]` selects which
    credential field `llm_api_key` (below) resolves to; `nvidia_api_key`
    stays in place, unchanged, as the back-compat/future-re-enable branch —
    it is never removed, only no longer the default.
    """

    nvidia_api_key: SecretStr = SecretStr("")
    # v1.6 (task 6R-14): the new default credential — OpenAI's own API key.
    # Empty-`SecretStr` default and repr-hiding mirror every other secret
    # field, `nvidia_api_key` included.
    openai_api_key: SecretStr = SecretStr("")
    database_url: SecretStr = SecretStr("")
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    admin_emails: str = ""

    # v1.6 (task 6R-14): which provider `llm_api_key`/the embedding+chat/agent
    # clients resolve to. Defaults to `"openai"` — both NVIDIA NIM models
    # this app was pinned to are end-of-life (410 Gone, 2026-08-25/26); PRD
    # §7.2 v1.6 amendment. `"nvidia"` stays selectable as a back-compat/
    # future-re-enable branch (a 2048-dim NVIDIA embedding model exists but
    # would need a migration + full corpus re-embed — deliberately deferred,
    # not ruled out).
    llm_provider: Literal["openai", "nvidia"] = "openai"

    # OpenAI-compatible base URL (PRD §7.2). Defaults to OpenAI's own
    # endpoint (v1.6); pointed at NVIDIA NIM's compatible endpoint
    # (`https://integrate.api.nvidia.com/v1`) when `llm_provider="nvidia"`.
    # Config-only so a provider swap never touches code.
    llm_base_url: str = "https://api.openai.com/v1"
    # `text-embedding-3-small` (PRD §7.2, v1.6) — controller-verified live:
    # `dimensions=1024` returns exactly 1024-dim vectors, a drop-in for the
    # existing `chunks.embedding vector(1024)` column (no migration). Unlike
    # the earlier NVIDIA model, OpenAI's embedding model is symmetric — the
    # `input_type` asymmetry (`app.rag.embeddings.embed_texts`) is now
    # NVIDIA-branch-specific.
    embedding_model: str = "text-embedding-3-small"
    # The model's output vector width (PRD §7.2) — also the
    # `chunks.embedding` pgvector column's dimension (migration 0002); a
    # provider/model swap with a different width updates this one value and
    # its matching Alembic migration together. Unchanged by the v1.6
    # provider swap: `text-embedding-3-small@1024` is a drop-in for the
    # prior `nvidia/nv-embedqa-e5-v5@1024`.
    embedding_dimensions: int = 1024

    # Chat-completion model for the client assistant's answer synthesis (PRD
    # §7.5) and the admin agent loop (§5.4) — both talk to the same
    # OpenAI-compatible endpoint (`llm_base_url` above). `gpt-4o-mini` (PRD
    # §7.2, v1.6) — controller-verified live: responds and supports
    # tool-calling (the admin agent needs it). `CHAT_MODEL` env-overridable
    # per PRD §9 so a provider swap never touches code.
    chat_model: str = "gpt-4o-mini"

    # Not part of the PRD §9 env roster (phase-3 task-02 review round 1,
    # finding I1): the `openai` SDK's own defaults for an unconfigured
    # client are `read=600s` with `max_retries=2` (3 attempts total) — since
    # `app.rag.pipeline.EmbeddingChunkPipeline` calls the embedder inside the
    # same DB transaction it's about to `flush()` into (PRD §4 atomicity),
    # those defaults would hold that write transaction open for up to ~30
    # minutes on a stalled/misbehaving provider. `embedding_timeout_seconds`
    # bounds a single embedding request/attempt; `embedding_max_retries`
    # bounds how many times the SDK retries a failed one. Config-only (PRD
    # §7.2 "a provider swap never touches code") so a real deployment can
    # tighten both without a code change — phase-4's query-embedding path
    # (same `Embedder`, on the public chat request path where first-token
    # latency matters) may reuse a lower `embedding_timeout_seconds` than
    # publish-time bulk embedding needs.
    embedding_timeout_seconds: float = 30.0
    embedding_max_retries: int = 2

    # Not part of the PRD §9 env roster: the real `HttpxGoogleOAuthClient`
    # (app.auth.oauth, phase-2 task-01) needs a fixed, Google-console-
    # registered callback URL to exchange a code — this is that URL. Empty
    # by default so `Settings()`/`create_app()` stay zero-env-var
    # constructible; only a real deployment sets it.
    google_redirect_uri: str = ""

    # Also not part of the PRD §9 env roster: the minimal signal
    # `app.auth.sessions.issue_cookie` needs to decide the session cookie's
    # `Secure` flag ("Secure when not dev" — task-01 brief). Defaults to
    # `"development"` so local `docker compose up`/tests (plain HTTP) get a
    # cookie that actually round-trips; a real deployment sets
    # `ENVIRONMENT=production`.
    environment: str = "development"

    # Also not part of the PRD §9 env roster (phase-2 task-01 review M8
    # resolution, amended before task-04): the admin SPA's origin.
    # `app.routes.auth_routes.auth_callback` 303-redirects here on success
    # so the browser lands back in the admin app after Google sign-in
    # instead of dead-ending on a bodyless response on the API's own
    # origin. Defaults to the local admin dev server so
    # `Settings()`/`create_app()` stay zero-env-var constructible; a real
    # deployment sets `ADMIN_APP_URL` to the admin app's real origin.
    admin_app_url: str = "http://localhost:3001"

    # Implementation trap: pydantic-settings JSON-decodes "complex" field
    # types (list[str], dict, ...) from their env-var string BEFORE
    # validation, and raises on a bare comma-separated value like
    # "http://a,http://b" (it is not valid JSON). So this stays a plain
    # `str` field, parsed by hand via the `cors_origin_list` property below.
    cors_origins: str = ""

    # Retuned 0.35 -> 0.5 on 2026-09-06 for the OpenAI text-embedding-3-small
    # provider (PRD §7.3). Measured over seed/eval_questions.yaml against the live
    # corpus: answerable questions score top-similarity 0.645-0.806, unanswerable
    # 0.356-0.403 — a clean gap. The old 0.35 sat BELOW the unanswerable max, so
    # off-topic questions surfaced a spurious chunk (a citation on a refusal); 0.5
    # is centred in the gap (~0.1 margin each side) so answerable keep all their
    # chunks and unanswerable retrieve nothing. Env-configurable.
    similarity_threshold: float = 0.5
    rate_limit_per_min: int = 10
    rate_limit_per_day: int = 50
    session_create_per_day: int = 20
    mcp_http_enabled: bool = False

    # Not part of the PRD §9 env roster: default lifetime for a freshly-minted MCP bearer token
    # (phase-6 remediation task-09, WR-02 residual, migration 0006). `scripts/mint_mcp_token.py
    # ::mint` stamps `expires_at = now() + mcp_token_ttl_days` on every fresh mint; a pre-existing
    # token (minted before migration 0006 ever ran) keeps its `NULL` expires_at — "no expiry" —
    # regardless of this value. 90 days is a sane default for a long-lived connector credential
    # (PRD §3) without being effectively permanent; `MCP_TOKEN_TTL_DAYS` overrides it per
    # deployment.
    mcp_token_ttl_days: int = 90

    # mcp-oauth plan, task-01: an OAuth 2.1 authorization server co-hosted with the existing
    # `/api/v1/mcp` endpoint (docs/plans/mcp-oauth/DESIGN.md §"Token & data model"). All six
    # fields are zero-env-var constructible (CONVENTIONS.md §5); `oauth_issuer_url` is validated
    # below and `mcp_resource_url` (the property further down) derives the canonical MCP resource
    # URI from it.
    oauth_issuer_url: str = "http://localhost:8000"
    oauth_access_token_ttl_minutes: int = 60
    oauth_refresh_token_ttl_days: int = 30
    oauth_auth_code_ttl_seconds: int = 60
    oauth_rate_limit_per_min: int = 30
    oauth_max_clients: int = 200

    @field_validator("oauth_issuer_url")
    @classmethod
    def _validate_oauth_issuer_url(cls, value: str) -> str:
        """`oauth_issuer_url` must be a full `http://`/`https://` URL (mcp-oauth task-01).

        Every OAuth metadata document (`.well-known/oauth-authorization-server`, the RFC 8707
        resource indicator on minted tokens) is built by string-composing onto this value —
        `mcp_resource_url` below does exactly that — so a bare hostname or a relative path would
        silently produce a malformed URI everywhere downstream instead of failing loudly here.

        Strips exactly one trailing slash so a copy-pasted issuer URL with a trailing `/` doesn't
        compose into an accidental `//api/v1/mcp`.

        Raises:
            ValueError: `value` doesn't start with `http://` or `https://` — surfaces to the
                caller as a pydantic `ValidationError` with `errors()[0]["type"] ==
                "value_error"`.
        """
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError(
                f"oauth_issuer_url must start with http:// or https://, got {value!r}."
            )
        return value.removesuffix("/")

    @model_validator(mode="after")
    def _warn_on_provider_base_url_mismatch(self) -> Settings:
        """P7 remediation (fresh-review F2): the provider "switch" is five independently-settable
        fields (`llm_provider`, `llm_base_url`, `embedding_model`, `chat_model`,
        `embedding_dimensions`) with nothing tying them together — flipping `llm_provider` alone
        does not touch the other four, so `llm_provider="nvidia"` with `llm_base_url` left at its
        OpenAI default boots clean and only fails opaquely at the first real request (a
        same-shape auth/format error from the wrong endpoint, task 6R-14's own outage class).

        Deliberately a WARNING, never a validation error: `llm_base_url`'s own field docstring
        allows an arbitrary OpenAI-compatible endpoint (a self-hosted proxy, a third-party
        gateway), so raising here would block a legitimate custom config this field explicitly
        supports — exactly the "don't block valid custom configs" constraint this check must
        respect. It fires ONLY when `llm_base_url` equals the OTHER provider's own well-known
        default (`_PROVIDER_DEFAULT_BASE_URLS`) — the one shape that is unambiguously a mistake
        (an operator flipped `llm_provider` and forgot the companion fields) — never for a
        custom/self-hosted URL, which by construction matches neither literal default.
        """
        other_provider = "nvidia" if self.llm_provider == "openai" else "openai"
        if self.llm_base_url == _PROVIDER_DEFAULT_BASE_URLS[other_provider]:
            logger.warning(
                "Settings: llm_provider=%s but llm_base_url=%s is the %s provider's own "
                "default — a provider swap usually also needs LLM_BASE_URL (and "
                "EMBEDDING_MODEL/CHAT_MODEL) updated to match llm_provider.",
                self.llm_provider,
                self.llm_base_url,
                other_provider,
            )
        return self

    @property
    def llm_api_key(self) -> SecretStr:
        """The credential for the active `llm_provider` (v1.6, task 6R-14).

        Returns `openai_api_key` when `llm_provider == "openai"` (the
        default), else `nvidia_api_key` — the ONE field
        `OpenAICompatibleEmbedder.from_settings`/`OpenAICompatibleChatLLM.
        from_settings`/`OpenAICompatibleAgentLLM.from_settings` all read,
        so a provider switch never touches which field a call site names.
        Returns the `SecretStr` itself, never the unwrapped plaintext — a
        naive caller that logs `settings.llm_api_key` instead of calling
        `.get_secret_value()` must not leak a real key, same as every other
        secret field.
        """
        if self.llm_provider == "openai":
            return self.openai_api_key
        return self.nvidia_api_key

    @property
    def cors_origin_list(self) -> list[str]:
        """The `cors_origins` env value split into an allowlist (PRD §9 CORS).

        Splits on comma, strips whitespace from each entry, and drops empty
        entries (a stray trailing comma or blank env var never produces a
        blank origin).
        """
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def admin_email_set(self) -> set[str]:
        """The `ADMIN_EMAILS` allowlist, parsed once (PRD §5.1/§9).

        Comma-separated, case-insensitively compared (email local/domain
        parts are conventionally treated case-insensitively) — mirrors
        `cors_origin_list`'s parsing shape.
        """
        return {email.strip().lower() for email in self.admin_emails.split(",") if email.strip()}

    @property
    def mcp_resource_url(self) -> str:
        """The canonical MCP resource URI, derived from `oauth_issuer_url` (mcp-oauth task-01).

        This is the RFC 8707 `resource` value every OAuth-issued (and, from this task on, every
        `scripts/mint_mcp_token.py`-minted) token targeting this MCP server is scoped to.
        """
        return f"{self.oauth_issuer_url}/api/v1/mcp"

    @property
    def is_dev(self) -> bool:
        """Whether `ENVIRONMENT` selects local-development defaults (task-01 brief).

        Anything other than `"production"` (case-insensitive) is treated as
        dev — the safer default when the var is unset entirely.
        """
        return self.environment.strip().lower() != "production"
