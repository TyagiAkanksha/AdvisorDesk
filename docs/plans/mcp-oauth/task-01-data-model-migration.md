---
id: mcp-oauth-t01
phase: mcp-oauth
depends_on: []
status: planned
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 01 — Data model + Alembic migration 0007 + OAuth settings ★

## Goal

Land every persistent + configuration primitive the OAuth server needs, with nothing that uses
them yet: four new tables (`oauth_clients`, `oauth_authorization_codes`, `oauth_refresh_tokens`,
`oauth_consents`), three nullable columns on `api_tokens`, a shared token-hashing leaf in
`app/services`, and six new `Settings` fields. The CLI mint script starts stamping `resource`.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"Token & data model", §"Security / threat model",
  §"Decisions pinned at plan time".
- `CONVENTIONS.md` §2 (layering), §3 (services), §4 (models: uuid PKs, `TimestampMixin`),
  §8 (Alembic only), §10 (tests).
- `apps/api/app/models/base.py`, `apps/api/app/models/api_tokens.py`,
  `apps/api/app/models/users.py`, `apps/api/app/models/__init__.py`.
- `apps/api/alembic/versions/0006_api_tokens_expires_at.py` (migration shape + docstring style).
- `apps/api/app/config.py` lines 28–190 (field style, `mcp_token_ttl_days`, `is_dev`).
- `apps/api/app/auth/tokens.py` lines 1–60 (`mint_token`, `_TOKEN_PREFIX`).
- `apps/api/scripts/mint_mcp_token.py` (`mint()` builds the `ApiToken` row).
- `apps/api/tests/conftest.py` (`tmp_engine`, `db_session`), `apps/api/tests/test_models_schema.py`
  (`test_orm_metadata_matches_migration_head` — the drift guard your migration must satisfy).

## Files

**Create**
- `apps/api/app/models/oauth.py` — the four ORM models.
- `apps/api/alembic/versions/0007_oauth_tables.py` — `revision = "0007"`, `down_revision = "0006"`.
- `apps/api/app/services/token_hashing.py` — pure leaf: `hash_token`, `generate_token`.
- `apps/api/tests/test_oauth_models_migration.py` (DB), `apps/api/tests/test_token_hashing.py` (unit),
  `apps/api/tests/test_oauth_settings.py` (unit).

**Modify**
- `apps/api/app/models/api_tokens.py` — add `client_id`, `resource`, `last_used_at`.
- `apps/api/app/models/__init__.py` — re-export `OAuthClient`, `OAuthAuthorizationCode`,
  `OAuthRefreshToken`, `OAuthConsent`; update the docstring's table count.
- `apps/api/app/config.py` — six fields + one property + one validator (below).
- `apps/api/app/auth/tokens.py` — `mint_token()` delegates to `generate_token("adk_")`
  (behavior and return shape unchanged; `_TOKEN_PREFIX` stays exported).
- `apps/api/scripts/mint_mcp_token.py` — `mint()` stamps `resource=settings.mcp_resource_url`,
  `client_id=None`.
- `.env.example` — NOT in this task (task 02 documents the env vars).

## Interfaces

**Consumes:** `Base`, `TimestampMixin`, `uuid_pk` from `app.models.base`; `User`, `ApiToken`.

**Produces exactly:**

```python
# app/models/oauth.py
class OAuthClient(Base, TimestampMixin):
    __tablename__ = "oauth_clients"
    client_id: Mapped[str] = mapped_column(Text, primary_key=True)      # the RFC 7591 id IS the key
    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)  # postgresql.ARRAY

class OAuthAuthorizationCode(Base, TimestampMixin):
    __tablename__ = "oauth_authorization_codes"
    id: Mapped[uuid.UUID] = uuid_pk()
    code_hash: Mapped[str]            # Text, unique, not null
    client_id: Mapped[str]            # Text, FK oauth_clients.client_id ondelete="CASCADE", not null, index=True
    user_id: Mapped[uuid.UUID]        # UUID, FK users.id, not null
    redirect_uri: Mapped[str]         # Text not null
    code_challenge: Mapped[str]       # Text not null
    resource: Mapped[str]             # Text not null
    scope: Mapped[str]                # Text not null
    expires_at: Mapped[datetime]      # DateTime(timezone=True) not null
    consumed_at: Mapped[datetime | None]

class OAuthRefreshToken(Base, TimestampMixin):
    __tablename__ = "oauth_refresh_tokens"
    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str]           # Text, unique, not null
    client_id: Mapped[str]            # Text, FK oauth_clients.client_id ondelete="CASCADE", not null, index=True
    user_id: Mapped[uuid.UUID]        # UUID, FK users.id, not null
    access_token_id: Mapped[uuid.UUID | None]   # UUID, FK api_tokens.id ondelete="SET NULL", nullable
    family_id: Mapped[uuid.UUID]      # UUID not null, index=True  (= the originating authorization code's id)
    rotated_from_id: Mapped[uuid.UUID | None]   # UUID, FK oauth_refresh_tokens.id ondelete="SET NULL", nullable
    resource: Mapped[str]             # Text not null
    scope: Mapped[str]                # Text not null
    expires_at: Mapped[datetime]      # DateTime(timezone=True) not null
    revoked_at: Mapped[datetime | None]

class OAuthConsent(Base, TimestampMixin):
    __tablename__ = "oauth_consents"
    __table_args__ = (UniqueConstraint("user_id", "client_id", name="uq_oauth_consents_user_id_client_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID]        # UUID, FK users.id, not null
    client_id: Mapped[str]            # Text, FK oauth_clients.client_id ondelete="CASCADE", not null
    scope: Mapped[str]                # Text not null
    revoked_at: Mapped[datetime | None]

# app/models/api_tokens.py — additions (all nullable so every existing ApiToken(...) call site keeps working)
client_id: Mapped[str | None] = mapped_column(Text, ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=True, index=True)
resource: Mapped[str | None] = mapped_column(Text, nullable=True)
last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# app/services/token_hashing.py
def hash_token(raw: str) -> str: ...                       # hashlib.sha256(raw.encode()).hexdigest()
def generate_token(prefix: str) -> tuple[str, str]: ...    # (prefix + secrets.token_urlsafe(32), hash_token(raw))

# app/config.py — new fields (all zero-env constructible)
oauth_issuer_url: str = "http://localhost:8000"     # validator: strip trailing "/"; must start with http:// or https://
oauth_access_token_ttl_minutes: int = 60
oauth_refresh_token_ttl_days: int = 30
oauth_auth_code_ttl_seconds: int = 60
oauth_rate_limit_per_min: int = 30
oauth_max_clients: int = 200
@property
def mcp_resource_url(self) -> str: return f"{self.oauth_issuer_url}/api/v1/mcp"
```

Index names follow `Base.metadata`'s naming convention (`ix_<table>_<column>`); the migration must
create exactly what `compare_metadata` expects (the existing drift test enforces this).

## Steps (TDD)

- [ ] **RED — test-author writes and proves failing:**
  - `tests/test_oauth_models_migration.py` (uses `tmp_engine`/`db_session`):
    - `test_migration_head_creates_oauth_tables` — `sa.inspect(tmp_engine).get_table_names()`
      (schema-aware, as `test_inspector_sees_hnsw_and_fk_indexes` does) contains all four tables.
    - `test_api_tokens_has_new_nullable_columns` — inspector columns for `api_tokens` include
      `client_id`, `resource`, `last_used_at`, each `nullable=True`.
    - `test_legacy_api_token_constructor_still_inserts` — `ApiToken(user_id=…, token_hash=…, name=…)`
      flushes; `client_id`, `resource`, `last_used_at` read back `None`.
    - `test_deleting_client_cascades_to_dependents` — insert a client, a code, a refresh token, a
      consent, and an `ApiToken(client_id=…)`; `session.delete(client)`; flush; all four dependent
      rows are gone.
    - `test_consent_unique_per_user_client` — second `OAuthConsent` for the same
      `(user_id, client_id)` raises `IntegrityError` on flush.
    - `test_refresh_token_hash_unique` — duplicate `token_hash` raises `IntegrityError`.
  - `tests/test_token_hashing.py`: `test_generate_token_prefix_and_hash_roundtrip`
    (`raw.startswith("adkr_")`, `hash_token(raw) == hashed`, `len(hashed) == 64`);
    `test_mint_token_unchanged_shape` — `app.auth.tokens.mint_token()` returns an `adk_` raw and
    its sha256 hex.
  - `tests/test_oauth_settings.py`: `test_defaults_are_zero_env` (`Settings()` has the six
    defaults + `mcp_resource_url == "http://localhost:8000/api/v1/mcp"`);
    `test_issuer_trailing_slash_stripped` (`Settings(oauth_issuer_url="https://x.example/")` →
    `"https://x.example"`); `test_issuer_must_be_http_url` (`Settings(oauth_issuer_url="x.example")`
    raises `ValidationError`).
  - `tests/test_mint_allowlist.py`-style check for the mint script: add to
    `tests/test_oauth_models_migration.py` — `test_mint_script_stamps_resource_and_null_client`
    (import the script the way `tests/test_mint_allowlist.py::_import_mint_script` does; call
    `mint(session, email=..., name=..., settings=Settings(session_secret="s", admin_emails=email,
    oauth_issuer_url="https://api.example"))`; the row has `resource == "https://api.example/api/v1/mcp"`
    and `client_id is None`).
  - Run `uv run pytest -q tests/test_oauth_models_migration.py tests/test_token_hashing.py tests/test_oauth_settings.py`
    → every test FAILS (ImportError / missing tables / missing attributes). Record the output.
- [ ] **GREEN — implementer:** write `app/models/oauth.py`, extend `api_tokens.py`, export from
  `app/models/__init__.py`, write migration `0007_oauth_tables.py` (`op.create_table` ×4 with
  explicit FKs/uniques/indexes, `op.add_column` ×3 + `op.create_index("ix_api_tokens_client_id", …)`;
  `downgrade` reverses in dependency order), `app/services/token_hashing.py`, the `Settings`
  fields/validator/property, `mint_token` delegation, and the mint-script stamp.
- [ ] Run the three new test files + `tests/test_models_schema.py` (drift guard) + `tests/test_mint_allowlist.py`
  → PASS.
- [ ] Full gates: `uv run ruff check --no-cache . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`.
- [ ] Commit: `feat(api): oauth data model, migration 0007, settings (mcp-oauth t01)` — path-scoped
  `git add` of the files listed above only.

## Verify

```bash
cd apps/api
uv run alembic upgrade head   # against a scratch DB, e.g. TEST_DATABASE_URL — never prod
uv run pytest -q tests/test_oauth_models_migration.py tests/test_token_hashing.py tests/test_oauth_settings.py tests/test_models_schema.py
uv run ruff check --no-cache . && uv run ruff format --check . && uv run mypy && uv run lint-imports
```

## Acceptance

- All named tests pass; `test_orm_metadata_matches_migration_head` still passes (no drift).
- `create_app()` with no args still succeeds (`tests/test_app_factory.py`).
- Every pre-existing test that constructs `ApiToken(...)` without the new kwargs is untouched and green.
- No `commit()` in services; models remain a pure leaf (`lint-imports` green).
- Reviewer (Opus) confirms: FK `ondelete` choices match the Interfaces block; hashes are sha256
  hex; the issuer validator rejects non-HTTP values and strips one trailing slash only.
