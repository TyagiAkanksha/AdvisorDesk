---
id: mcp-oauth-t06
phase: mcp-oauth
depends_on: [mcp-oauth-t05, mcp-oauth-t07]
status: built
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 06 — Consent screen (server-rendered) + per-client consent record ★

## Goal

Insert the confused-deputy guard: the first time an admin authorizes a given `client_id`,
`/authorize/continue` renders an HTML "Approve / Deny" page instead of issuing the code
immediately; Approve records an `OAuthConsent` row and issues the code; later authorizations
for the same `(user, client)` skip the page. Runs **after task 07** so the whole flow stays
green end-to-end.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"Google bridge + consent", §"End-to-end flow" step 5–6,
  §"Decisions pinned" (server-rendered consent on the API).
- `docs/plans/mcp-oauth/00-INDEX.md` Global Constraints → **OAuth error shape**, **Rate limiting**,
  **SDD discipline** (this task may extend `tests/oauth_helpers.py::complete_authorization`).
- `CONVENTIONS.md` §3, §5.
- `apps/api/app/routes/oauth_routes.py` (t05: `oauth_authorize_continue`, `_issue_code_and_redirect`;
  t07: form-field style).
- `apps/api/app/auth/oauth_request.py` (`PendingAuthorization.nonce`, cookie helpers).
- `apps/api/app/auth/deps.py` (`resolve_admin`, `require_admin`).
- `apps/api/app/models/oauth.py` (`OAuthConsent` — unique `(user_id, client_id)`, `revoked_at`).
- `apps/api/app/services/oauth_clients.py` (`get_client` — for `client_name`).
- `apps/api/tests/oauth_helpers.py` (`complete_authorization` — extend to click Approve),
  `apps/api/tests/test_oauth_authorize.py` (`test_full_bridge_issues_code` — its assertions must
  keep passing through the extended helper).

## Files

**Create**
- `apps/api/app/services/oauth_consents.py`
- `apps/api/app/routes/oauth_consent_html.py` — pure rendering, no FastAPI imports.
- `apps/api/tests/test_oauth_consent.py` (DB).

**Modify**
- `apps/api/app/routes/oauth_routes.py` — consent gate in `oauth_authorize_continue`; new
  `oauth_authorize_decision`.
- `apps/api/tests/oauth_helpers.py` — `complete_authorization` handles the 200 HTML hop by
  POSTing `decision=approve` with the nonce parsed from the page (regex on
  `name="nonce" value="([^"]+)"`); when `continue` already 302s (consent on file) it behaves as before.
- `apps/api/openapi.json` + both `schema.d.ts` — regenerated.

## Interfaces

**Consumes:** `PendingAuthorization` (t05), `read_pending_authorization`, `clear_pending_cookie`
(t05), `resolve_admin`, `require_admin` (t05), `_issue_code_and_redirect` (t05),
`OAuthError`, `OAuthRedirectError` (t04/t05), `get_client` (t04), `OAuthConsent` (t01).

**Produces exactly:**

```python
# app/services/oauth_consents.py
def find_active_consent(session: Session, *, user_id: uuid.UUID, client_id: str) -> OAuthConsent | None:
    # revoked_at IS NULL only
def record_consent(session: Session, *, user_id: uuid.UUID, client_id: str, scope: str, now: datetime) -> OAuthConsent:
    # existing row (any revoked_at) -> set scope, revoked_at=None; else insert; flush; return

# app/routes/oauth_consent_html.py
CONSENT_CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"
def render_consent_page(*, client_name: str, user_email: str, action_path: str, nonce: str) -> str:
    # html.escape() every interpolated value (client_name, user_email, action_path, nonce).
    # Minimal document: <title>Authorize AdvisorDesk MCP access</title>; inline <style> only; body says
    #   "<client_name> wants MCP access to AdvisorDesk" and "Signed in as <user_email>" and lists the single scope
    #   "mcp — use the AdvisorDesk MCP tools (admin-level access)";
    #   <form method="post" action="<action_path>"> with <input type="hidden" name="nonce" value="…">,
    #   <button type="submit" name="decision" value="approve">Approve</button>
    #   <button type="submit" name="decision" value="deny">Deny</button>. No script tags, no external assets.
```

```python
# app/routes/oauth_routes.py
# oauth_authorize_continue — after the allowlist check:
#   if find_active_consent(session, user_id=principal.user_id, client_id=pending.client_id) is not None:
#       return _issue_code_and_redirect(session, pending, principal, settings)
#   client = get_client(session, pending.client_id)   # None -> OAuthError("invalid_client", "Unknown client.") (client deleted mid-flow)
#   html = render_consent_page(client_name=client.client_name, user_email=principal.email,
#                              action_path="/api/v1/oauth/authorize/decision", nonce=pending.nonce)
#   return HTMLResponse(html, headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Content-Security-Policy": CONSENT_CSP})

POST /oauth/authorize/decision   operation_id="oauth_authorize_decision"   -> Response
# form: decision: Annotated[str | None, Form()] = None; nonce: Annotated[str | None, Form()] = None
# limiter.check_oauth_request(ip)
# pending = read_pending_authorization(cookie, settings); None -> OAuthError("invalid_request", "No pending authorization request.")
# principal = require_admin(request)                      # 401 auth_required envelope when the session vanished
# if principal.email.lower() not in settings.admin_email_set -> OAuthRedirectError("access_denied", …, pending.redirect_uri, pending.state)
# if nonce != pending.nonce (hmac.compare_digest on str) -> OAuthError("invalid_request", "Consent form token mismatch.")
# decision == "deny": response = RedirectResponse(<redirect_uri>?error=access_denied&error_description=The+user+denied+the+request.&state=…, 302, no-store headers); clear_pending_cookie(response); return
# decision == "approve": record_consent(session, user_id=principal.user_id, client_id=pending.client_id, scope=pending.scope, now=datetime.now(UTC)); return _issue_code_and_redirect(...)
# else -> OAuthError("invalid_request", "decision must be approve or deny.")
# responses: 200 text/html is documented on `continue` via responses={200: {"content": {"text/html": {}}}}
```

The deny redirect must reuse the same `?`/`&` separator logic as `_issue_code_and_redirect` —
factor a tiny module-level `_redirect_with_params(redirect_uri, params) -> str` in
`oauth_routes.py` and use it in both places (and in the t05 error handler if the implementer
prefers a shared helper in `app/routes/errors.py`; either is acceptable, duplication is not).

## Steps (TDD)

- [ ] **RED — test-author** writes `tests/test_oauth_consent.py` (DB; same `_build_app` as
  `test_oauth_authorize`; helper `_reach_consent(client, *, client_name="Claude") -> tuple[str, str]`
  = register (with `client_name`) → authorize → `login_as` → GET continue, returns `(html, nonce)`):
  - `test_first_authorization_renders_consent_page` — 200, `content-type` starts with `text/html`,
    `Cache-Control: no-store`, CSP header equals `CONSENT_CSP`; body contains `Claude`,
    `admin@example.com`, `name="decision" value="approve"`, `value="deny"`, `name="nonce"`.
  - `test_consent_page_escapes_client_name` — `client_name="<b>Evil</b>"` → body contains
    `&lt;b&gt;Evil&lt;/b&gt;` and NOT `<b>Evil</b>`.
  - `test_consent_page_has_no_script` — `<script` not in body.
  - `test_approve_records_consent_and_issues_code` — POST decision `approve` + nonce → 302 with
    `code=` + `state=xyz`; `OAuthConsent` row with `revoked_at None`, `scope == "mcp"`; pending
    cookie cleared.
  - `test_repeat_authorization_skips_consent` — after approve, authorize the same client again
    (new state) → continue → 302 with a code directly (no HTML).
  - `test_revoked_consent_reprompts` — set `revoked_at` on the row in `db_session` → continue → 200 HTML;
    approve again → row revived (`revoked_at None`, same row id).
  - `test_deny_redirects_access_denied` — 302 `error=access_denied`, `state=xyz`; no consent row;
    cookie cleared; no code row.
  - `test_wrong_nonce_400` — 400 `invalid_request` "Consent form token mismatch."; no code row.
  - `test_decision_without_cookie_400`; `test_decision_without_session_401` (drop the admin
    cookie → 401 `auth_required` envelope); `test_bad_decision_value_400`.
  - `test_decision_rate_limited` — `oauth_rate_limit_per_min=1`.
  - `test_openapi_has_decision_operation`.
  - Extend `tests/oauth_helpers.py::complete_authorization` as described (the test-author owns
    this edit; the implementer keeps it working). Re-run `tests/test_oauth_authorize.py` and
    `tests/test_oauth_token.py` — they now FAIL at the consent hop (RED evidence), except through
    the extended helper once GREEN.
  - Prove RED.
- [ ] **GREEN — implementer:** service → renderer → route changes → regenerate baseline + codegens.
- [ ] Run `tests/test_oauth_consent.py tests/test_oauth_authorize.py tests/test_oauth_token.py` → PASS.
- [ ] Full backend gates.
- [ ] Commit: `feat(api): consent screen + per-client consent record (mcp-oauth t06)`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_oauth_consent.py tests/test_oauth_authorize.py tests/test_oauth_token.py
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json
```

## Acceptance

- First authorization per `(user, client)` shows the page; approve → consent row + code; deny →
  `access_denied` redirect; repeat → no page.
- The page is XSS-safe (escaped), script-free, CSP-locked, `no-store`.
- The decision POST is bound to the pending request by the signed-cookie nonce.
- Reviewer (Opus) confirms: no code is issued without an approve for a client lacking consent;
  `require_admin` (not `resolve_admin`) guards the POST so a lost session is a 401, never a 307
  loop; the helper extension did not weaken any t05/t07 assertion.
