# Production config — synced copies (doc of record)

**Source of truth is the box**, `/opt/advisordesk/` on the deployed EC2 instance — not this
directory. The three files here (`docker-compose.yml`, `Caddyfile`, `fetch-secrets.sh`) are
committed, byte-identical copies of what actually runs, so the production configuration is
reviewable, diffable, and greppable from the repo instead of asserted-only (WR-03), and so the
disaster-recovery runbook has something concrete to restore from (WR-14). They are not applied
from here automatically — nothing reads this directory at deploy time.

## Change procedure

1. Edit the file **here**, in the repo, and get the change reviewed like any other commit.
2. Apply it to the box via SSM (`ec2-single-host.md` has the session command) — copy the file to
   `/opt/advisordesk/` and re-run/restart whatever the change requires
   (`docker compose up -d` for compose changes, `docker compose restart caddy` for `Caddyfile`
   changes).
   - For a release that ships a new Alembic migration, also run
     `docker compose exec api uv run alembic upgrade head` — migrations are **not** run
     automatically by the api container's start command (`database.md`'s own top-of-file note),
     so `docker compose up -d` alone leaves new tables/columns missing and the API will 500 on
     any route that touches them.
3. Re-run the relevant checks in `../VERIFY.md` against the live deployment.
4. If applying the change on the box surfaced any drift from what's committed here (a manual
   fix made directly on the box, a value that had to differ), commit that drift back in the same
   sitting — docs must equal reality.

`fetch-secrets.sh` runs **on the box only** (it uses the instance's IAM role to decrypt SSM
`SecureString` parameters); it is not meant to be run from a workstation.

## Image tags

The `api`/`admin`/`client` image tags in `docker-compose.yml` are pinned to the deployed git SHA,
not a moving tag like `latest`. Each redeploy pushes new images tagged with the new SHA
(`../push_ecr.sh`) and updates the tag in this file (both the box's copy and this committed copy)
to match — so at any point in time this file names exactly what's running.

## Already shipped (for the record — no longer pending)

- **Security headers** (WR-04, 6R-05) — DONE. The Caddy `header` directive block
  (`Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options:
  DENY`, `Content-Security-Policy: frame-ancestors 'none'`) is live on all three vhosts in
  `Caddyfile` today; task-05 (`task-05-security-headers.md`) shipped and was reviewed APPROVED.
  This item previously lingered in the "Staged follow-up" list below after it had already
  shipped — removed from there as of this pass (p7 review finding M-1).
- **OpenAI provider switch** (6R-14) — DONE. `docker-compose.yml`'s `api` service sets
  `LLM_PROVIDER=openai`, `LLM_BASE_URL=https://api.openai.com/v1`,
  `EMBEDDING_MODEL=text-embedding-3-small`, `EMBEDDING_DIMENSIONS="1024"`,
  `CHAT_MODEL=gpt-4o-mini`, `SIMILARITY_THRESHOLD="0.5"`; `fetch-secrets.sh` fetches
  `OPENAI_API_KEY` from SSM. Both NVIDIA NIM models (embedding + chat) reached end-of-life in
  August 2026; `NVIDIA_API_KEY` is fetched only for back-compat and unused while
  `LLM_PROVIDER=openai`.

## Staged follow-up (NOT applied in this task)

The following are pre-agreed next box-sync items from the phase-6 remediation plan, and remain
genuinely pending. They apply to the box first (a controller+owner ops session), then this
committed copy is updated in the same sitting:

- **Log rotation** (WR-70) — add
  `logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}` to each service in
  `docker-compose.yml`. Check `docker-compose.yml` directly for current status — this is being
  worked concurrently with this doc pass; the fix isn't considered done until every service (not
  just an unused anchor) actually references the logging config on the box.
- **`FORWARDED_ALLOW_IPS=*` → docker bridge subnet** (WR-03 residual) — defense-in-depth so
  uvicorn's own trusted-proxy walk still means something even if the Caddy `header_up` line is
  ever dropped. Not yet applied — `docker-compose.yml`'s `api` service still sets
  `FORWARDED_ALLOW_IPS: "*"`. This changes production request-trust behavior, so it **must be
  verified against a live spoof test (`../VERIFY.md` check 2b) at apply time**, before it's
  considered done.

## MCP OAuth Connect (mcp-oauth)

`docker-compose.yml`'s `api` service now sets `OAUTH_ISSUER_URL=https://api.advisordesk.tyagiakanksha.com`
(mcp-oauth plan, `docs/plans/mcp-oauth/DESIGN.md`) — the API co-hosts an OAuth 2.1 authorization
server alongside the MCP resource server so claude.ai's remote-connector **Connect** button works
against `https://api.advisordesk.tyagiakanksha.com/api/v1/mcp` directly, replacing the manual
CLI-mint-and-paste flow as the primary path.

1. **Connect from claude.ai:** Settings → Connectors → Add custom connector → URL
   `https://api.advisordesk.tyagiakanksha.com/api/v1/mcp` → Connect. claude.ai discovers the
   `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`
   documents, registers itself via DCR, then bridges to Google sign-in — sign in with an
   allowlisted admin email (`ADMIN_EMAILS`) — and approve the consent screen ("Claude wants MCP
   access to AdvisorDesk"). Claude receives a rotating access/refresh token pair; no token is ever
   pasted into the connector config for this path.
2. **Admin app → Connected apps** lists every registered client (name, admin, issued, last used,
   live token counts) with a **Revoke** action that deletes the client and cascades every
   dependent authorization code/refresh/access token row. Note: the table's "Approved" column is
   `consent_granted_at` — the FIRST time an admin approved that client's consent — not a
   last-approved timestamp; revoking a client and re-approving it later revives the same consent
   record, so "Approved" keeps showing the original grant date, not the date of the re-approval.
3. **CLI mint fallback:** for ops/CI callers that can't drive an OAuth redirect, the pre-existing
   `scripts/mint_mcp_token.py --mint` CLI still works exactly as before — see
   `env-checklist.md`'s "MCP bearer-token note" for the exact command and its `OAUTH_ISSUER_URL`
   requirement.
4. **Migration:** the four new OAuth tables (Alembic migration `0007`) are **not** created by any
   automatic step at container start — see the "Change procedure" step 2 sub-bullet above. A fresh
   deploy or upgrade to this release must run
   `docker compose exec api uv run alembic upgrade head` before `/oauth/*` or `/.well-known/*`
   traffic is sent to the box, or every OAuth route 500s against the missing tables.
