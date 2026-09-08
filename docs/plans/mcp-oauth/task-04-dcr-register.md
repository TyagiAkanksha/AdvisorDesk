---
id: mcp-oauth-t04
phase: mcp-oauth
depends_on: [mcp-oauth-t02]
status: built
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 04 — Dynamic client registration `POST /oauth/register` (RFC 7591) ★

## Goal

Land the OAuth error family + its RFC-shaped handler, the per-IP OAuth rate-limit method, the
client service, and the first `/api/v1/oauth/*` route. After this task claude.ai can register
itself and receive a `client_id`; nothing can authorize yet.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"End-to-end flow" step 4, §"Security / threat model"
  (redirect URIs, rate-limit + DCR cap), §"Error handling".
- `docs/plans/mcp-oauth/00-INDEX.md` Global Constraints → **Redirect URIs**, **Scope**,
  **Token formats**, **OAuth error shape**, **Rate limiting**.
- `CONVENTIONS.md` §3 (services), §5 (routes + error handlers), §6 (DTOs).
- `apps/api/app/services/errors.py` (task 03's `AppError` with `headers`).
- `apps/api/app/routes/errors.py` (`register_error_handlers`, `_make_handler` — you add one more handler).
- `apps/api/app/routes/ratelimit.py` (whole file — add one method following `check_message`'s shape).
- `apps/api/app/routes/deps.py` (`get_session`, `get_settings`, `get_rate_limiter`).
- `apps/api/app/routes/public_routes.py` lines 390–410 (how a route reads `client_ip` + calls the limiter).
- `apps/api/app/models/oauth.py`, `apps/api/app/services/token_hashing.py` (task 01).
- `apps/api/app/models/schemas/common.py` (`ErrorEnvelope`), one existing DTO module e.g.
  `apps/api/app/models/schemas/stats.py` (Pydantic style: `ConfigDict`, `Field`).
- `apps/api/tests/test_ratelimit.py` (the `RateLimiter(settings, clock=…)` fake-clock pattern).
- `apps/api/tests/test_app_factory.py` (`test_registered_error_maps_to_exact_envelope` — the
  throwaway-route pattern for handler tests).

## Files

**Create**
- `apps/api/app/services/oauth_clients.py`
- `apps/api/app/models/schemas/oauth.py`
- `apps/api/app/routes/oauth_routes.py`
- `apps/api/tests/test_oauth_register.py` (DB), `apps/api/tests/test_oauth_errors.py` (DB-less),
  `apps/api/tests/test_ratelimit_oauth.py` (unit).

**Modify**
- `apps/api/app/services/errors.py` — add `OAuthError`.
- `apps/api/app/routes/errors.py` — add `_oauth_error_handler`, register it.
- `apps/api/app/routes/ratelimit.py` — add `check_oauth_request`.
- `apps/api/app/factory.py` — `app.include_router(oauth_router, prefix=_API_PREFIX)` unconditionally.
- `apps/api/openapi.json` + both `schema.d.ts` — regenerated.

## Interfaces

**Consumes:** `AppError(message, *, headers)` (t03); `OAuthClient`, `OAuthConsent`,
`OAuthRefreshToken`, `ApiToken.client_id` (t01); `Settings.oauth_rate_limit_per_min`,
`Settings.oauth_max_clients` (t01); `RateLimitedError`, `RateLimiter._minute_windows`,
`_touch_minute_window` (existing).

**Produces exactly:**

```python
# app/services/errors.py
class OAuthError(AppError):
    """RFC 6749 §5.2-shaped error for /api/v1/oauth/* endpoints (rendered by app.routes.errors)."""
    code = "oauth_error"
    def __init__(self, error: str, description: str, *, status_code: int = 400) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code

# app/routes/errors.py
def _oauth_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # assert isinstance(exc, OAuthError)
    # JSONResponse(status_code=exc.status_code,
    #              content={"error": exc.error, "error_description": exc.description},
    #              headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
# register_error_handlers: app.add_exception_handler(OAuthError, _oauth_error_handler)
# (Starlette resolves handlers by walking type(exc).__mro__, so the OAuthError handler wins over
#  the AppError handler regardless of registration order — add a comment saying so.)

# app/routes/ratelimit.py
def check_oauth_request(self, ip: str) -> None:
    """Sliding per-IP minute window for the OAuth endpoints; key f"oauth:{ip}" in _minute_windows."""
    # cap = self._settings.oauth_rate_limit_per_min; over cap -> raise RateLimitedError(
    #   "Too many authorization requests from this IP in the last minute. Please slow down.")
    # Counts the request (append now) when allowed. Shares the lock and _prune_stale_entries.

# app/services/oauth_clients.py
def validate_redirect_uri(uri: str) -> None:
    """Raise OAuthError("invalid_redirect_uri", <why>) unless https://… or http://localhost|127.0.0.1|[::1] (any port/path), no fragment."""
def register_client(session: Session, *, redirect_uris: list[str], client_name: str) -> OAuthClient:
    """Validate every uri (validate_redirect_uri); insert OAuthClient(client_id="adkc_" + secrets.token_urlsafe(24), …); flush; return it. The cap is checked by the ROUTE via count_clients."""
def count_clients(session: Session) -> int: ...
def get_client(session: Session, client_id: str) -> OAuthClient | None: ...
def prune_stale_clients(session: Session, *, now: datetime) -> int:
    """Delete clients with created_at < now - 24h that have no oauth_consents, no api_tokens, and no oauth_refresh_tokens rows. Returns the count."""
```

Client id generation: `client_id = "adkc_" + secrets.token_urlsafe(24)` — do NOT go through
`generate_token` (that appends `token_urlsafe(32)` and returns a hash we don't need); import
`secrets` directly in the service. `token_hashing` is not used by this task.

```python
# app/models/schemas/oauth.py
class ClientRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    redirect_uris: list[str] | None = None            # required at the ROUTE level -> invalid_client_metadata when None/empty
    client_name: str | None = Field(default=None, max_length=200)
    token_endpoint_auth_method: str | None = None     # must be None or "none"
    grant_types: list[str] | None = None              # subset of {"authorization_code", "refresh_token"}
    response_types: list[str] | None = None           # subset of {"code"}
    scope: str | None = None                          # None or "mcp"

class ClientRegistrationResponse(BaseModel):
    client_id: str
    client_id_issued_at: int                          # unix seconds of created_at
    client_name: str
    redirect_uris: list[str]
    token_endpoint_auth_method: Literal["none"] = "none"
    grant_types: list[str]                            # ["authorization_code", "refresh_token"]
    response_types: list[str]                         # ["code"]
    scope: Literal["mcp"] = "mcp"
```

```python
# app/routes/oauth_routes.py — router = APIRouter(prefix="/oauth", tags=["oauth"])
POST /oauth/register   operation_id="oauth_register"   status 201   response_model=ClientRegistrationResponse
# deps: session=Depends(get_session), settings=Depends(get_settings), limiter=Depends(get_rate_limiter)
# body: ClientRegistrationRequest
# order: limiter.check_oauth_request(client_ip) -> prune_stale_clients(session, now=datetime.now(UTC))
#        -> metadata validation (each failure = OAuthError("invalid_client_metadata", <field-specific text>))
#        -> if count_clients(session) >= settings.oauth_max_clients: OAuthError("invalid_client_metadata", "Too many registered clients; try again later.")
#        -> register_client(...) -> response. Default client_name "Unnamed client" when absent/blank.
# responses={400: {"description": "OAuth error", "content": {"application/json": {"example": {"error": "invalid_client_metadata", "error_description": "…"}}}}, 429: {"model": ErrorEnvelope}}
```

`client_ip = request.client.host if request.client is not None else "unknown"` — copy the
existing expression from `public_routes.py`.

## Steps (TDD)

- [ ] **RED — test-author:**
  - `tests/test_oauth_errors.py` (DB-less `create_app(settings=Settings(session_secret="s"))`,
    add a throwaway route `/__oauth_err` that raises `OAuthError("invalid_grant", "bad", status_code=400)`
    and `/__oauth_err_401` raising `OAuthError("invalid_client", "who", status_code=401)`):
    - `test_oauth_error_renders_rfc_shape` — body `== {"error": "invalid_grant", "error_description": "bad"}`, status 400,
      no `"error": {"code": …}` envelope nesting.
    - `test_oauth_error_no_store_headers` — `Cache-Control == "no-store"`, `Pragma == "no-cache"`.
    - `test_oauth_error_status_code_honoured` — the 401 route returns 401.
    - `test_app_error_envelope_unchanged` — a throwaway route raising `NotFoundError("x")` still
      renders the existing `{"error": {"code": "not_found", "message": "x"}}` envelope.
  - `tests/test_ratelimit_oauth.py` (pure `RateLimiter(settings, clock=fake)`):
    - `test_oauth_window_allows_up_to_cap` — `oauth_rate_limit_per_min=3`: three calls pass, fourth raises `RateLimitedError`.
    - `test_oauth_window_slides` — advance the clock 61 s → allowed again.
    - `test_oauth_window_is_per_ip` — a different ip is unaffected.
    - `test_oauth_window_independent_of_message_window` — `check_message(ip, sid)` calls don't
      consume the oauth budget and vice versa.
    - `test_oauth_error_message_exact` — message string equals the one in Interfaces.
  - `tests/test_oauth_register.py` (DB; `_build_app()` like other DB tests, `oauth_issuer_url="https://api.example"`):
    - `test_register_minimal_returns_201_and_client` — body `{"redirect_uris": ["https://claude.ai/api/mcp/auth_callback"], "client_name": "Claude"}`
      → 201; `client_id.startswith("adkc_")`; `token_endpoint_auth_method == "none"`;
      `grant_types == ["authorization_code", "refresh_token"]`; `response_types == ["code"]`;
      `scope == "mcp"`; `client_id_issued_at` is an int; DB row exists with the same `redirect_uris`.
    - `test_register_ignores_unknown_fields` — extra `"foo": 1` is ignored (201).
    - `test_register_default_client_name` — no name → `"Unnamed client"`.
    - `test_register_requires_redirect_uris` — `{}` and `{"redirect_uris": []}` → 400 `invalid_client_metadata`.
    - `test_register_rejects_http_non_localhost` — `http://evil.example/cb` → 400 `invalid_redirect_uri`.
    - `test_register_accepts_localhost_variants` — `http://localhost:3000/cb`, `http://127.0.0.1/cb`, `http://[::1]:8/cb` → 201.
    - `test_register_rejects_fragment` — `https://a.example/cb#frag` → 400 `invalid_redirect_uri`.
    - `test_register_rejects_non_none_auth_method` — `token_endpoint_auth_method: "client_secret_basic"` → 400 `invalid_client_metadata`.
    - `test_register_rejects_unknown_grant_type` — `grant_types: ["implicit"]` → 400.
    - `test_register_rejects_unknown_response_type` — `response_types: ["token"]` → 400.
    - `test_register_rejects_bad_scope` — `scope: "admin"` → 400 `invalid_scope`.
    - `test_register_rejects_long_name` — 201-char `client_name` → 422 (Pydantic) — assert status only.
    - `test_register_cap_enforced` — settings `oauth_max_clients=2`: third register → 400
      `"Too many registered clients; try again later."`.
    - `test_register_prunes_stale_unused_clients` — insert a client with `created_at = now - 25h`
      (set directly on the row) and another aged client that owns an `OAuthConsent`; register →
      the unused one is gone, the consented one remains.
    - `test_register_rate_limited` — `oauth_rate_limit_per_min=1`: second call → 429 `rate_limited` envelope.
    - `test_register_error_headers` — any 400 carries `Cache-Control: no-store`.
    - `test_openapi_has_register_operation` — `/openapi.json` lists `oauth_register`.
  - Prove RED for all three files.
- [ ] **GREEN — implementer:** in this order — `OAuthError` → handler → limiter method → service →
  DTOs → route → factory include → regenerate baseline + codegens.
- [ ] Run the three new files + `tests/test_ratelimit.py` + `tests/test_app_factory.py` → PASS.
- [ ] Full backend gates.
- [ ] Commit: `feat(api): DCR client registration + OAuth error family + oauth rate limit (mcp-oauth t04)`
  including `openapi.json` and both `schema.d.ts`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_oauth_register.py tests/test_oauth_errors.py tests/test_ratelimit_oauth.py tests/test_ratelimit.py tests/test_app_factory.py
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json
```

## Acceptance

- Every 4xx from `/oauth/register` is RFC-shaped with no-store headers; the existing envelope for
  non-OAuth errors is untouched.
- Redirect-URI rules match Global Constraints exactly (five cases tested).
- Cap + prune + rate limit are all exercised.
- Reviewer (Opus) confirms: the route has no `try/except`; the service never commits; the prune
  query cannot delete a client that owns any consent/api_token/refresh row; `extra="ignore"` so
  claude.ai's extra DCR fields (`client_uri`, `contacts`, …) never 422.
