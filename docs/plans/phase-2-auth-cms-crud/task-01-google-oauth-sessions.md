---
id: task-01
phase: phase-2-auth-cms-crud
depends_on: [phase-1-skeleton/task-03]
status: planned
spec: advisordesk-prd.md §5.1, §4.1, §9
---

# task-01 — Google OAuth, signed sessions, allowlist, require_admin

## Goal

All four §5.1 auth routes work: Google consent redirect, code exchange with `ADMIN_EMAILS`
rejection and §4.1 reactivating upsert, signed HttpOnly session cookie, logout, `/auth/me`. The
`require_admin` dependency produced here guards every admin surface for the rest of the build
(routes, `/agent/chat`, MCP actor stamping).

## Context (read ONLY these)

- `advisordesk-prd.md` §5.1 (routes), §4.1 (users soft delete: upsert reactivates; soft-deleted
  session user ⇒ unauthenticated), §9 (cookie/allowlist rules).
- `CONVENTIONS.md` §3–§5 (services/errors/factory patterns), §10 (injectable seams).

## Files

- Create: `apps/api/app/auth/{oauth.py,sessions.py,deps.py}`,
  `apps/api/app/services/users.py`, `apps/api/app/routes/auth_routes.py`,
  `apps/api/app/models/schemas/auth.py`
- Create: `apps/api/tests/test_auth_endpoints.py`, `apps/api/tests/auth_helpers.py`
- Modify: `apps/api/app/factory.py` (include router), `apps/api/openapi.json` + both codegens

## Interfaces

- **Consumes:** `create_app`/`Settings`/`get_session` (p1-t03); `User` model + `active_select`
  (p1-t02).
- **Produces (later tasks rely on — produce exactly):**
  - `app.auth.oauth`: `class GoogleOAuthClient(Protocol)` with
    `authorization_url(state) -> str` and `exchange_code(code) -> GoogleIdentity`
    (`GoogleIdentity = {email, name, avatar_url}`); real httpx impl + the protocol is the test
    seam. Wired via `app.state.oauth_client` (factory param `oauth_client=None`).
  - `app.auth.sessions`: `issue_cookie(response, user_id, settings)`,
    `read_user_id(request, settings) -> uuid.UUID | None` (itsdangerous-signed, HttpOnly,
    SameSite=Lax, Secure when not dev).
  - `app.auth.deps`: `require_admin(...) -> AdminPrincipal` (frozen dataclass:
    `user_id, email, name`) — raises `AuthRequiredError` when no/invalid cookie **or the user row
    is soft-deleted** (§9). Consumed by every admin route, `/agent/chat` (p5-t03), MCP actor
    stamping (p5-t01).
  - `app.services.users`: `upsert_from_google(session, identity) -> User` — insert or update by
    email; flips `is_deleted=False` on a soft-deleted row (§4.1); refreshes name/avatar.
  - Routes (operation_ids): `auth_login`, `auth_callback`, `auth_logout`, `auth_me`
    (`MeResponse{id,email,name,avatar_url}`).
  - Test helper `auth_helpers.py`: `login_as(client, email)` — drives the fake OAuth flow; used
    by every later admin-route test.

## Steps (TDD)

- [ ] **Step 1: Failing endpoint tests** (`test_auth_endpoints.py`, fake OAuth client injected):
  `/auth/login` → 307 to the fake consent URL; callback with allowlisted email → cookie set +
  user row created; callback with unlisted email → 403 envelope, no row; callback for an existing
  soft-deleted allowlisted user → **same row id, `is_deleted` now False** (§4.1 pin); `/auth/me`
  without cookie → 401; with cookie → MeResponse; after the user row is soft-deleted directly in
  the DB → 401 (§9 pin); `/auth/logout` clears the cookie.
- [ ] **Step 2:** `uv run pytest tests/test_auth_endpoints.py -q` → FAIL (modules missing).
- [ ] **Step 3: Implement** `oauth.py`, `sessions.py`, `users.py`, `deps.py`, `auth_routes.py`,
  factory wiring — minimal code to green, no try/except in routes (errors via the typed family).
- [ ] **Step 4:** run → PASS (DB-fixture tests skip without `TEST_DATABASE_URL`, as designed).
- [ ] **Step 5: Baseline:** regenerate `openapi.json` + both apps' codegen (same commit).
- [ ] **Step 6: Gates → commit:**
  `feat(api): google oauth + sessions + require_admin (phase-2 task-01)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_auth_endpoints.py -q   # all passed
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json  # regenerated in-commit
grep -n "operation_id" app/routes/auth_routes.py    # auth_login/auth_callback/auth_logout/auth_me
```

## Acceptance

- All four §5.1 routes behave as specified; unlisted emails rejected before any row write.
- Reactivation pin: soft-deleted allowlisted user logs in → same `id`, active again (§4.1).
- Soft-deleted session user gets 401 on every `require_admin` surface (§9).
- Cookie is HttpOnly + signed; no session data stored client-readable.
