---
id: task-04
phase: phase-6-deployment
depends_on: [phase-5-mcp-agent/task-01]
status: planned
spec: advisordesk-prd.md §3 (MCP exposure), §9 (auth security) + owner decision 2026-08-08 (streamable-HTTP exposure for Claude connectors)
---

# task-04 — MCP bearer-token auth

## Goal

The mounted MCP endpoint (`/api/v1/mcp`) accepts **either** the existing admin session cookie
**or** an `Authorization: Bearer` token, so a deployed Claude connector (which can send an
Authorization header but never a cookie) can use it. Tokens are minted by a script — the §5
REST surface stays frozen (no new routes, OpenAPI baseline diff empty). `GET /api/v1/mcp`
returns 405 (phase-5 final-review t01-M8 fix).

## Context (read ONLY these)

- `app/mcp/server.py` — `_AdminGatedMcpApp.__call__` is the auth gate to extend;
  `mount_mcp_http` registers the bare-path `Route` + `Mount` (the 405 change lands here).
- `app/auth/deps.py` — `require_admin` / `AdminPrincipal`; the bearer path must resolve to the
  SAME `AdminPrincipal` shape so actor threading downstream is untouched.
- `app/models/base.py` + `app/models/users.py` — mixin conventions. **Design ruling:**
  `api_tokens` composes ONLY `TimestampMixin` (like the append-only tables) — PRD §4.1 scopes
  `SoftDeleteMixin` to `users`/`content`/`tags`, and revocation here is an honest hard `DELETE`
  via the script, with no restore path.
- `apps/api/alembic/versions/0002_chunks_embedding_1024_dims.py` — revision-chain tail to hook
  `0003` onto; follow its structure.
- `apps/api/scripts/export_mcp_tools.py` — script conventions (arg parsing, engine/session
  setup from env).

## Files

- Create: `apps/api/app/models/api_tokens.py`, `apps/api/app/auth/tokens.py`,
  `apps/api/scripts/mint_mcp_token.py`,
  `apps/api/alembic/versions/0003_api_tokens.py`
- Create: `apps/api/tests/test_mcp_bearer_auth.py`
- Modify: `apps/api/app/mcp/server.py` (gate + 405), `apps/api/app/models/__init__.py`
  (export, if the package re-exports models)

## Interfaces

- **Consumes:** `_AdminGatedMcpApp` / `mount_mcp_http` (p5-t01); `AdminPrincipal`;
  `get_active_user` (`app.services.users`); `Base`/`TimestampMixin`/`uuid_pk`.
- **Produces (later tasks rely on — produce exactly):**
  - `app.models.api_tokens.ApiToken`: `__tablename__ = "api_tokens"` — `id` (uuid_pk),
    `user_id` (UUID FK → `users.id`, nullable=False), `token_hash` (Text, unique,
    nullable=False — **sha256 hex of the FULL token string, never the raw token**),
    `name` (Text, nullable=False), plus `created_at` via `TimestampMixin`. Alembic `0003`
    creates it (down_revision = `0002`); downgrade drops it.
  - `app.auth.tokens`:
    - `mint_token() -> tuple[str, str]` — returns `(raw_token, token_hash)`; raw format is
      exactly `"adk_" + secrets.token_urlsafe(32)`; hash is `hashlib.sha256(raw.encode()).hexdigest()`.
    - `resolve_bearer_token(session: Session, raw_token: str) -> AdminPrincipal | None` —
      hashes, looks up `ApiToken` by `token_hash`, loads the owning user via
      `get_active_user` (so a soft-deleted admin's tokens die with the account), returns the
      same `AdminPrincipal(user_id, email, name)` shape or `None`. Constant work either way;
      never raises on unknown tokens.
  - `app/mcp/server.py` gate order in `_AdminGatedMcpApp.__call__`: if the request carries an
    `Authorization: Bearer <token>` header → resolve via `resolve_bearer_token` (on a worker
    thread, mirroring the existing `require_admin` offload; open/close its own session from
    `app.state.session_factory`); a resolvable token proceeds, an unresolvable one raises
    `AuthRequiredError` (→ the §9 401 envelope — do NOT fall through to the cookie path when a
    bearer header is present but bad). No bearer header → the existing `require_admin` cookie
    path, unchanged.
  - 405: the bare-path `Route` gets `methods=["POST"]` (Starlette then answers
    `GET/PUT/DELETE/...` with 405 + `Allow: POST` before auth runs — an unauthenticated GET is
    405, not 401). The `Mount` for sub-paths stays as-is.
  - `scripts/mint_mcp_token.py` — CLI over `DATABASE_URL` (env), NO new REST surface:
    - `--mint --email <admin-email> --name <label>`: resolves the ACTIVE user by normalized
      email (error message + exit 1 if missing/soft-deleted), inserts the hashed row, prints
      the raw token ONCE with a "shown once, store it now" warning. Never logs/stores the raw.
    - `--list`: id, name, user email, created_at — never hashes, never raw tokens.
    - `--revoke <token-id>`: hard-deletes the row (revocation semantics); exit 1 on unknown id.

## Steps (TDD)

- [ ] **Step 1: Failing tests** (`test_mcp_bearer_auth.py`; app built with
  `mcp_http_enabled=True` like `test_mcp_exposure.py` does):
  - no credentials → `POST /api/v1/mcp` 401 envelope (regression pin);
  - session cookie still works (one `initialize` round-trip — regression pin);
  - minted bearer token → `initialize` 2xx; `tools/list` returns the 8 tools;
  - a write tool called with a bearer token stamps the token OWNER's `user_id` as actor
    (create a draft; assert `author_id`);
  - unknown/garbage bearer → 401; bearer for a soft-deleted user → 401 (bad bearer with a
    VALID cookie also present → still 401: no fall-through);
  - `GET /api/v1/mcp` → 405;
  - `mint_token()` format pin: raw starts `adk_`, hash is sha256 hex of raw, DB stores only
    the hash (assert raw not in any `api_tokens` row);
  - script behaviors via its importable functions: mint for unknown email fails, revoke
    deletes the row and the token stops authenticating.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** model + migration + `tokens.py` + gate +
  script. **Step 4:** run → PASS; full api suite green; `uv run alembic upgrade head` /
  `downgrade -1` round-trips clean against the test DB.
- [ ] **Step 5: Baseline:** `git diff --exit-code openapi.json` — MUST be empty (no route
  changes; the §5 freeze is the point).
- [ ] **Step 6: Gates → commit:** `feat(api): MCP bearer-token auth + mint script (phase-6 task-04)`

## Verify

```bash
cd apps/api
set -a && source ../../.env && set +a
uv run pytest tests/test_mcp_bearer_auth.py -q
uv run pytest -q                                  # whole suite
git diff --exit-code openapi.json                 # §5 surface frozen
uv run python scripts/mint_mcp_token.py --list    # runs, table output
```

## Acceptance

- Cookie AND bearer both open the MCP endpoint; each resolves to a real `AdminPrincipal`;
  actor stamping via bearer verified by row evidence.
- Raw tokens exist only in the mint script's one-time stdout; DB carries sha256 hashes only;
  revocation is immediate (deleted row → 401).
- `GET /api/v1/mcp` → 405; OpenAPI baseline unchanged; migration up/down clean.
