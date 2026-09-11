---
id: p8-t13
phase: phase-8-ui-polish
depends_on: []
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 13 — API: `/auth/callback` failures redirect to `/signin?error=…` (C0)

## Goal

Today a sign-in that fails the OAuth-state check or the admin allowlist dead-ends the browser on
the API origin with a JSON 403 envelope — an admin who signs in with the wrong Google account
sees raw JSON. After this task both failure branches `303`-redirect to the admin app's sign-in
page with a machine-readable reason (`?error=state` / `?error=forbidden`) that task 16's sign-in
card turns into a friendly message. WARNING logs are unchanged; the rejected email never appears
in the URL. The OpenAPI baseline and both apps' generated types are regenerated in the same
commit (CONVENTIONS.md §8).

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §5 C0.
- `CONVENTIONS.md` §4 (no `try/except` in routes; errors flow to handlers), §8 (wire-surface
  baselines: `openapi.json` + both codegens in the same commit), §10 (tests never read `.env`).
- `apps/api/app/routes/auth_routes.py` — the whole file; the two `raise ForbiddenError(...)`
  lines in `auth_callback` are the only behaviour that changes.
- `apps/api/tests/test_auth_callback_redirect.py` — the file's `_build_client`/`_ADMIN_APP_URL`
  helpers (reused as-is) and its unlisted-email test (rewritten below).
- `apps/api/tests/test_auth_endpoints.py` lines 165–197 and `apps/api/tests/test_auth_hardening.py`
  lines 371–460 — the four state-failure pins and the one allowlist pin that currently assert
  403 (rewritten below). Both files build `Settings` without `admin_app_url`, so the default
  `http://localhost:3001` applies.
- `apps/api/scripts/export_openapi.py`; `apps/admin/package.json` + `apps/client/package.json`
  `codegen` scripts.

## Files

**Modify**
- `apps/api/app/routes/auth_routes.py`
- `apps/api/tests/test_auth_callback_redirect.py`
- `apps/api/tests/test_auth_endpoints.py`
- `apps/api/tests/test_auth_hardening.py`

**Regenerate (same commit)**
- `apps/api/openapi.json` (`cd apps/api && uv run python scripts/export_openapi.py`)
- `apps/admin/src/types/generated/schema.d.ts` (`pnpm -C apps/admin codegen`)
- `apps/client/src/types/generated/schema.d.ts` (`pnpm -C apps/client codegen`)

## Interfaces

**Produces (wire contract task 16 consumes):**

| Callback outcome | Response |
|---|---|
| `state` fails `verify_state` or ≠ the `advisordesk_oauth_state` cookie | `303`, `Location: {settings.admin_app_url}/signin?error=state`, no `Set-Cookie` |
| email not in `ADMIN_EMAILS` | `303`, `Location: {settings.admin_app_url}/signin?error=forbidden`, no `Set-Cookie`, no row written |
| success | unchanged (`303` to `admin_app_url` or the `/oauth/authorize/continue` detour, session cookie set) |

`reason` values are exactly `state` and `forbidden` — the sign-in card ignores anything else.

**Implementation shape (`auth_routes.py`):**

```python
def _sign_in_error_redirect(settings: Settings, reason: str) -> RedirectResponse:
    """Phase-8 C0: land a failed callback on the admin sign-in page with a machine-readable
    reason (`state` | `forbidden`) instead of a JSON 403 on the API origin. Never carries the
    email or the state value."""
    return RedirectResponse(f"{settings.admin_app_url}/signin?error={reason}", status_code=303)
```

- State branch: keep `logger.warning("OAuth state verification failed")`, then
  `return _sign_in_error_redirect(settings, "state")`.
- Allowlist branch: keep `logger.warning("Login rejected: email=%s reason=allowlist", …)`, then
  `return _sign_in_error_redirect(settings, "forbidden")`.
- `responses=`: remove the `403` arm (the route no longer raises it); update the `303`
  description to `"Session cookie set and redirect to the admin app; or, on a state/allowlist
  failure, redirect to {admin_app_url}/signin?error=state|forbidden with no cookie."`. Keep
  `422` and `502`.
- Docstring: replace the `Raises: ForbiddenError …` section with a `Returns:` paragraph that
  states the three outcomes above (the docstring is embedded verbatim in `openapi.json`, so the
  baseline diff is expected — limited to this operation's `description` and `responses`).
- Drop the now-unused `ForbiddenError` import (ruff F401) and fix the module docstring's first
  paragraph, which says `ForbiddenError` is raised below.

## Steps (TDD)

- [ ] **RED — test-author.** Rewrite the six 403 pins and add one new test. Exact code:

  **`tests/test_auth_callback_redirect.py`** — replace
  `test_callback_unlisted_email_403_has_no_cookie_and_no_redirect` with:

```python
def test_callback_unlisted_email_redirects_303_to_signin_forbidden_with_no_cookie(
    tmp_engine: Engine,
) -> None:
    """Phase-8 C0: an allowlist failure lands on the admin sign-in page, never a JSON 403."""
    client, oauth_client = _build_client(tmp_engine)
    code = "redirect-unlisted-code"
    oauth_client.identities[code] = {
        "email": "outsider@example.com",
        "name": "Outsider",
        "avatar_url": None,
    }
    state = mint_state(client.app.state.settings)  # type: ignore[attr-defined]
    client.cookies.set(_STATE_COOKIE_NAME, state)

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": state}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"{_ADMIN_APP_URL}/signin?error=forbidden"
    assert response.headers.get("set-cookie") is None


def test_callback_failure_redirect_never_carries_the_email(tmp_engine: Engine) -> None:
    """The rejected address must not leak into the URL (it is logged at WARNING only)."""
    client, oauth_client = _build_client(tmp_engine)
    code = "redirect-unlisted-code-2"
    oauth_client.identities[code] = {
        "email": "outsider@example.com",
        "name": "Outsider",
        "avatar_url": None,
    }
    state = mint_state(client.app.state.settings)  # type: ignore[attr-defined]
    client.cookies.set(_STATE_COOKIE_NAME, state)

    response = client.get(
        _CALLBACK_PATH, params={"code": code, "state": state}, follow_redirects=False
    )

    assert "outsider" not in response.headers["location"]
    assert "example.com" not in response.headers["location"]
```

  **`tests/test_auth_endpoints.py`** — rename
  `test_callback_unlisted_email_rejected_with_403_and_no_row_created` →
  `test_callback_unlisted_email_redirects_to_signin_forbidden_and_no_row_created` and replace
  its assertions (keep the setup lines above `response = …` unchanged):

```python
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3001/signin?error=forbidden"
    assert response.headers.get("set-cookie") is None
    assert _fetch_user_by_email(tmp_engine, "outsider@example.com") is None
```

  Update the docstring to `"""PRD §5.1/§9 + phase-8 C0: an email outside `ADMIN_EMAILS` is
  rejected before any row write and lands on the admin sign-in page with `?error=forbidden`."""`.

  **`tests/test_auth_hardening.py`** — in each of the four callback tests
  (`test_callback_rejects_forged_unsigned_state_with_403`,
  `test_callback_rejects_valid_state_with_no_state_cookie_with_403`,
  `test_callback_rejects_valid_state_with_mismatched_state_cookie_with_403`,
  `test_callback_rejects_expired_state_with_403`) rename the `_with_403` suffix to
  `_with_signin_redirect`, and replace every `assert response.status_code == 403` plus any
  following `body = response.json()` / `assert set(body…)` lines with exactly:

```python
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3001/signin?error=state"
    assert response.headers.get("set-cookie") is None
```

  Update each docstring's "-> 403"/"— 403" wording to "-> 303 to `/signin?error=state`". The
  "unregistered code" trick in those tests still proves the state check runs before
  `exchange_code` (a `KeyError` would surface as a 500, not the 303).

- [ ] **Run RED:** `cd apps/api && uv run pytest tests/test_auth_callback_redirect.py
  tests/test_auth_endpoints.py tests/test_auth_hardening.py -q` → the 7 rewritten/new tests
  FAIL (403 ≠ 303); every other test in those files passes.

- [ ] **GREEN — implementer:** implement per Interfaces. Then regenerate the baselines:
  `cd apps/api && uv run python scripts/export_openapi.py`, `pnpm -C apps/admin codegen`,
  `pnpm -C apps/client codegen`. Confirm `git diff --stat` touches exactly
  `auth_routes.py`, the three test files, `openapi.json`, and the two `schema.d.ts` files; the
  `openapi.json` diff is confined to the `auth_callback` operation (`description` + removal of
  the `403` response). If either `schema.d.ts` shows no diff, that is fine (the 403 arm has no
  schema of its own) — still run codegen so the commit provably did.

- [ ] **Run GREEN:** the three files above; then the full API suite `uv run pytest -q`.

- [ ] **Gates:** `pnpm gates:api` (ruff, ruff format, mypy, lint-imports, pytest) → clean;
  `pnpm -C apps/admin type-check && pnpm -C apps/client type-check` → clean (generated types
  still compile). No screenshots (API only).

- [ ] **Commit:**
  `git add apps/api/app/routes/auth_routes.py apps/api/tests/test_auth_callback_redirect.py apps/api/tests/test_auth_endpoints.py apps/api/tests/test_auth_hardening.py apps/api/openapi.json apps/admin/src/types/generated/schema.d.ts apps/client/src/types/generated/schema.d.ts`
  `git commit -m "feat(api): auth callback failures redirect to /signin?error=state|forbidden (p8 t13)"`

## Verify

```bash
cd apps/api && uv run pytest tests/test_auth_callback_redirect.py tests/test_auth_endpoints.py tests/test_auth_hardening.py -q
pnpm gates:api
git diff --exit-code -- apps/api/openapi.json  # must FAIL before commit (baseline moved), pass after
```

## Acceptance

- Both failure branches answer `303` with the documented `Location` and no `Set-Cookie`; the
  email and the state value never appear in the URL; success path byte-for-byte unchanged.
- `openapi.json` and both `schema.d.ts` regenerated in the same commit; no 403 arm remains on
  `auth_callback`; `ForbiddenError` no longer imported by `auth_routes.py`.
- Full API gate set green.
