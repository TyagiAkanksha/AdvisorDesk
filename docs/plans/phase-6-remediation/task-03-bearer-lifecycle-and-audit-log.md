# Task 6R-03 — Bearer-token revocation via session epoch + auth audit logging

WR-ids: WR-02, WR-05. Effort M. Full three-agent SDD (test-author → implementer → reviewer; security
surface ⇒ reviewer escalates per model policy). Independent of other 6R tasks.

## Goal

A leaked MCP bearer token becomes containable: `/auth/logout` (which bumps `users.session_epoch`)
revokes every outstanding bearer token for that user, exactly as it already kills cookies. And every
auth event leaves a log line, so use of any credential is observable.

## Design pins (controller decisions — implementer freedom only where marked)

1. **Migration 0005** (chained after 0004): `api_tokens.session_epoch` INTEGER NOT NULL. Backfill for
   existing rows: the owning user's **current** `session_epoch` (existing tokens keep working until
   the next logout — deliberate; a hard-revoke backfill would break the owner's live connector
   silently).
2. **Mint** (`app/auth/tokens.py::mint`, + the script paths that reach it): stamp the user's current
   `session_epoch` on the new row.
3. **Resolve** (`resolve_bearer_token`): after the existing hash→user resolution, reject
   (`AuthRequiredError`, same code/envelope as today's failures — no new wire surface) when
   `token.session_epoch != user.session_epoch`. Constant behavior for well-formed-but-revoked ==
   well-formed-but-unknown (no oracle distinguishing the two from outside).
4. **Audit logging** (WR-05): module-level `logging.getLogger(__name__)` in the auth modules; six
   events, exact content pins:
   - login success → INFO, email
   - login rejected (allowlist / soft-deleted) → WARNING, email + reason keyword
   - OAuth state verification failed → WARNING (no state value logged)
   - logout → INFO, user id + whether epoch bumped
   - bearer resolved → INFO, token row id ONLY
   - bearer rejected → WARNING, reason keyword (`malformed` / `unknown` / `revoked` / `inactive-user`), NEVER any part of the presented token
   **Never log**: raw tokens, token hashes, cookie values, state values, secrets. Reviewer greps for this.
5. Wire surface: zero route/DTO changes ⇒ `openapi.json` + `mcp-tools.json` byte-stable (gate).
6. CONVENTIONS §2 note: `app/auth/tokens.py` already carries the owner-ratified raw-ORM exception
   (t04-M1, owner ruled leave-as-is 2026-08-31-era batch is pending but the review recommended
   as-is) — extending its queries for the epoch check stays inside that documented exception;
   do not relocate the module.

## Test-author scope (RED first, new files only; sha256 pin on handoff)

New file `tests/test_bearer_revocation.py` (+ may extend `tests/auth_helpers.py` ONLY via new
helpers, not edits to existing ones):
- mint → resolve OK (epoch match) — guards the backfill/mint path
- mint → logout (epoch bump) → same token now 401; a freshly-minted post-logout token works
- revoked-token rejection is envelope-identical to unknown-token rejection
- migration 0005 up/down/up round-trip clean (mirror `test_lifecycle` migration pattern)
- caplog pins for all six audit events, including the never-log assertions (assert raw token/state
  absent from records)
Standing rules apply: env-export line verbatim, ruff/format-clean upfront, app.* imports first-party
placed for the post-GREEN I001 flip (pre-authorized reorder pattern if it flips anyway).

## Acceptance

Full suite green env-exported (baseline 453 + new), all five api gates clean, both wire baselines
byte-stable, migration round-trip evidence, pins verified at every round boundary. Path-scoped adds
only; the owner-pending dirty files are untouchable.
