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
