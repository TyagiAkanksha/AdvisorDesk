---
id: task-05
phase: phase-6-deployment
depends_on: [task-04]
status: built
spec: advisordesk-prd.md §9 (auth security) — phase-2 review findings t01-M6 (logout does not revoke) and t01-M7 (OAuth state not verified), owner-ratified for pre-deploy fix 2026-08-08
---

# task-05 — Auth hardening: logout revocation + OAuth state CSRF

## Goal

Two ledgered phase-2 Minors get real fixes before the site goes public: (i) `/auth/logout`
actually revokes outstanding session cookies (today it only clears the browser's copy — a
stolen cookie keeps working for 30 days), via a `users.session_epoch` counter; (ii) the OAuth
`state` round-trip is cryptographically verified (today the callback accepts any `state`),
closing login-CSRF. No REST surface change: same routes, same OpenAPI baseline.

## Context (read ONLY these)

- `app/auth/sessions.py` — the signed-cookie module to extend (payload today: bare
  `str(user_id)`).
- `app/auth/deps.py` — `require_admin`, where epoch validation lands.
- `app/routes/auth_routes.py` — login/callback/logout; note callback ALREADY declares 403 in
  `responses=` (`ForbiddenError`), so a state-mismatch 403 changes no OpenAPI.
- `app/services/users.py` — service-layer home for the epoch bump.
- `apps/api/alembic/versions/0003_api_tokens.py` (task-04) — chain `0004` after it.
- `tests/auth_helpers.py` + `tests/test_auth_endpoints.py` + `tests/test_auth_callback_redirect.py`
  + `tests/test_auth_security.py` — the merged tests this task's behavior change touches; the
  test-author owns updating them (they are this task's spec now) and pins the updated files.

## Files

- Create: `apps/api/app/auth/state.py`, `apps/api/alembic/versions/0004_users_session_epoch.py`
- Create: `apps/api/tests/test_auth_hardening.py`
- Modify: `apps/api/app/models/users.py`, `apps/api/app/auth/sessions.py`,
  `apps/api/app/auth/deps.py`, `apps/api/app/routes/auth_routes.py`,
  `apps/api/app/services/users.py`, and the four existing test files named above (drive the
  new state/epoch flows; updates authored + pinned by the test-author, not improvised by the
  implementer)

## Interfaces

- **Consumes:** `URLSafeTimedSerializer` pattern (`app.auth.sessions`); `ForbiddenError` /
  `AuthRequiredError`; task-04's migration as `down_revision`.
- **Produces (later tasks rely on — produce exactly):**

  **(i) Logout revocation — `users.session_epoch`:**
  - Migration `0004`: `users.session_epoch` `Integer, nullable=False, server_default="0"`;
    model field `session_epoch: Mapped[int]` (`default=0`).
  - `app.auth.sessions`: cookie payload becomes the signed dict `{"uid": str(user_id),
    "epoch": int}`. `issue_cookie(response, user_id, session_epoch, settings)` (positional,
    mirroring today's order + epoch). `read_user_id` is REPLACED by
    `read_session(request, settings) -> tuple[uuid.UUID, int] | None` — same never-raises
    contract; a legacy bare-string payload, missing key, or non-int epoch all return `None`
    (old cookies just re-login — acceptable, single admin; note it in the module docstring).
  - `require_admin`: after `get_active_user`, also require
    `cookie_epoch == user.session_epoch`, else `AuthRequiredError` (same 401 envelope).
  - `app.services.users.bump_session_epoch(session: Session, user_id: uuid.UUID) -> None` —
    `session_epoch += 1` + `updated_at` touch (CONVENTIONS §3: app-layer maintenance).
  - `/auth/logout`: keeps its no-auth idempotent-200 contract. Best-effort revocation: read
    the cookie via `read_session`; if present and the user row exists, call
    `bump_session_epoch` (add `Depends(get_session)` — no schema change); then clear the
    cookie exactly as today. No cookie / invalid cookie → still 200.
  - `/auth/callback`: `issue_cookie(response, user.id, user.session_epoch, settings)` — a
    re-login AFTER logout gets the bumped epoch and works.

  **(ii) OAuth state CSRF — signed state + double-submit cookie:**
  - `app.auth.state`: `mint_state(settings) -> str` — `URLSafeTimedSerializer` over
    `settings.session_secret`, salt `"advisordesk.auth.oauth-state"`, payload
    `secrets.token_urlsafe(16)`; `verify_state(value: str, settings) -> bool` — signature +
    `max_age=STATE_MAX_AGE_SECONDS = 600`; never raises.
  - `/auth/login`: `state = mint_state(settings)`; pass to `authorization_url(state)` AND set
    it as cookie `advisordesk_oauth_state` on the redirect response (HttpOnly, SameSite=Lax,
    `max_age=600`, `secure=not settings.is_dev`). The signature alone does not stop
    login-CSRF (an attacker can mint a valid state from their own `/auth/login`); the
    double-submit cookie binds the state to THIS browser — both checks are required.
  - `/auth/callback`, BEFORE `exchange_code`: require (a) `verify_state(state, settings)` and
    (b) `state == request.cookies.get("advisordesk_oauth_state")` — either failing →
    `ForbiddenError("OAuth state verification failed — restart sign-in.")` (403 §9 envelope,
    already declared). On success, delete the state cookie on the redirect response.

## Steps (TDD)

- [ ] **Step 1: Failing tests** (`test_auth_hardening.py` + updates to the four existing
  files):
  - logout revocation: login → `/auth/me` 200 → capture cookie → `/auth/logout` → replaying
    the CAPTURED cookie on `/auth/me` → 401; re-login → new cookie works; logout with no
    cookie → 200; a cookie legitimately signed at epoch N is dead once the row is at N+1
    (that IS the replay test — epochs are not forgeable client-side, the signature covers
    them);
  - migration pin: `users.session_epoch` exists, default 0;
  - state CSRF: `/auth/login` response's redirect URL `state` == its `advisordesk_oauth_state`
    cookie value; callback with a forged/unsigned `state` → 403 envelope; callback with a
    VALID-signature state but no/mismatched state cookie → 403 (the CSRF pin); expired state
    (monkeypatch `STATE_MAX_AGE_SECONDS` to 0) → 403; full happy round-trip through
    login-then-callback (TestClient cookie jar) → 303 + session cookie;
  - existing-file updates: `auth_helpers.login_as` drives login→callback so the state
    round-trip holds; direct-callback tests get a real minted state + cookie.
- [ ] **Step 2:** run → FAIL. **Step 3: implement.** **Step 4:** run → PASS; full api suite
  green; `alembic upgrade head`/`downgrade -1` round-trip clean.
- [ ] **Step 5: Baseline:** `git diff --exit-code openapi.json` — MUST be empty.
- [ ] **Step 6: Gates → commit:**
  `feat(api): logout revocation via session epoch + OAuth state CSRF (phase-6 task-05)`

## Verify

```bash
cd apps/api
set -a && source ../../.env && set +a
uv run pytest tests/test_auth_hardening.py tests/test_auth_endpoints.py \
  tests/test_auth_security.py tests/test_auth_callback_redirect.py -q
uv run pytest -q
git diff --exit-code openapi.json
```

## Acceptance

- A logged-out cookie is dead server-side (replay → 401), proven by test evidence; re-login
  works; logout stays idempotent-200.
- Callback rejects forged, replayed-cross-browser, and expired `state` with the 403 envelope;
  happy path unchanged for a real browser flow.
- OpenAPI baseline unchanged; migration chain 0002→0003→0004 up/down clean.
