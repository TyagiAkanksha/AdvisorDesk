"""Typed application settings — the single config surface (CONVENTIONS.md §7).

PRD §9 defines the full env-var roster and defaults; every later task reads
configuration through `Settings` rather than `os.environ` directly.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings


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
    """

    nvidia_api_key: SecretStr = SecretStr("")
    database_url: SecretStr = SecretStr("")
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    admin_emails: str = ""

    # NVIDIA NIM's OpenAI-compatible base URL (PRD §7.2, v1.5) — embeddings
    # today (phase-3 task-02); the phase-4 chat/agent LLM client reuses the
    # same field. Config-only so a provider swap never touches code.
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    # `nvidia/nv-embedqa-e5-v5` (PRD §7.2, v1.5) — asymmetric embedding
    # model: `input_type="passage"` at publish time, `input_type="query"` at
    # retrieval time (phase-4 task-01 reuses `Embedder` for the latter).
    embedding_model: str = "nvidia/nv-embedqa-e5-v5"
    # The model's output vector width (PRD §7.2, v1.5) — also the
    # `chunks.embedding` pgvector column's dimension (migration 0002); a
    # provider/model swap with a different width updates this one value and
    # its matching Alembic migration together.
    embedding_dimensions: int = 1024

    # Chat-completion model for the client assistant's answer synthesis (PRD
    # §7.5) and, later, the admin agent loop (§5.4) — both talk to the same
    # NVIDIA NIM OpenAI-compatible endpoint (`llm_base_url` above). Pinned in
    # the phase-4 plan (`docs/plans/phase-4-rag-assistant/`); `CHAT_MODEL`
    # env-overridable per PRD §9 so a provider swap never touches code.
    chat_model: str = "meta/llama-3.1-8b-instruct"

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

    similarity_threshold: float = 0.35
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
    def is_dev(self) -> bool:
        """Whether `ENVIRONMENT` selects local-development defaults (task-01 brief).

        Anything other than `"production"` (case-insensitive) is treated as
        dev — the safer default when the var is unset entirely.
        """
        return self.environment.strip().lower() != "production"
