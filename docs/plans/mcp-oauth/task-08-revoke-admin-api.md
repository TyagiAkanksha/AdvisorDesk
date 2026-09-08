---
id: mcp-oauth-t08
phase: mcp-oauth
depends_on: [mcp-oauth-t07]
status: built
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 08 — `POST /oauth/revoke` (RFC 7009) + admin list/revoke API ★

## Goal

Give the client (and the admin UI) a way to kill tokens: RFC 7009 revocation for the OAuth
client, plus two admin-session-gated endpoints the "Connected apps" page (task 09) consumes —
list every registered client with its live-token summary, and revoke a client outright.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"Endpoints" (`/revoke`), §"Admin management UI".
- `docs/plans/mcp-oauth/00-INDEX.md` Global Constraints → **OAuth error shape**, **Rate limiting**,
  **Wire gates**.
- `CONVENTIONS.md` §3, §5, §6.
- `apps/api/app/services/oauth_tokens.py` (t07: `revoke_family`), `apps/api/app/services/oauth_clients.py` (t04).
- `apps/api/app/models/oauth.py`, `apps/api/app/models/api_tokens.py` (t01).
- `apps/api/app/routes/oauth_routes.py` (t04–t07), `apps/api/app/models/schemas/oauth.py`.
- `apps/api/app/routes/admin_routes.py` (existing admin router — `Depends(require_admin)` shape,
  `responses={401: …}`; you create a sibling router).
- `apps/api/app/factory.py` (router includes).
- `apps/api/tests/oauth_helpers.py` (`complete_authorization`), `apps/api/tests/test_oauth_token.py`
  (`_exchange`, `_mcp_initialize` helpers — copy, do not import test modules).

## Files

**Create**
- `apps/api/app/routes/oauth_admin_routes.py`
- `apps/api/tests/test_oauth_revoke_admin.py` (DB).

**Modify**
- `apps/api/app/services/oauth_tokens.py` — `revoke_token`.
- `apps/api/app/services/oauth_clients.py` — `list_connected_apps`, `delete_client`.
- `apps/api/app/models/schemas/oauth.py` — `ConnectedApp`, `ConnectedAppsResponse`.
- `apps/api/app/routes/oauth_routes.py` — `oauth_revoke`.
- `apps/api/app/factory.py` — include `oauth_admin_router` with `_API_PREFIX`, unconditional.
- `apps/api/openapi.json` + both `schema.d.ts` — regenerated.

## Interfaces

**Consumes:** `revoke_family` (t07), `hash_token` (t01), `get_client` (t04), `OAuthError` (t04),
`check_oauth_request` (t04), `require_admin` (existing), `NotFoundError` (existing),
`OAuthClient`, `OAuthConsent`, `OAuthRefreshToken`, `ApiToken`.

**Produces exactly:**

```python
# app/services/oauth_tokens.py — addition
def revoke_token(session: Session, *, raw_token: str, client_id: str, now: datetime) -> None:
    """RFC 7009 §2.2: always succeeds from the caller's view. Refresh token -> revoke_family; access token -> delete that ApiToken row only; unknown or other client's token -> no-op."""
    # hashed = hash_token(raw_token)
    # refresh = select OAuthRefreshToken by token_hash; if refresh and refresh.client_id == client_id: revoke_family(session, refresh.family_id, now); return
    # access = select ApiToken by token_hash; if access and access.client_id == client_id: session.delete(access); flush
    # (token_type_hint is accepted by the route but ignored — both lookups are cheap.)

# app/services/oauth_clients.py — additions
@dataclass(frozen=True)
class ConnectedAppRow:
    client_id: str
    client_name: str
    redirect_uris: list[str]
    created_at: datetime
    consent_granted_at: datetime | None      # latest OAuthConsent.updated_at with revoked_at IS NULL
    active_access_tokens: int                # ApiToken rows with client_id == this and (expires_at IS NULL OR expires_at > now)
    active_refresh_tokens: int               # OAuthRefreshToken rows revoked_at IS NULL and expires_at > now
    last_used_at: datetime | None            # max(ApiToken.last_used_at) over this client
    latest_expires_at: datetime | None       # max(OAuthRefreshToken.expires_at) over active refresh rows
def list_connected_apps(session: Session, *, now: datetime) -> list[ConnectedAppRow]:
    # ordered by created_at DESC; one row per oauth_clients row (clients with zero tokens still appear)
def delete_client(session: Session, client_id: str) -> bool:
    # get_client; None -> False; session.delete(client); flush; True   (FK CASCADE removes codes/refresh/consents/api_tokens)
```

```python
# app/models/schemas/oauth.py — additions (from_attributes=True so the dataclass maps directly)
class ConnectedApp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    client_id: str
    client_name: str
    redirect_uris: list[str]
    created_at: datetime
    consent_granted_at: datetime | None
    active_access_tokens: int
    active_refresh_tokens: int
    last_used_at: datetime | None
    latest_expires_at: datetime | None
class ConnectedAppsResponse(BaseModel):
    items: list[ConnectedApp]
```

```python
# app/routes/oauth_routes.py — addition
POST /oauth/revoke   operation_id="oauth_revoke"   -> Response (200, empty body)
# form: token, token_type_hint, client_id (all Annotated[str | None, Form()] = None)
# limiter.check_oauth_request(ip)
# token None                              -> OAuthError("invalid_request", "token is required.")
# client_id None or get_client is None    -> OAuthError("invalid_client", "Unknown client.", status_code=401)
# revoke_token(session, raw_token=token, client_id=client_id, now=datetime.now(UTC))
# return Response(status_code=200, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

# app/routes/oauth_admin_routes.py — router = APIRouter(prefix="/oauth/clients", tags=["oauth-admin"], dependencies=[Depends(require_admin)])
GET    /oauth/clients               operation_id="oauth_clients_list"    response_model=ConnectedAppsResponse
DELETE /oauth/clients/{client_id}   operation_id="oauth_client_revoke"   status 204   (NotFoundError("Client not found.") -> 404 envelope when delete_client returns False)
# responses={401: {"model": ErrorEnvelope}} on both; 404 on DELETE
```

## Steps (TDD)

- [ ] **RED — test-author** writes `tests/test_oauth_revoke_admin.py` (DB; helpers copied from
  `test_oauth_token.py`; `complete_authorization` + exchange to get a live pair):
  - `test_revoke_refresh_token_kills_family` — POST `/oauth/revoke` `token=<refresh>, client_id` →
    200 empty body + no-store; refresh row `revoked_at` set; access token → MCP 401.
  - `test_revoke_access_token_only` — `token=<access>` → 200; access → 401; refresh row still
    active and CAN still rotate (200 at `/token`).
  - `test_revoke_unknown_token_200` — `token=adkr_nope` → 200 (RFC 7009 §2.2).
  - `test_revoke_other_clients_token_noop` — register a second client, present the first client's
    refresh token with the second `client_id` → 200; nothing revoked (access still 200 at MCP).
  - `test_revoke_missing_token_400`; `test_revoke_unknown_client_401`; `test_revoke_rate_limited`.
  - `test_admin_list_requires_session` — GET `/api/v1/oauth/clients` no cookie → 401 envelope.
  - `test_admin_list_shape` — after one full flow: one item; `client_id`, `client_name == "Claude"`,
    `redirect_uris`, `active_access_tokens == 1`, `active_refresh_tokens == 1`,
    `consent_granted_at` not None, `last_used_at` None before any MCP call and not None after
    one `initialize`, `latest_expires_at` ≈ created + 30 d; body key `items`.
  - `test_admin_list_counts_exclude_expired_and_revoked` — backdate the access row's `expires_at`
    and set `revoked_at` on the refresh row → both counts 0, `latest_expires_at` None.
  - `test_admin_list_includes_tokenless_client` — a freshly registered client appears with zeros.
  - `test_admin_list_ordered_newest_first`.
  - `test_admin_revoke_client_204_and_cascade` — DELETE → 204; client, consent, refresh,
    api_token rows gone; access token → MCP 401; refresh → `/token` 401 `invalid_client`.
  - `test_admin_revoke_unknown_404`; `test_admin_revoke_requires_session`.
  - `test_openapi_has_revoke_and_admin_operations` — `oauth_revoke`, `oauth_clients_list`,
    `oauth_client_revoke`; and `components.schemas` contains `ConnectedApp` + `ConnectedAppsResponse`.
  - Prove RED.
- [ ] **GREEN — implementer:** services → DTOs → routes → factory → regenerate baseline + codegens.
- [ ] Run `tests/test_oauth_revoke_admin.py tests/test_oauth_token.py tests/test_oauth_register.py` → PASS.
- [ ] Full backend gates.
- [ ] Commit: `feat(api): RFC 7009 revoke + admin connected-apps list/revoke (mcp-oauth t08)`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_oauth_revoke_admin.py tests/test_oauth_token.py
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json
grep -c '"ConnectedApp"' apps/admin/src/types/generated/schema.d.ts   # >= 1 after codegen
```

## Acceptance

- `/oauth/revoke` never reveals whether a token existed (always 200 for a known client).
- Admin endpoints are cookie-gated; DELETE cascades and the tokens stop working immediately.
- `ConnectedApp` / `ConnectedAppsResponse` are in `openapi.json` and both `schema.d.ts` so task 09
  can `components['schemas']['ConnectedApp']`.
- Reviewer (Opus) confirms: the list query is not N+1 (aggregate subqueries or one grouped query
  per table, not per client); `revoke_token` cannot revoke across clients; no raw token logged.
