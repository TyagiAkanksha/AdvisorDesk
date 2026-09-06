# Task 6R-05 — Security response headers

WR-id: WR-04. Effort S. Depends on 6R-04 (committed Caddyfile must exist). Three-agent SDD; the
frontend halves obey standing rule (d): live-server curl evidence is mandatory.

## Design pins (use the review's CORRECTED rationale — the cross-site-iframe clickjacking scenario
was refuted by the verifier; the real drivers are the first-visit HTTP downgrade window and
same-registrable-domain framing)

1. **Both `next.config.ts` files** gain an `async headers()` block applying to `/(.*)`:
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   (No CSP in this task — a real CSP for the MUI/Emotion inline-style stack needs its own
   design pass; note it as a follow-up, don't ship `unsafe-inline` theater.)
2. **Committed `infra/deploy/prod/Caddyfile`**: add a `header` block to all three site blocks —
   the three headers above at the edge (covers the API origin, which Next can't) plus
   `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'` on the two app
   hosts (defense against same-registrable-domain framing; the API host gets the frame headers too —
   nothing legitimate frames JSON).
   This is a PROPOSED prod change per 6R-04's sync discipline: committed now, applied to the box +
   VERIFY'd in the next ops sitting; the task's live evidence is LOCAL (next start), not the prod box.
3. API app: no change (Caddy fronts it in prod; adding header middleware in FastAPI would duplicate
   the edge and touch factory.py for no local benefit). Record the reasoning.

## Test-author scope

- Frontend: one test per app asserting the exported `headers()` config contains exactly the pinned
  header set (unit-level; the live check is the implementer's acceptance evidence).
- Extend `apps/api/tests/test_prod_config_pins.py`? NO — new file `test_prod_config_headers.py`
  pinning the Caddyfile header directives (same skip-if-absent pattern), so 6R-04's pinned file
  stays byte-stable.

## Acceptance

`pnpm gates:admin` / `gates:client` green + `pnpm build` both apps; **live evidence**: `next start`
each app locally and `curl -sI` shows the three headers on `/`; api suite green env-exported;
path-scoped adds only (`apps/admin/next.config.ts`, `apps/client/next.config.ts`, the two new test
files, `infra/deploy/prod/Caddyfile`); owner-pending files untouchable.
