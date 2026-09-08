# MCP OAuth 2.1 Authorization Server — Design Spec

**Status:** **approved by owner 2026-09-07** ("go ahead, ensure everything is well set"). Implementation
plan: `docs/plans/mcp-oauth/00-INDEX.md` + task files.
**Goal:** make claude.ai's remote-connector **"Connect"** button work end-to-end against
`https://api.advisordesk.tyagiakanksha.com/api/v1/mcp` — an allowlisted admin clicks Connect,
signs in with Google, approves a consent screen, and Claude gets a rotating OAuth token. Replaces
the manual "mint a CLI token + paste an `Authorization` header" flow.

**Owner decisions (brainstorm, 2026-09-07):** *Full polish* (refresh tokens + explicit consent
screen + admin UI to view/revoke connected clients) · client registration via **DCR** (RFC 7591).

## Conformance target (authoritative)

MCP Authorization spec (rev 2025-06-18) — our server plays **both** OAuth roles, co-hosted:

- **Resource server** (the `/api/v1/mcp` endpoint):
  - MUST implement **RFC 9728** Protected Resource Metadata at `/.well-known/oauth-protected-resource`,
    including an `authorization_servers` array (≥1) and the `resource` identifier.
  - MUST return `WWW-Authenticate` on 401 pointing to that metadata URL (RFC 9728 §5.1 form:
    `Bearer resource_metadata="https://api.advisordesk.tyagiakanksha.com/.well-known/oauth-protected-resource"`).
  - MUST validate the presented token was issued **for this resource** (audience binding, RFC 8707);
    reject otherwise. Invalid/expired → 401; insufficient scope → 403; malformed → 400.
- **Authorization server:**
  - MUST provide **RFC 8414** AS metadata at `/.well-known/oauth-authorization-server`.
  - MUST implement OAuth 2.1 authorization-code flow with **PKCE S256 (mandatory)**.
  - SHOULD support **DCR (RFC 7591)** → `POST /register` (we do).
  - MUST validate **exact** `redirect_uri` against the registered client's values.
  - For public clients, MUST **rotate refresh tokens** (OAuth 2.1 §4.3.1). Access tokens SHOULD be short-lived.
  - MUST accept + honor the `resource` parameter (RFC 8707) on authorize + token requests and bind
    the issued token's audience to it.
  - All endpoints HTTPS; redirect URIs `localhost` or HTTPS only.

**Implemented carve-outs (mcp-oauth, ruled at plan time):** with a single `mcp` scope there is no
insufficient-scope state — a token either resolves to an allowlisted admin or it does not — so no
403 path exists; and a malformed `Authorization` header stays **401** (`reason=malformed`) rather
than 400, preserving the byte-identical 401 envelope that keeps the rejection reason unobservable
from outside.

**Canonical resource URI** (the `resource` value + audience): `https://api.advisordesk.tyagiakanksha.com/api/v1/mcp`
(most-specific, no trailing slash).

## End-to-end flow

1. Claude → `POST /api/v1/mcp` with no token → **401** + `WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"`.
2. Claude → `GET /.well-known/oauth-protected-resource` → `{ resource, authorization_servers: ["https://api.advisordesk.tyagiakanksha.com"] }`.
3. Claude → `GET /.well-known/oauth-authorization-server` → AS metadata (endpoints + capabilities).
4. Claude → `POST /register` (DCR) with its `redirect_uris` + name → `{ client_id, … }` (public client, no secret).
5. Claude opens `GET /authorize?response_type=code&client_id=…&redirect_uri=…&code_challenge=…&code_challenge_method=S256&state=…&resource=…&scope=mcp`.
   - Our `/authorize` validates the request, then **bridges to the existing Google login**
     (`app.auth.oauth` + signed-state CSRF). After Google returns an allowlisted admin, we show a
     **consent screen** ("Claude wants MCP access to AdvisorDesk — Approve / Deny").
6. Approve → issue a single-use **authorization code** (short TTL, bound to `client_id` +
   exact `redirect_uri` + PKCE `code_challenge` + `resource` + the admin user) → 302 back to
   `redirect_uri?code=…&state=…`.
7. Claude → `POST /token` (`grant_type=authorization_code`, `code`, `code_verifier`, `redirect_uri`,
   `resource`, `client_id`) → validate PKCE + exact redirect_uri + audience → return
   `{ access_token (adk_…), token_type: "Bearer", expires_in, refresh_token, scope }`.
8. Claude → `POST /api/v1/mcp` with `Authorization: Bearer <access_token>` → validated (audience +
   allowlist + epoch + expiry) → **all 9 tools**. On expiry, Claude uses `grant_type=refresh_token`
   (rotated) to get a fresh access token — no user interaction.

## Components & recommended technical calls

### Endpoints
| Endpoint | Location | Purpose |
|---|---|---|
| `GET /.well-known/oauth-protected-resource` | **root** (outside `/api/v1`) | RFC 9728 RS metadata |
| `GET /.well-known/oauth-authorization-server` | **root** | RFC 8414 AS metadata |
| `POST /register` | `/api/v1/oauth/register` (advertised via metadata) | DCR (RFC 7591) |
| `GET /authorize` | `/api/v1/oauth/authorize` | authorize + Google bridge + consent |
| `POST /token` | `/api/v1/oauth/token` | code + refresh grants |
| `POST /revoke` | `/api/v1/oauth/revoke` | RFC 7009 token revocation (used by admin UI) |

The two `.well-known` docs live at the domain **root** (RFC-mandated); the `authorization_endpoint`
etc. inside them point at the `/api/v1/oauth/*` paths. Caddy already proxies the whole `api.`
subdomain to the API container, so root paths reach FastAPI — the app just registers these two
routes outside the `_API_PREFIX` router.

### Token & data model
- **Access tokens reuse the existing `adk_` model** (`app.auth.tokens` — CSPRNG + sha256-at-rest,
  and `resolve_bearer_token` already enforces allowlist + `session_epoch` + `expires_at`), so the
  MCP endpoint's validation path barely changes. Extend the token row with `client_id` (nullable;
  NULL = CLI-minted) and `resource`/audience, and add **audience validation** to the MCP resolve
  (token's `resource` MUST equal the canonical MCP URI).
- **New tables** (Alembic migration): `oauth_clients` (DCR: client_id, redirect_uris[], client_name,
  created_at), `oauth_authorization_codes` (code_hash, client_id, redirect_uri, code_challenge,
  resource, user_id, scope, expires_at, consumed_at — single-use), `oauth_refresh_tokens`
  (token_hash, access-token linkage, client_id, user_id, resource, rotated_from, expires_at,
  revoked_at). Refresh tokens rotate on every use (old one revoked).
- **Scope:** a single `mcp` scope granting the admin MCP tools (same authority as today's bearer).

### Google bridge + consent (reuse, don't reinvent)
`/authorize` reuses `app.auth.oauth.GoogleOAuthClient` + `app.auth.state` signed-state CSRF and the
allowlist check that `/auth/callback` already performs. The **consent screen** is a minimal
server-rendered HTML page on the API (simplest for the mid-redirect hop); Approve posts back to
issue the code. Per-client consent (each DCR client id) satisfies the MCP "confused-deputy"
requirement. We never pass Google's token through — we mint our own `adk_` token, so there is no
token-passthrough exposure.

### Admin management UI (the first visible new UI)
A new **admin-app page** ("Connected apps") lists DCR clients + live tokens (client name, admin,
issued, last used, expiry) with a **Revoke** action, backed by new admin-session-gated API
endpoints (list + revoke → `/revoke`). Revoking calls `revoke_family` (kills the refresh-token
family and its current access token) or deletes the client outright (`CASCADE`s every dependent
row) — **not** an epoch bump: `/auth/logout`'s epoch bump only invalidates the current access
token, and the next refresh silently re-mints a new one under the new epoch, so web logout is not
connected-app revocation (task-07 review, finding I-1). `POST /oauth/revoke` (RFC 7009) kills
tokens but does not retract consent — `OAuthConsent.revoked_at` has no writer yet — so that
client can re-authorize without a new prompt; only the admin's Revoke (client `DELETE`, cascading
the consent row) fully de-authorizes.

## Security / threat model (all MUST unless noted)

- PKCE **S256 mandatory**; reject authorize/token without a valid challenge/verifier pair.
- **Exact** `redirect_uri` match against the registered client (no prefix/substring); redirect URIs HTTPS or localhost only; open-redirect prevention on any error redirect.
- Authorization codes: single-use, short TTL (~60s), hashed at rest, bound to client+redirect+PKCE+resource+user.
- **Refresh-token rotation** on every refresh; detect reuse of a rotated (revoked) refresh token → revoke the whole chain.
- Concurrent replay is self-inflicted DoS by design: two requests racing the same authorization
  code or the same refresh token → one wins, the loser trips the replay/reuse branch and revokes
  the whole family, including the tokens the winner was just issued. A client that retries in
  parallel (or a proxy that duplicates a POST) loses its grant and must re-consent. This is
  correct per RFC 6819 and is NOT a bug.
- **Audience binding:** issued tokens carry the MCP `resource`; the MCP endpoint validates it. Reject tokens not issued for this resource.
- Allowlist re-checked at every resolve (already true) + at authorize (Google callback).
- **Rate-limit** `/register`, `/authorize`, and `/token` (reuse `app.routes.ratelimit`); DCR is open per MCP, so cap client creation + prune stale/unused clients.
- Secrets: codes/refresh/access all sha256-at-rest; never logged. HTTPS enforced (Caddy).
- Error responses follow OAuth 2.1: 401 (auth required/invalid token), 403 (scope), 400 (malformed) + the standard `{ "error": … }` bodies on the OAuth endpoints.

## Error handling
OAuth endpoints return RFC-shaped `{ "error": "...", "error_description": "..." }` with correct
status codes; the MCP resource endpoint keeps its current in-band JSON-RPC error behavior for tool
errors but uses 401/403/400 at the transport layer per the table above. Reuse
`app.routes.errors.register_error_handlers` where it fits; OAuth-specific error shapes are their own.

## Testing strategy
- **Unit (TDD, fakes only — no real Google/network):** each endpoint in isolation — metadata docs
  exact shape; DCR register/validate; `/authorize` request validation + PKCE + exact-redirect + the
  Google-bridge branch (fake `GoogleOAuthClient`) + consent gating; `/token` code+PKCE+audience and
  refresh-rotation (incl. reuse-detection); MCP 401 `WWW-Authenticate`; audience rejection.
- **Security-focused adversarial tests:** PKCE downgrade, wrong `code_verifier`, redirect_uri
  mismatch, code replay, refresh reuse, cross-resource token, non-allowlisted admin.
- **End-to-end (final):** a **real claude.ai connect** against a staging/prod deploy — the true
  acceptance test — recorded.

## Task breakdown (for the implementation plan)
Suggested order + phasing; each is a three-agent SDD task, **Opus review on every security-critical one (★)**:
1. Data model + Alembic migration (`oauth_clients`, `oauth_authorization_codes`, `oauth_refresh_tokens`; extend api_tokens). ★
2. Discovery documents (RFC 9728 + RFC 8414) at root + config. 
3. MCP 401 `WWW-Authenticate` challenge + audience validation on resolve. ★
4. DCR `/register` (RFC 7591). ★
5. `/authorize` — request validation + PKCE + Google bridge (reuse) + auth-code issuance. ★
6. Consent screen (server-rendered) + per-client consent record. ★
7. `/token` — authorization_code grant + refresh grant with rotation + reuse detection. ★
8. `/revoke` (RFC 7009) + admin list/revoke API endpoints. ★
9. Admin "Connected apps" UI page (apps/admin). 
10. Wiring + Caddy note + **end-to-end real-connect verification**. ★

**Phasing option:** Tasks 1–5+7 deliver a *working Connect* (core OAuth); 6, 8, 9 add the polish
(consent + management). Could ship core first, polish second — decide at plan time.

## Non-goals (MVP boundary)
- No third-party/upstream API proxying (we are the only resource; no token passthrough).
- No multi-tenant / non-admin users — the `mcp` scope maps to the existing admin allowlist.
- No CIMD and no static-client path (DCR is the one registration method). CLI mint (`scripts/mint_mcp_token.py`) is **kept** as an ops/CI fallback.
- Access-token format stays opaque `adk_` (not JWT) — simpler, and validation already exists.

## Decisions pinned at plan time (owner: "go ahead, ensure everything is well set", 2026-09-07)
- **Token lifetimes:** access token **60 min**; refresh token **30 days**, rotated on every use
  (a rotated refresh token inherits the *remaining* 30-day window — the chain does not extend
  forever; re-consent after 30 days of the original grant).
- **Authorization-code TTL:** 60 s, single-use.
- **Consent screen:** server-rendered HTML on the API (`/api/v1/oauth/authorize` continuation),
  not a route in the admin app.
- **Phasing:** **one plan, one branch (`feat/mcp-oauth`), one PR.** Tasks are ordered core-first
  (1–5, 7) so a working Connect exists mid-branch, but the branch ships only when the polish
  (6, 8, 9) and the real-connect e2e (10) are green. Rationale: owner chose "Full polish"; a
  second PR/deploy round buys nothing for a solo owner.
