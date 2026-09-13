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
   - For a release that ships a new Alembic migration: bumping the `api` image tag in
     `docker-compose.yml` (the compose-file edit — see "Image tags" below) is what selects the new
     image; `docker compose up -d` only recreates the container from whatever tag is already in
     the file. `docker compose exec api …` therefore runs INSIDE the still-running OLD container —
     its image has no new migration yet, so `alembic upgrade head` there resolves to the schema
     already applied and silently no-ops. Run the migration from the NEW image instead, in a
     one-off container that doesn't touch the running service, **before** `docker compose up -d`:
     `docker compose pull api && docker compose run --rm api uv run alembic upgrade head` (the
     form `infra/Dockerfile.api:8` documents; the prod `api` service has no `depends_on`, so
     nothing else starts). A **fresh** deploy or upgrade to this release must run the same
     `pull`/`run --rm` command — there is no running `api` container to `exec` into yet, so this
     form covers both cases (`exec` would either no-op against the old image or error outright
     against no container). Migrations are **not** run automatically by the api container's start
     command (`database.md`'s own top-of-file note: "Do this BEFORE bringing the API up") — the
     equivalent alternative, from a local checkout with network access to the DB, is
     `database.md:38-41`'s form (`cd apps/api && DATABASE_URL=… uv run alembic upgrade head`),
     which needs no running container at all. Either way, migrating first avoids a window where a
     NEW image is live against the OLD schema and 500s on every route that touches the missing
     tables/columns — including, for this specific migration, the existing CLI-minted MCP
     bearer-token path (see the "MCP OAuth Connect" section below).
   - **The order flips for a DESTRUCTIVE migration** (one that drops or renames a column/table —
     first instance: `0008_drop_oauth_consents_revoked_at`, 2026-09-11). Migrating first would
     leave the OLD image live against a schema missing a column it still `SELECT`s/`INSERT`s
     (`UndefinedColumn` 500s until `up -d`). The new image must be forward-compatible with the
     old schema (it simply ignores the extra column), so: `docker compose pull api && docker
     compose up -d` FIRST, confirm healthy, THEN `docker compose run --rm api uv run alembic
     upgrade head`. Additive migrations keep the migrate-first order above. A migration that is
     both (adds AND drops) must be split into two releases.
3. Re-run the relevant checks in `../VERIFY.md` against the live deployment. For any release
   that touches the api image, also record `docker compose exec -T api uv run alembic current`
   before and after — the 2026-09-08 mcp-oauth deploy found prod still at `0004` (migrations
   `0005`/`0006` had never been applied by the two earlier deploys) and walked it to `0007` in
   one go; see the deploy-session note at the end of `../VERIFY.md` §5a.
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
  `LLM_PROVIDER=openai`, `LLM_BASE_URL=https://api.openai.com/v1`, `EMBEDDING_DIMENSIONS="1024"`,
  `SIMILARITY_THRESHOLD="0.5"`; `fetch-secrets.sh` fetches
  `OPENAI_API_KEY` from SSM. Both NVIDIA NIM models (embedding + chat) reached end-of-life in
  August 2026; `NVIDIA_API_KEY` is fetched only for back-compat and unused while
  `LLM_PROVIDER=openai`. The model NAMES (`CHAT_MODEL`, `EMBEDDING_MODEL`, `JUDGE_MODEL`) are
  deliberately NOT set in the compose file since the phase-9 deploy (`ca4e634`, 2026-09-13): the
  code defaults apply (`gpt-5.4-mini` / `text-embedding-3-small` / `gpt-5.4`), and
  `tests/test_prod_config_pins.py` fails if a pin reappears in `environment:`.

## Staged follow-up (NOT applied in this task)

The following are pre-agreed next box-sync items from the phase-6 remediation plan, and remain
genuinely pending. They apply to the box first (a controller+owner ops session), then this
committed copy is updated in the same sitting:

- **Log rotation** (WR-70) — add
  `logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}` to each service in
  `docker-compose.yml`. Check `docker-compose.yml` directly for current status — this is being
  worked concurrently with this doc pass; the fix isn't considered done until every service (not
  just an unused anchor) actually references the logging config on the box.
- **`FORWARDED_ALLOW_IPS=*` → docker bridge range** (WR-03 residual) — defense-in-depth so
  uvicorn's own trusted-proxy walk still means something even if the Caddy `header_up` line is
  ever dropped. **Applied 2026-09-11 (desktop closeout):** `docker-compose.yml`'s `api` service
  now sets `FORWARDED_ALLOW_IPS: "172.16.0.0/12"` — the whole RFC 1918 block Docker draws
  bridge subnets from, because the compose network's subnet is not pinned (it was
  `172.18.0.0/16` that day) and a stale /16 would fail silently (every visitor in one
  rate-limit bucket). Verified at apply time by `../VERIFY.md` check 2b (spoof, recorded) and
  the single-IP form of check 2 (the api access log shows the real client IP, not Caddy's
  bridge address, after the change — recorded there).

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
   dependent authorization code/refresh/access token row. Note: "Approved" is `consent_granted_at`
   — the first time an admin approved that client. Revoking deletes the client and cascades every
   dependent row (consent included), so a later reconnect arrives as a **new** client with a new
   `client_id` and a new Approved date. `POST /oauth/revoke` (RFC 7009) is different: it kills
   tokens but leaves the consent standing, so that client can re-authorize without a new consent
   prompt.
3. **CLI mint fallback:** for ops/CI callers that can't drive an OAuth redirect, the pre-existing
   `scripts/mint_mcp_token.py --mint` CLI still works exactly as before — see
   `env-checklist.md`'s "MCP bearer-token note" for the exact command and its `OAUTH_ISSUER_URL`
   requirement.
4. **Migration:** the four new OAuth tables (Alembic migration `0007`) are **not** created by any
   automatic step at container start — see the "Change procedure" step 2 sub-bullet above, which
   pins both the order and the command: bump the `api` tag in `docker-compose.yml` first (the
   compose-file edit is what selects the new image — `docker compose up -d` merely recreates the
   container from whatever tag is already in the file), then run
   `docker compose pull api && docker compose run --rm api uv run alembic upgrade head` — a
   one-off container from the NEW image, **before** `docker compose up -d` — never
   `docker compose exec api …`, which runs inside the still-running OLD container and silently
   no-ops (its image has no `0007` to resolve against). Getting the order backwards is not just an
   `/oauth/*` or `/.well-known/*` problem — the NEW image's `resolve_bearer_token`
   (`app/auth/tokens.py`) selects `api_tokens.client_id`, `.resource`, and `.last_used_at`, columns
   migration `0007` adds, so **every** request that resolves a bearer token 500s against the
   missing columns, including the pre-existing, currently-working CLI-minted connector path
   (`scripts/mint_mcp_token.py`) — not only the new OAuth surface.
