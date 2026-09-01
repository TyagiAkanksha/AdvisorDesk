# Task 6R-01 — Root gate scripts, git hooks, coverage-artifact hygiene

WR-ids: WR-16 (root-orchestration limb), WR-74. Effort S. Everything here is locally verifiable.

## Goal

One source of truth for the gate commands (today they exist as three independently-typed lists in
README.md §Gates and CONVENTIONS.md §10), consumable by humans, the future CI workflow (task-02),
and a pre-commit hook.

## Files

1. **`package.json` (root)** — add a `"scripts"` block (currently absent; file has only
   name/version/private/packageManager). Exact scripts:
   - `"gates:api"`: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
   - `"gates:admin"`: `pnpm -C apps/admin lint && pnpm -C apps/admin type-check && pnpm -C apps/admin format:check && pnpm -C apps/admin test`
   - `"gates:client"`: same as gates:admin with `apps/client`
   - `"gates"`: `pnpm gates:api && pnpm gates:admin && pnpm gates:client`
   Note: `gates:api`'s pytest leg needs `TEST_DATABASE_URL` exported by the caller (unset ⇒ DB tests
   skip by design); do NOT bake the URL into the script.
2. **`lefthook.yml` (root, new)** + `lefthook` as a root devDependency (pinned) — pre-commit only,
   convenience not enforcement (CI in task-02 is the backstop).
   > **AMENDED 2026-08-31 (controller, after implementer NEEDS_CONTEXT):** the original literal YAML
   > here was defective — gobwas-glob `apps/api/**/*.py` cannot match direct children of `apps/api/`,
   > and `cd apps/api && … {staged_files}` double-prefixes repo-root-relative paths. The spec is now
   > REQUIREMENT-DRIVEN; use lefthook's `root:` key per command (which chdirs and re-roots
   > `{staged_files}`) or whatever shape empirically satisfies ALL of:
   > (a) a staged `.py` directly under `apps/api/` AND one nested (e.g. `apps/api/app/x.py`) both
   >     trigger ruff `check --fix` + `format` and get re-staged (`stage_fixed: true`);
   > (b) a staged `.ts`/`.tsx` anywhere under each frontend app triggers that app's own prettier
   >     (`--write`) and is re-staged;
   > (c) non-matching files (e.g. `.md`) trigger nothing.
   > Prove (a)–(c) empirically with scratch probe files, then remove every probe (never committed).
   - Add a `"prepare": "lefthook install"` root script so the hook self-installs on `pnpm install`.
   - **Also authorized:** add `lefthook: false` to `pnpm-workspace.yaml`'s existing `allowBuilds`
     denial block with a one-line rationale comment (hook install is handled explicitly by the
     `prepare` script; postinstall not needed) — silences `ERR_PNPM_IGNORED_BUILDS` consistently
     with the repo's existing supply-chain convention. `pnpm-workspace.yaml` joins the path-scoped
     `git add` list in Constraints.
   - Ratified implementer judgment calls: `--no-frozen-lockfile` install (TTY prompt workaround),
     reverting pnpm's unrelated auto-edit, pinning lefthook `2.1.12`.
3. **`.gitignore` (root)** — add `.coverage`, `.coverage.*`, `htmlcov/` (a stray `apps/api/.coverage`
   from the review's baseline run currently sits untracked; after the gitignore change confirm
   `git status` no longer lists it — do not delete it).
4. **`README.md` — DO NOT EDIT.** It is dirty with an owner-pending docs pass. Record in your report
   that README's gate section should later point at `pnpm gates` (fold into task-02's reviewer notes
   or the docs task); leave the file untouched.

## Constraints

- Path-scoped `git add` of exactly: root `package.json`, `pnpm-lock.yaml` (lefthook dep), `lefthook.yml`, `.gitignore`. Nothing else. The 11 dirty files + untracked `infra/deploy/ec2-single-host.md` are owner-pending — touching them is a task failure.
- Commit message: `chore(repo): root gate scripts + lefthook + coverage gitignore (6R-01, WR-16/WR-74)`.

## Acceptance (run and capture verbatim)

1. `export "$(grep '^TEST_DATABASE_URL=' .env | tr -d '\r')" && pnpm gates:api` → all five gates run, exits 0 (test DB container `advisordesk-test-db` on :5433 must be running — `docker start advisordesk-test-db` if not).
2. `pnpm gates:admin` and `pnpm gates:client` → exit 0.
3. `pnpm lefthook run pre-commit` on a scratch staged change (make a whitespace edit to a COPY under /tmp? No — instead: stage a temporary trivially-reformattable change to a NEW scratch file `apps/api/scratch_lefthook_probe.py`, verify the hook formats it, then `git reset` and delete the probe file; probe must never be committed).
4. `git status --short` afterwards shows exactly the original 11 dirty files + 1 untracked doc (probe gone, `.coverage` no longer listed).
