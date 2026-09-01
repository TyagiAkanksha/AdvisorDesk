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

## Staged follow-up (NOT applied in this task)

The following are pre-agreed next box-sync items from the phase-6 remediation plan. They apply to
the box first (a controller+owner ops session), then this committed copy is updated in the same
sitting:

- **Log rotation** (WR-70) — add
  `logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}` to each service in
  `docker-compose.yml`.
- **`FORWARDED_ALLOW_IPS=*` → docker bridge subnet** (WR-03 residual) — defense-in-depth so
  uvicorn's own trusted-proxy walk still means something even if the Caddy `header_up` line is
  ever dropped. This changes production request-trust behavior, so it **must be verified against
  a live spoof test (`../VERIFY.md` check 2b) at apply time**, before it's considered done.
- **Security headers** — a Caddy `header` directive addition (`X-Frame-Options: DENY` /
  `frame-ancestors 'none'`, alongside the frontends' own `next.config.ts` headers). Arrives with
  task-05.
