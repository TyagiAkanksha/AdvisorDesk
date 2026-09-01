# Task 6R-04 — Production compose + Caddyfile into the repo (doc of record)

WR-ids: WR-03 (version-control limb), WR-14 (restore-target limb), WR-70 (log rotation, staged).
Effort S-M. Author → reviewer (config/docs task; no test-author — 6R-01/02 precedent), EXCEPT one
gates-as-test which follows normal rules.

## Context

The controller fetched the three files from the box 2026-08-31 via SSM (read-only), secret-scanned
clean: scratchpad file `box-config-fetch.txt` (path in the dispatch). The Caddyfile's
`header_up X-Forwarded-For {remote_host}` line — the load-bearing spoof-proofing control — is
confirmed present.

## Steps

1. **New dir `infra/deploy/prod/`** with three files, VERBATIM as fetched (they are the doc of
   record for what runs; do not "improve" them in this commit):
   - `docker-compose.yml` (the box's prod compose)
   - `Caddyfile`
   - `fetch-secrets.sh` (mode 755)
   Plus a short `README.md` in that dir: source of truth = the box at `/opt/advisordesk/`; these are
   synced copies; change procedure = edit here → apply to box via SSM → re-run VERIFY checks → commit
   any drift back. Note the image tags are pinned to the deployed git SHA and updated at each redeploy.
2. **Gates-as-test** (new file `apps/api/tests/test_prod_config_pins.py`): asserts the committed
   `infra/deploy/prod/Caddyfile` contains `header_up X-Forwarded-For {remote_host}` for the api
   host block, and the committed prod compose does NOT publish the api port to the host (`expose`
   only, no `ports:` on the api service) — the two facts `FORWARDED_ALLOW_IPS=*` safety rests on
   (WR-03). Skip cleanly (with reason) if the files are absent so the suite stays runnable on
   checkouts predating this task. Ruff/format-clean; runs without DB.
3. **Staged (do NOT apply in this task): follow-up change set** recorded at the bottom of the new
   README as the next box-sync items, each pre-agreed from the remediation plan:
   - log-rotation options per service (`logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}`) — WR-70
   - `FORWARDED_ALLOW_IPS=*` → docker bridge subnet (defense-in-depth; MUST be verified with a live
     VERIFY.md check-2b spoof test at apply time) — WR-03 residual
   - security `header` directive additions — arrives with task-05
   These apply to the box first (controller+owner ops session), then the committed copies update in
   the same sitting (docs==reality discipline).

## Constraints

Path-scoped adds: `infra/deploy/prod/**`, `apps/api/tests/test_prod_config_pins.py`. The 11 dirty
owner-pending files + untracked `infra/deploy/ec2-single-host.md` are untouchable (the
cross-reference from ec2-single-host.md to this new dir is added later, after the owner commits
their docs pass). Commit: `feat(infra): prod compose + Caddyfile as doc of record + config pins (6R-04, WR-03/14/70)`.

## Acceptance

Committed files byte-identical to the fetched originals (diff against the scratchpad fetch, ignoring
the fetch markers); new test green in the full suite (env-exported) AND green standalone without
TEST_DATABASE_URL; five api gates clean; `git status` afterwards shows only the owner-pending set.
