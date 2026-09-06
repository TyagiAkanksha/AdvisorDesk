# Task 6R-09 — Bearer-token expiry + ADMIN_EMAILS re-check on resolve (WR-02 residual)

WR-id: WR-02 residual (the expiry + allowlist-recheck halves left open by 6R-03, review M5). Effort M.
Full three-agent SDD; security surface ⇒ reviewer escalates. Builds on 6R-03's session-epoch work.

## Context

6R-03 (f189453) closed logout-revocation: a bumped `session_epoch` invalidates outstanding tokens.
Still open: (a) tokens never EXPIRE on their own; (b) `resolve_bearer_token` never re-checks the
resolved user's email against `ADMIN_EMAILS` (offboarding an admin from the allowlist doesn't kill
their token). Both are the WR-02 threat model's remaining teeth.

## Design pins

1. **Migration 0006** (chained after 0005): `api_tokens.expires_at TIMESTAMPTZ NULL`. NULL = "no
   expiry" (preserves existing tokens' behavior — do not force-expire the owner's live connector).
   Mint stamps `now() + <ttl>`; TTL from a new `Settings.mcp_token_ttl_days` (default: pick a sane
   value — 90 days — and document it; env-overridable). Existing rows stay NULL (backfill NULL).
2. **resolve_bearer_token** — after the existing hash→user + epoch checks, add: (a) if `expires_at`
   is not NULL and `< now()`, reject; (b) re-check the resolved user's normalized email against
   `admin_email_set` (the same set `auth_callback` uses), reject if absent. Both rejections use the
   SAME AuthRequiredError path/code as today — no new wire surface, no oracle (identical to unknown).
   Audit-log the reason keyword (`expired` / `not-allowlisted`) per 6R-03's logging pattern — token
   id only, never the token.
3. **mint script** (`scripts/mint_mcp_token.py`): `--list` should show expiry (and epoch-revoked
   state per 6R-03 review M6 if cheap) so an operator can see token lifecycle. Stamp expires_at on mint.
4. Wire surface: no route/DTO change ⇒ openapi.json + mcp-tools.json byte-stable.

## Test-author scope (RED, new file `tests/test_bearer_expiry_allowlist.py`)

- mint stamps expires_at = now + ttl (fake-clock or freeze); a token past expiry → 401 identical
  envelope to unknown; a NULL-expiry legacy token still works.
- allowlist re-check: mint for an admin, remove their email from ADMIN_EMAILS (settings override),
  resolve → 401; envelope identical to unknown.
- migration 0006 up/down/up round-trip; existing rows backfill NULL.
- audit-log pins for `expired` / `not-allowlisted` reasons + never-log assertions (reuse the
  log-hygiene pattern from test_auth_log_hygiene.py — new helpers, no edits to pinned files).
Pinned-file stop rule: 6R-03's test_bearer_revocation.py (5e8ece9e) + registry hashes untouchable.

## Acceptance

Full suite green env-exported; five api gates clean; migration round-trip; wire baselines byte-stable;
pins re-verified. Path-scoped adds: migration 0006, app/models/api_tokens.py, app/auth/tokens.py,
app/config.py, scripts/mint_mcp_token.py, new test file. Owner-pending files untouchable. Commit
`feat(api): bearer-token expiry + allowlist re-check on resolve (6R-09, WR-02 residual)`.
