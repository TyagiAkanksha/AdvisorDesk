---
id: mcp-oauth-t07
phase: mcp-oauth
depends_on: [mcp-oauth-t05]
status: built
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 07 — `POST /oauth/token`: authorization-code grant + refresh rotation + reuse detection ★

## Goal

Exchange a code (with PKCE verifier, exact redirect, audience) for an `adk_` access token + an
`adkr_` refresh token; rotate refresh tokens on every use; detect reuse of a rotated token and
kill the whole family. After this task a working **Connect** exists: the task's tests drive
register → authorize → login → code → token → MCP `initialize`.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"End-to-end flow" steps 7–8, §"Token & data model",
  §"Security / threat model" (rotation, reuse, audience), §"Decisions pinned" (lifetimes).
- `docs/plans/mcp-oauth/00-INDEX.md` Global Constraints → **Lifetimes**, **PKCE**, **Token
  formats**, **Audience rule**, **OAuth error shape**, **Rate limiting**.
- `CONVENTIONS.md` §3, §5, §6.
- `apps/api/app/services/oauth_codes.py` (t05 — you add `consume_authorization_code`).
- `apps/api/app/services/pkce.py` (`verify_s256`, `is_valid_code_verifier`), `apps/api/app/services/token_hashing.py`.
- `apps/api/app/models/oauth.py`, `apps/api/app/models/api_tokens.py` (t01).
- `apps/api/app/auth/tokens.py` (`resolve_bearer_token` — what the access-token row must satisfy:
  allowlist, `session_epoch`, `expires_at`, audience).
- `apps/api/app/services/users.py` (`get_user_by_id` — for `session_epoch`).
- `apps/api/app/routes/oauth_routes.py` (t04/t05), `apps/api/app/models/schemas/oauth.py` (t04).
- `apps/api/tests/oauth_helpers.py` (`complete_authorization`), `apps/api/tests/test_mcp_bearer_auth.py`
  (`_INITIALIZE_BODY`, `_MCP_HEADERS`).
- `apps/api/pyproject.toml` (deps list — `python-multipart` is missing; FastAPI `Form` needs it).

## Files

**Create**
- `apps/api/app/services/oauth_tokens.py`
- `apps/api/tests/test_oauth_token.py` (DB).

**Modify**
- `apps/api/pyproject.toml` + `uv.lock` — `uv add "python-multipart>=0.0.20"`.
- `apps/api/app/services/oauth_codes.py` — `consume_authorization_code`.
- `apps/api/app/models/schemas/oauth.py` — `TokenResponse`.
- `apps/api/app/routes/oauth_routes.py` — `oauth_token`.
- `apps/api/openapi.json` + both `schema.d.ts` — regenerated.

## Interfaces

**Consumes:** `OAuthError` (t04), `get_client` (t04), `check_oauth_request` (t04), `verify_s256`,
`is_valid_code_verifier` (t05), `generate_token`, `hash_token` (t01), `OAuthAuthorizationCode`,
`OAuthRefreshToken`, `ApiToken` (t01), `get_user_by_id` (existing), `Settings.oauth_access_token_ttl_minutes`,
`Settings.oauth_refresh_token_ttl_days`, `Settings.mcp_resource_url` (t01).

**Produces exactly:**

```python
# app/services/oauth_codes.py — addition
def consume_authorization_code(
    session: Session, *, raw_code: str, client_id: str, redirect_uri: str, code_verifier: str, resource: str, now: datetime,
) -> OAuthAuthorizationCode:
    # row = select by code_hash == hash_token(raw_code) FOR UPDATE (with_for_update())
    # None                                    -> OAuthError("invalid_grant", "Unknown or expired authorization code.")
    # row.consumed_at is not None (REPLAY)    -> revoke_family(session, row.id, now)   # kills every token minted from this code
    #                                            log WARNING "oauth code replay detected client_id=%s reason=code-replay"
    #                                            -> OAuthError("invalid_grant", "Authorization code already used.")
    # row.expires_at <= now                   -> OAuthError("invalid_grant", "Unknown or expired authorization code.")
    # row.client_id != client_id              -> same invalid_grant text
    # row.redirect_uri != redirect_uri        -> OAuthError("invalid_grant", "redirect_uri does not match the authorization request.")
    # not is_valid_code_verifier(code_verifier) or not verify_s256(code_verifier, row.code_challenge)
    #                                         -> OAuthError("invalid_grant", "PKCE verification failed.")
    # row.resource != resource                -> OAuthError("invalid_target", "resource does not match the authorization request.")
    # row.consumed_at = now; flush; return row
    # (revoke_family is imported from app.services.oauth_tokens — codes -> tokens is a one-way import; tokens must NOT import codes at module level.
    #  To avoid a cycle, `redeem_authorization_code` in oauth_tokens imports consume_authorization_code INSIDE the function body with a comment.)

# app/services/oauth_tokens.py
@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int          # seconds
    scope: str

def issue_token_pair(
    session: Session, *, client_id: str, user_id: uuid.UUID, resource: str, scope: str, family_id: uuid.UUID,
    refresh_expires_at: datetime, now: datetime, settings: Settings, rotated_from_id: uuid.UUID | None = None,
) -> IssuedTokens:
    # user = get_user_by_id(session, user_id)  (None -> OAuthError("invalid_grant", "User no longer exists."))
    # access_raw, access_hash = generate_token("adk_")
    # access = ApiToken(user_id=user_id, token_hash=access_hash, name=f"oauth:{client_id}", session_epoch=user.session_epoch,
    #                   expires_at=now + timedelta(minutes=settings.oauth_access_token_ttl_minutes), client_id=client_id, resource=resource)
    # refresh_raw, refresh_hash = generate_token("adkr_")
    # refresh = OAuthRefreshToken(token_hash=refresh_hash, client_id=client_id, user_id=user_id, access_token_id=access.id,
    #                             family_id=family_id, rotated_from_id=rotated_from_id, resource=resource, scope=scope, expires_at=refresh_expires_at)
    # session.add_all([access, refresh]); flush
    # return IssuedTokens(access_raw, refresh_raw, settings.oauth_access_token_ttl_minutes * 60, scope)

def redeem_authorization_code(
    session: Session, *, raw_code: str, client_id: str, redirect_uri: str, code_verifier: str, resource: str, now: datetime, settings: Settings,
) -> IssuedTokens:
    # code = consume_authorization_code(...)           # local import, see above
    # return issue_token_pair(session, client_id=client_id, user_id=code.user_id, resource=code.resource, scope=code.scope,
    #                         family_id=code.id, refresh_expires_at=now + timedelta(days=settings.oauth_refresh_token_ttl_days), now=now, settings=settings)

def rotate_refresh_token(
    session: Session, *, raw_refresh_token: str, client_id: str, resource: str | None, scope: str | None, now: datetime, settings: Settings,
) -> IssuedTokens:
    # old = select OAuthRefreshToken by token_hash FOR UPDATE
    # None                                  -> OAuthError("invalid_grant", "Unknown or expired refresh token.")
    # old.revoked_at is not None (REUSE)    -> revoke_family(session, old.family_id, now); log WARNING "refresh token reuse detected client_id=%s reason=refresh-reuse"
    #                                          -> OAuthError("invalid_grant", "Refresh token has been revoked.")
    # old.expires_at <= now                 -> OAuthError("invalid_grant", "Unknown or expired refresh token.")
    # old.client_id != client_id            -> same text
    # resource not in (None, "", old.resource) -> OAuthError("invalid_target", "resource does not match the original grant.")
    # scope not in (None, "", old.scope)       -> OAuthError("invalid_scope", "Requested scope exceeds the original grant.")
    # old.revoked_at = now
    # if old.access_token_id is not None: delete that ApiToken row (session.execute(delete(ApiToken).where(ApiToken.id == old.access_token_id)))
    # return issue_token_pair(..., family_id=old.family_id, refresh_expires_at=old.expires_at, rotated_from_id=old.id, ...)   # inherits the remaining window

def revoke_family(session: Session, family_id: uuid.UUID, now: datetime) -> int:
    # rows = select OAuthRefreshToken where family_id == family_id and revoked_at is None
    # for each: revoked_at = now; delete its access token row if access_token_id is not None
    # flush; return len(rows)
```

```python
# app/models/schemas/oauth.py — addition
class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str
```

```python
# app/routes/oauth_routes.py — addition
POST /oauth/token   operation_id="oauth_token"   response_model=TokenResponse
# form fields (all `Annotated[str | None, Form()] = None`): grant_type, code, redirect_uri, code_verifier,
#   client_id, resource, refresh_token, scope
# limiter.check_oauth_request(ip)
# grant_type None                        -> OAuthError("invalid_request", "grant_type is required.")
# client_id None or get_client is None   -> OAuthError("invalid_client", "Unknown client.", status_code=401)
# "authorization_code": code/redirect_uri/code_verifier None -> OAuthError("invalid_request", "<field> is required.")
#     resource default: resource or settings.mcp_resource_url
#     tokens = redeem_authorization_code(...)
# "refresh_token": refresh_token None -> invalid_request; tokens = rotate_refresh_token(...)
# anything else                          -> OAuthError("unsupported_grant_type", "Only authorization_code and refresh_token are supported.")
# return JSONResponse(TokenResponse(...).model_dump(), headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
#   (JSONResponse so the RFC 6749 §5.1 no-store headers are set; keep response_model for the schema)
```

## Steps (TDD)

- [ ] **RED — test-author** writes `tests/test_oauth_token.py` (DB; `_build_app()` as in
  `test_oauth_authorize`; helper `_exchange(client, result: AuthorizationResult, **overrides) -> Response`
  posting form data `grant_type=authorization_code, code, redirect_uri, code_verifier, client_id, resource`;
  helper `_mcp_initialize(client, token) -> Response`):
  - `test_code_grant_happy_path_and_mcp_round_trip` — 200; body keys exactly
    `{access_token, token_type, expires_in, refresh_token, scope}`; `access_token.startswith("adk_")`,
    `refresh_token.startswith("adkr_")`, `expires_in == 3600`, `scope == "mcp"`, `token_type == "Bearer"`;
    headers no-store/no-cache; then MCP `initialize` with the access token → 200. DB: `ApiToken`
    row with `client_id`, `resource == "https://api.example/api/v1/mcp"`, `name == f"oauth:{client_id}"`,
    `expires_at - created_at ≈ 60 min`; `OAuthRefreshToken` row with `family_id == code.id`,
    `access_token_id == access.id`, `expires_at - created_at ≈ 30 d`; code row `consumed_at` set.
  - `test_wrong_verifier_invalid_grant` — 400 `invalid_grant` "PKCE verification failed."; the
    code row is NOT consumed (`consumed_at is None`). Decision: a failed PKCE check leaves the
    code intact — the 60 s TTL and the 30-per-minute rate limit bound retries, and the verifier
    space (≥43 unreserved chars) is not brute-forceable in that window. Only a *successful*
    exchange consumes; a second successful-looking exchange is the replay case below.
  - `test_redirect_mismatch_invalid_grant`; `test_wrong_client_invalid_grant` (register a second
    client, use its id → 400 `invalid_grant`); `test_unknown_client_401_invalid_client`;
    `test_missing_grant_type_invalid_request`; `test_unsupported_grant_type`;
    `test_missing_code_invalid_request`.
  - `test_expired_code_invalid_grant` — backdate the code row's `expires_at` in `db_session` → 400.
  - `test_code_replay_kills_issued_tokens` — exchange once (200), exchange again → 400
    `"Authorization code already used."`; the first access token now fails MCP (401) and the
    refresh token row has `revoked_at` set.
  - `test_resource_mismatch_invalid_target` — `resource=https://other.example/api/v1/mcp` → 400 `invalid_target`.
  - `test_absent_resource_defaults_to_canonical` — omit `resource` → 200.
  - `test_refresh_happy_path_rotates` — exchange → refresh (`grant_type=refresh_token, refresh_token, client_id`)
    → 200 with a NEW access + NEW refresh; old refresh row `revoked_at` set, new row `rotated_from_id == old.id`,
    `new.expires_at == old.expires_at` (inherits), `new.family_id == old.family_id`; old access token
    now 401 at MCP; new access token 200 at MCP.
  - `test_refresh_reuse_revokes_family` — after rotation, present the OLD refresh again → 400
    `"Refresh token has been revoked."`; the NEW refresh is now revoked too; the NEW access token 401.
  - `test_refresh_expired_invalid_grant` — backdate `expires_at` → 400.
  - `test_refresh_wrong_client_invalid_grant`; `test_refresh_resource_mismatch_invalid_target`;
    `test_refresh_scope_escalation_invalid_scope` (`scope=admin`).
  - `test_refresh_unknown_token_invalid_grant`.
  - `test_token_rate_limited` — `oauth_rate_limit_per_min=1` → second POST → 429.
  - `test_openapi_has_token_operation`.
  - Prove RED (the form routes will 500/404 until `python-multipart` + route exist — record it).
- [ ] **GREEN — implementer:** `uv add "python-multipart>=0.0.20"` → `consume_authorization_code`
  → `oauth_tokens` → `TokenResponse` → route → regenerate baseline + codegens.
- [ ] Run `tests/test_oauth_token.py tests/test_oauth_authorize.py tests/test_mcp_www_authenticate.py tests/test_mcp_bearer_auth.py` → PASS.
- [ ] Full backend gates (`lint-imports` must stay green — services↔services imports are fine;
  the local import in `redeem_authorization_code` exists only to break the codes↔tokens cycle).
- [ ] Commit: `feat(api): /oauth/token code grant, refresh rotation, reuse detection (mcp-oauth t07)`
  including `pyproject.toml`, `uv.lock`, `openapi.json`, both `schema.d.ts`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_oauth_token.py tests/test_oauth_authorize.py tests/test_mcp_www_authenticate.py
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json
```

## Acceptance

- A full Connect is proven by test: register → authorize → login → code → token → MCP 200.
- Rotation inherits the window; reuse kills the family; replay of a code kills its tokens.
- All token-endpoint errors are RFC-shaped with no-store headers; `invalid_client` is 401.
- Reviewer (Opus) confirms: `FOR UPDATE` on code/refresh lookups; raw tokens never logged; the
  access `ApiToken` row satisfies every check in `resolve_bearer_token` (epoch copied from the
  user at issue time, so `/auth/logout` still kills OAuth access tokens); no `commit()` in services.
