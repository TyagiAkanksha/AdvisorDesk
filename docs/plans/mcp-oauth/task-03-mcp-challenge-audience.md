---
id: mcp-oauth-t03
phase: mcp-oauth
depends_on: [mcp-oauth-t02]
status: planned
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 03 — MCP 401 `WWW-Authenticate` challenge + audience validation on resolve ★

## Goal

Every unauthenticated response from the MCP endpoint carries the RFC 9728 challenge header so
claude.ai can discover the authorization server, and `resolve_bearer_token` enforces the audience
rule (RFC 8707) and stamps `last_used_at`.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"Conformance target" (resource-server bullets), §"Security /
  threat model" (audience binding), §"End-to-end flow" step 1 and 8.
- `docs/plans/mcp-oauth/00-INDEX.md` Global Constraints → **Audience rule**, **MCP 401**.
- `apps/api/app/services/errors.py` (the `AppError` base — you add an optional `headers`).
- `apps/api/app/routes/errors.py` (`_make_handler`, `_http_exception_handler` — the latter already
  forwards headers; mirror it).
- `apps/api/app/auth/tokens.py` (`resolve_bearer_token` — reason-keyword WARNING logs).
- `apps/api/app/mcp/server.py` lines 230–316 (`_extract_bearer_token`, `_resolve_bearer_principal`)
  and 436–444 (the gate in `_AdminGatedMcpApp.__call__`).
- `apps/api/app/auth/deps.py` (`require_admin`).
- `apps/api/app/auth/oauth_discovery.py` (task 02: `www_authenticate_challenge`).
- `apps/api/tests/test_mcp_bearer_auth.py` (test shape to copy: `_build_app`, `_INITIALIZE_BODY`,
  `_MCP_HEADERS`, 401 envelope assertions).
- `apps/api/tests/auth_helpers.py` (`login_as`).

## Files

**Create**
- `apps/api/tests/test_mcp_www_authenticate.py` (DB-backed via `tmp_engine`).

**Modify**
- `apps/api/app/services/errors.py` — `AppError.__init__(self, message: str, *, headers: Mapping[str, str] | None = None)`; stores `self.headers`.
- `apps/api/app/routes/errors.py` — `_make_handler` passes `headers=getattr(exc, "headers", None)` to `JSONResponse`.
- `apps/api/app/auth/tokens.py` — audience rule + `last_used_at` stamp.
- `apps/api/app/mcp/server.py` — all three 401 paths raise with the challenge header.

## Interfaces

**Consumes:** `www_authenticate_challenge(settings)` (task 02); `ApiToken.client_id`,
`ApiToken.resource`, `ApiToken.last_used_at`; `Settings.mcp_resource_url` (task 01).

**Produces exactly:**

```python
# app/services/errors.py
class AppError(Exception):
    code = "error"
    def __init__(self, message: str, *, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(message)
        self.headers: Mapping[str, str] | None = headers

# app/auth/tokens.py — resolve_bearer_token(session, raw_token, settings) -> AdminPrincipal | None
# New rejection branches, evaluated AFTER the existing expiry check and BEFORE the allowlist check:
#   token.client_id is not None and token.resource != settings.mcp_resource_url  -> WARNING reason=wrong-audience, return None
#   token.client_id is None and token.resource not in (None, settings.mcp_resource_url) -> WARNING reason=wrong-audience, return None
# On success (after the allowlist check passes): token.last_used_at = datetime.now(UTC); session.flush()
# (the CALLER commits — `_resolve_bearer_principal` adds `session.commit()` on the success path.)

# app/mcp/server.py
def _auth_required(request: Request) -> AuthRequiredError:
    """Build the 401 error carrying `WWW-Authenticate` (RFC 9728 §5.1) from the LIVE settings."""
    settings = cast(Settings, request.app.state.settings)
    return AuthRequiredError("Sign in required.", headers={"WWW-Authenticate": www_authenticate_challenge(settings)})
```

- `_extract_bearer_token(request)` raises `_auth_required(request)` on the malformed-header branch.
- `_resolve_bearer_principal(request, raw_token)` raises `_auth_required(request)` when the
  principal is `None`; commits the session when the principal is not `None` (the `last_used_at` stamp).
- Cookie path in `__call__`: replace `principal = await anyio.to_thread.run_sync(require_admin, request)`
  with a call to a new module-level `_require_admin_with_challenge(request) -> AdminPrincipal` that
  calls `resolve_admin(request)` (task 05 introduces `resolve_admin`; **in this task** implement it
  by calling `require_admin` inside a `try/except AuthRequiredError as exc: raise _auth_required(request) from exc`
  — this is `app.mcp`, not a route, so the CONVENTIONS §5 no-try/except rule does not apply; task 05
  swaps the body to `resolve_admin` without touching tests).

## Steps (TDD)

- [ ] **RED — test-author** writes `tests/test_mcp_www_authenticate.py` (copy `_build_settings`
  /`_build_app`/`_INITIALIZE_BODY`/`_MCP_HEADERS` from `test_mcp_bearer_auth.py`; settings add
  `oauth_issuer_url="https://api.example"`; expected header value
  `'Bearer resource_metadata="https://api.example/.well-known/oauth-protected-resource"'`):
  - `test_no_credentials_401_carries_www_authenticate` — POST `/api/v1/mcp` with no header/cookie
    → 401, `error.code == "auth_required"`, exact `WWW-Authenticate`.
  - `test_malformed_bearer_401_carries_www_authenticate` — `Authorization: Bearer` (empty value) → same.
  - `test_unknown_bearer_401_carries_www_authenticate` — `Bearer adk_nope` → same.
  - `test_stale_cookie_401_carries_www_authenticate` — `login_as`, then bump
    `User.session_epoch` directly in `db_session`, call with cookie → 401 + header.
  - `test_oauth_token_wrong_audience_rejected` — insert `OAuthClient` + `ApiToken(client_id=<it>,
    resource="https://other.example/api/v1/mcp", …)` for an allowlisted user → 401 + header.
  - `test_oauth_token_right_audience_accepted` — same but `resource="https://api.example/api/v1/mcp"`
    → 200 `initialize` result.
  - `test_cli_token_null_resource_accepted` — `ApiToken(client_id=None, resource=None)` → 200 (legacy CLI).
  - `test_cli_token_wrong_resource_rejected` — `ApiToken(client_id=None, resource="https://other.example/api/v1/mcp")` → 401.
  - `test_oauth_token_null_resource_rejected` — `ApiToken(client_id=<client>, resource=None)` → 401.
  - `test_successful_resolve_stamps_last_used_at` — after a 200 call, re-read the row in a fresh
    session: `last_used_at` is not `None`.
  - `test_www_authenticate_uses_live_settings` — mutate `app.state.settings.oauth_issuer_url`
    after build (as `test_mcp_bearer_auth` mutates `admin_emails`) → header reflects the new issuer.
  - `test_rest_401_has_no_www_authenticate` — `GET /api/v1/auth/me` without cookie → 401 and
    **no** `WWW-Authenticate` header (the challenge is MCP-only).
  - Prove RED: `uv run pytest -q tests/test_mcp_www_authenticate.py`.
- [ ] **GREEN — implementer:** the four modifications above. Keep `resolve_bearer_token`'s
  "never raises" contract and its existing reason keywords; add `wrong-audience`.
- [ ] Run `tests/test_mcp_www_authenticate.py tests/test_mcp_bearer_auth.py tests/test_mcp_gate_fixes.py tests/test_bearer_*.py tests/test_resolve_bearer_settings_required.py` → PASS.
- [ ] Full backend gates. (`openapi.json` is unaffected — no route/DTO change; verify with the
  export + `git diff --exit-code`.)
- [ ] Commit: `feat(api): MCP WWW-Authenticate challenge + bearer audience check (mcp-oauth t03)`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_mcp_www_authenticate.py tests/test_mcp_bearer_auth.py tests/test_mcp_gate_fixes.py
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json
```

## Acceptance

- All three 401 paths carry the exact header; REST 401s do not.
- Audience rule matches the Global Constraints table exactly (four cases tested).
- `last_used_at` is stamped only on success and committed by the MCP gate, not by the service.
- Reviewer (Opus) confirms no raw token or header value is ever logged, and that pre-existing
  bearer tests remain untouched and green.
