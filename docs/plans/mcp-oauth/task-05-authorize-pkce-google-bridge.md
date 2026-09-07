---
id: mcp-oauth-t05
phase: mcp-oauth
depends_on: [mcp-oauth-t04]
status: planned
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 05 — `/authorize`: request validation + PKCE + Google bridge + code issuance ★

## Goal

`GET /api/v1/oauth/authorize` validates an OAuth 2.1 request against the registered client,
parks it in a signed cookie, bridges to the existing Google login when there is no admin
session, and — once an allowlisted admin is present — issues a single-use authorization code
and redirects back to the client. **No consent screen yet** (task 06 inserts it into
`/authorize/continue`); this task's `continue` goes straight to the code so the core flow is
provable in task 07.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"End-to-end flow" steps 5–6, §"Google bridge + consent",
  §"Security / threat model" (PKCE, exact redirect, open-redirect prevention, code TTL).
- `docs/plans/mcp-oauth/00-INDEX.md` Global Constraints → **PKCE**, **Redirect URIs**, **Scope**,
  **Token formats**, **OAuth error shape** (the 302 variant), **Rate limiting**.
- `CONVENTIONS.md` §2, §3, §5.
- `apps/api/app/auth/state.py` (whole file — the signed-cookie pattern you copy for the pending
  authorization), `apps/api/app/auth/cookies.py` (`issue_cookie` flags: httponly/samesite/secure).
- `apps/api/app/auth/deps.py` (`require_admin` — you split it into `resolve_admin` + raise).
- `apps/api/app/routes/auth_routes.py` (`auth_login`, `auth_callback` — the one line you change
  is the success redirect target; docstrings are byte-embedded in `openapi.json`, so put the
  explanation in a code comment, not the docstring).
- `apps/api/app/services/errors.py`, `apps/api/app/routes/errors.py` (t04's `OAuthError` +
  handler — you add the redirect variant).
- `apps/api/app/services/oauth_clients.py` (`get_client`), `apps/api/app/services/token_hashing.py`,
  `apps/api/app/models/oauth.py` (t01/t04).
- `apps/api/app/mcp/server.py` — only `_require_admin_with_challenge` (t03) which you simplify.
- `apps/api/app/routes/oauth_routes.py` (t04 — you add three routes).
- `apps/api/tests/auth_helpers.py` (`login_as`, `FakeGoogleOAuthClient`), `apps/api/tests/test_auth_routes.py`
  (how the callback is driven with the fake Google client + state cookie).

## Files

**Create**
- `apps/api/app/services/pkce.py` — pure leaf (stdlib only).
- `apps/api/app/auth/oauth_request.py` — pending-authorization cookie (signed, itsdangerous).
- `apps/api/app/auth/oauth_authorize.py` — request validation against the client registry.
- `apps/api/app/services/oauth_codes.py` — code issuance (t07 adds consumption).
- `apps/api/tests/test_pkce.py` (unit), `apps/api/tests/test_oauth_authorize.py` (DB),
  `apps/api/tests/oauth_helpers.py` (shared non-test helper module, like `auth_helpers.py`).

**Modify**
- `apps/api/app/services/errors.py` — `OAuthRedirectError`.
- `apps/api/app/routes/errors.py` — `_oauth_redirect_error_handler`, registered.
- `apps/api/app/auth/deps.py` — `resolve_admin`; `require_admin` delegates.
- `apps/api/app/mcp/server.py` — `_require_admin_with_challenge` now calls `resolve_admin` and
  raises `_auth_required(request)` on `None` (drops the t03 `try/except`).
- `apps/api/app/routes/auth_routes.py` — `auth_callback` success redirect.
- `apps/api/app/routes/oauth_routes.py` — `oauth_authorize`, `oauth_authorize_continue`.
- `apps/api/openapi.json` + both `schema.d.ts` — regenerated.

## Interfaces

**Consumes:** `OAuthError` (t04), `get_client` (t04), `RateLimiter.check_oauth_request` (t04),
`generate_token`/`hash_token` (t01), `OAuthAuthorizationCode` (t01), `Settings.mcp_resource_url`,
`Settings.oauth_auth_code_ttl_seconds`, `Settings.session_secret`, `Settings.is_dev`,
`Settings.admin_email_set`, `Settings.admin_app_url` (existing/t01); `AdminPrincipal`,
`STATE_COOKIE_NAME` (existing).

**Produces exactly:**

```python
# app/services/pkce.py  (RFC 7636)
_UNRESERVED = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
def is_valid_code_challenge(value: str) -> bool: ...   # bool(_UNRESERVED.fullmatch(value))
def is_valid_code_verifier(value: str) -> bool: ...    # same charset/length rule
def verify_s256(code_verifier: str, code_challenge: str) -> bool:
    # expected = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    # return hmac.compare_digest(expected, code_challenge)

# app/auth/oauth_request.py
AUTHORIZE_COOKIE_NAME = "advisordesk_oauth_authz"
AUTHORIZE_MAX_AGE_SECONDS = 600
_SALT = "advisordesk.auth.oauth-authorize"
@dataclass(frozen=True)
class PendingAuthorization:
    client_id: str
    redirect_uri: str
    code_challenge: str
    resource: str
    scope: str
    state: str | None
    nonce: str                     # secrets.token_urlsafe(16); task 06 binds the consent form to it
def mint_pending_authorization(pending: PendingAuthorization, settings: Settings) -> str: ...
    # URLSafeTimedSerializer(settings.session_secret, salt=_SALT).dumps(dataclasses.asdict(pending))
def read_pending_authorization(value: str | None, settings: Settings) -> PendingAuthorization | None: ...
    # None on missing/BadSignature/SignatureExpired(max_age=AUTHORIZE_MAX_AGE_SECONDS)/shape mismatch
def set_pending_cookie(response: Response, value: str, settings: Settings) -> None: ...
    # response.set_cookie(AUTHORIZE_COOKIE_NAME, value, max_age=AUTHORIZE_MAX_AGE_SECONDS, httponly=True,
    #                     samesite="lax", secure=not settings.is_dev, path="/api/v1")
def clear_pending_cookie(response: Response) -> None: ...
    # response.delete_cookie(AUTHORIZE_COOKIE_NAME, path="/api/v1", httponly=True, samesite="lax")

# app/auth/oauth_authorize.py
def validate_authorize_request(
    session: Session, *, client_id: str | None, redirect_uri: str | None, response_type: str | None,
    code_challenge: str | None, code_challenge_method: str | None, scope: str | None,
    resource: str | None, state: str | None, settings: Settings,
) -> PendingAuthorization:
    # 1. client_id None or get_client(...) is None            -> OAuthError("invalid_client", "Unknown client.", status_code=400)
    # 2. redirect_uri None or not in client.redirect_uris      -> OAuthError("invalid_redirect_uri", "redirect_uri is not registered for this client.")
    #    (steps 1-2 NEVER redirect — RFC 6749 §4.1.2.1)
    # 3. response_type != "code"                                -> OAuthRedirectError("unsupported_response_type", "Only response_type=code is supported.", redirect_uri, state)
    # 4. code_challenge None or not is_valid_code_challenge     -> OAuthRedirectError("invalid_request", "code_challenge is required (PKCE S256).", …)
    # 5. code_challenge_method != "S256" (None or "plain")      -> OAuthRedirectError("invalid_request", "code_challenge_method must be S256.", …)
    # 6. scope not in (None, "", "mcp")                          -> OAuthRedirectError("invalid_scope", "Only scope=mcp is supported.", …)
    # 7. resource not in (None, "", settings.mcp_resource_url)   -> OAuthRedirectError("invalid_target", "resource must be the MCP endpoint of this server.", …)
    # -> PendingAuthorization(client_id, redirect_uri, code_challenge, resource=settings.mcp_resource_url, scope="mcp", state, nonce=secrets.token_urlsafe(16))

# app/services/errors.py
class OAuthRedirectError(AppError):
    """Authorize-endpoint error that is SAFE to redirect: the redirect_uri was already verified against the client."""
    code = "oauth_redirect_error"
    def __init__(self, error: str, description: str, redirect_uri: str, state: str | None) -> None:
        super().__init__(description)
        self.error = error; self.description = description; self.redirect_uri = redirect_uri; self.state = state

# app/routes/errors.py
def _oauth_redirect_error_handler(_: Request, exc: Exception) -> RedirectResponse:
    # params = {"error": exc.error, "error_description": exc.description}; if exc.state is not None: params["state"] = exc.state
    # sep = "&" if "?" in exc.redirect_uri else "?"
    # RedirectResponse(f"{exc.redirect_uri}{sep}{urlencode(params)}", status_code=302, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
# register: app.add_exception_handler(OAuthRedirectError, _oauth_redirect_error_handler)

# app/auth/deps.py
def resolve_admin(request: Request) -> AdminPrincipal | None:
    """Everything require_admin does, returning None instead of raising (same WARNING logs, same reasons)."""
def require_admin(request: Request) -> AdminPrincipal:
    principal = resolve_admin(request)
    if principal is None:
        raise AuthRequiredError("Sign in required.")
    return principal

# app/services/oauth_codes.py
def issue_authorization_code(
    session: Session, *, client_id: str, user_id: uuid.UUID, redirect_uri: str, code_challenge: str,
    resource: str, scope: str, now: datetime, ttl_seconds: int,
) -> str:
    # raw, hashed = generate_token("adkac_"); insert OAuthAuthorizationCode(code_hash=hashed, …, expires_at=now + timedelta(seconds=ttl_seconds)); flush; return raw
```

```python
# app/routes/oauth_routes.py — additions
GET /oauth/authorize            operation_id="oauth_authorize"           response_class=RedirectResponse (303)
# query params (all `str | None = None`): response_type, client_id, redirect_uri, code_challenge,
#   code_challenge_method, scope, resource, state
# limiter.check_oauth_request(ip) -> pending = validate_authorize_request(...)
# -> response = RedirectResponse("/api/v1/oauth/authorize/continue", status_code=303)
# -> set_pending_cookie(response, mint_pending_authorization(pending, settings), settings) -> return
GET /oauth/authorize/continue   operation_id="oauth_authorize_continue"  -> Response
# limiter.check_oauth_request(ip)
# pending = read_pending_authorization(request.cookies.get(AUTHORIZE_COOKIE_NAME), settings)
#   None -> raise OAuthError("invalid_request", "No pending authorization request.")
# principal = resolve_admin(request)
#   None -> return RedirectResponse("/api/v1/auth/login", status_code=307)      # Google bridge
# if principal.email.lower() not in settings.admin_email_set:
#   raise OAuthRedirectError("access_denied", "This account is not permitted to authorize MCP access.", pending.redirect_uri, pending.state)
# return _issue_code_and_redirect(session, pending, principal, settings)      # module-level helper, task 06 reuses it
```

```python
def _issue_code_and_redirect(session: Session, pending: PendingAuthorization, principal: AdminPrincipal, settings: Settings) -> RedirectResponse:
    now = datetime.now(UTC)
    code = issue_authorization_code(session, client_id=pending.client_id, user_id=principal.user_id, redirect_uri=pending.redirect_uri,
                                    code_challenge=pending.code_challenge, resource=pending.resource, scope=pending.scope,
                                    now=now, ttl_seconds=settings.oauth_auth_code_ttl_seconds)
    params = {"code": code}; if pending.state is not None: params["state"] = pending.state
    sep = "&" if "?" in pending.redirect_uri else "?"
    response = RedirectResponse(f"{pending.redirect_uri}{sep}{urlencode(params)}", status_code=302,
                                headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
    clear_pending_cookie(response)
    return response
```

`auth_callback` change (one line + comment): after `issue_cookie(...)`, if
`request.cookies.get(AUTHORIZE_COOKIE_NAME) is not None` the redirect target is
`"/api/v1/oauth/authorize/continue"` (303) instead of `settings.admin_app_url`. The state-cookie
delete stays as is. Docstring unchanged.

`resolve_admin` keeps the existing `RuntimeError` when `request.app.state.session_factory` is
`None` (a misconfigured app is a bug, not an auth outcome); only the authentication failures
(no cookie, bad cookie, unknown/inactive user, stale epoch) become `None`.

## Steps (TDD)

- [ ] **RED — test-author:**
  - `tests/test_pkce.py`:
    - `test_rfc7636_appendix_b_vector` — verifier `dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk`
      ↔ challenge `E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM` → `verify_s256` True.
    - `test_wrong_verifier_false`; `test_challenge_charset_and_length` (42 chars False, 43 True,
      128 True, 129 False, `+` False); `test_verifier_charset_and_length` likewise.
  - `tests/test_oauth_authorize.py` (DB; `_build_app()` with `oauth_issuer_url="https://api.example"`,
    `admin_emails="admin@example.com"`, `FakeGoogleOAuthClient` as `test_auth_routes` does;
    helper `_register(client) -> client_id` posting to `/api/v1/oauth/register` with
    `redirect_uris=["https://claude.ai/api/mcp/auth_callback"]`; helper `_authorize_params(client_id, **overrides)`
    returning the full valid query dict with `code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`,
    `state="xyz"`, `resource="https://api.example/api/v1/mcp"`; **`follow_redirects=False` everywhere**):
    - `test_unknown_client_400_json_no_redirect` — `client_id=adkc_nope` → 400 `invalid_client`, JSON, no `Location`.
    - `test_unregistered_redirect_400_json_no_redirect` — `redirect_uri=https://evil.example/cb` → 400 `invalid_redirect_uri`.
    - `test_missing_challenge_redirects_invalid_request` — 302; `Location` starts with the registered
      redirect, query has `error=invalid_request`, `state=xyz`.
    - `test_plain_method_redirects_invalid_request`; `test_response_type_token_redirects_unsupported`;
      `test_bad_scope_redirects_invalid_scope`; `test_bad_resource_redirects_invalid_target`;
      `test_error_redirect_has_no_store` (headers on the 302).
    - `test_valid_request_303_sets_httponly_cookie` — 303 to `/api/v1/oauth/authorize/continue`;
      `Set-Cookie` contains `advisordesk_oauth_authz=`, `HttpOnly`, `Path=/api/v1`, `SameSite=lax`.
    - `test_absent_scope_and_resource_default` — omit both → 303 (defaults applied; assert via the
      later code row: `scope == "mcp"`, `resource == "https://api.example/api/v1/mcp"`).
    - `test_continue_without_cookie_400` — 400 `invalid_request` "No pending authorization request."
    - `test_continue_without_session_307_login` — cookie present, no admin cookie → 307 `/api/v1/auth/login`.
    - `test_full_bridge_issues_code` — uses the shared helper
      `tests/oauth_helpers.py::complete_authorization(client, *, email="admin@example.com") -> AuthorizationResult`
      (a non-test module next to `auth_helpers.py`; tasks 06/07/08/10 import it, and **task 06 is
      the one task allowed to extend it** to click Approve). `AuthorizationResult` is a frozen
      dataclass `{code, client_id, redirect_uri, code_verifier, state}`; the helper: registers a
      client (`redirect_uris=["https://claude.ai/api/mcp/auth_callback"]`) → GET authorize with
      the RFC 7636 vector (`code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk`,
      `state="xyz"`) → asserts 303 (cookie kept by `TestClient`) → `login_as(client, email)` →
      GET continue → asserts 302 → parses `Location`. The test then asserts `code.startswith("adkac_")`,
      `state == "xyz"`, and in `db_session`: one `OAuthAuthorizationCode` row, `code_hash == hash_token(code)`,
      `consumed_at is None`, `expires_at - created_at` within 55–65 s, `client_id`, `redirect_uri`,
      `resource`, `scope == "mcp"` match; the 302 `Set-Cookie` deletes `advisordesk_oauth_authz`.
    - `test_continue_via_google_callback_redirects_to_continue` — authorize → then drive the real
      `/api/v1/auth/login` → `/api/v1/auth/callback` with the fake Google client + state cookie
      (as `test_auth_routes` does) → callback responds 303 to `/api/v1/oauth/authorize/continue`.
    - `test_callback_without_pending_cookie_still_goes_to_admin_app` — plain login flow → 303 `admin_app_url`.
    - `test_non_allowlisted_admin_access_denied` — after `login_as`, set `app.state.settings.admin_emails`
      to another address (mirror `test_mcp_bearer_auth`'s mutation) → continue → 302 `error=access_denied&state=xyz`.
    - `test_tampered_cookie_is_ignored` — set `advisordesk_oauth_authz=garbage` → continue → 400.
    - `test_authorize_rate_limited` — `oauth_rate_limit_per_min=1` → second GET → 429.
    - `test_mcp_cookie_path_still_401_with_challenge` — regression for the `resolve_admin` refactor:
      POST `/api/v1/mcp` with a stale cookie → 401 + `WWW-Authenticate` (t03 behaviour preserved).
    - `test_openapi_has_authorize_operations` — both `operation_id`s present.
  - Prove RED.
- [ ] **GREEN — implementer:** `pkce` → `oauth_request` → `OAuthRedirectError` + handler →
  `resolve_admin` split (+ `server.py` simplification) → `oauth_authorize` → `oauth_codes` →
  routes → `auth_callback` line → regenerate baseline + codegens.
- [ ] Run new tests + `tests/test_auth_routes.py tests/test_mcp_www_authenticate.py tests/test_mcp_bearer_auth.py tests/test_oauth_register.py` → PASS.
- [ ] Full backend gates.
- [ ] Commit: `feat(api): /oauth/authorize with PKCE, Google bridge, and code issuance (mcp-oauth t05)`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_pkce.py tests/test_oauth_authorize.py tests/test_auth_routes.py tests/test_mcp_www_authenticate.py
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json
```

## Acceptance

- Errors for unknown client / unregistered redirect never redirect; all other validation errors
  redirect with `state` preserved and no-store headers.
- The pending cookie is signed, expires after 600 s, `HttpOnly`, `Path=/api/v1`, `Secure` outside dev.
- `require_admin` behaviour is byte-identical from the outside (existing auth tests untouched).
- Reviewer (Opus) confirms: no raw code is logged; the code TTL comes from settings; the
  `auth_callback` docstring (and therefore `openapi.json`'s description) is unchanged; the
  `Location` builder handles a `redirect_uri` that already contains `?`.
