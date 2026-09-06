# Task 6R-02 — CI workflow, dependency scanning, permanent coverage gate

WR-ids: WR-16 (centerpiece), WR-17, WR-50, WR-51, WR-52. Effort M. Depends on task-01 (calls its scripts).

## Goal

`.github/workflows/ci.yml` running the exact existing gates on every push/PR, plus Dependabot,
audit steps, a coverage threshold, a mass-skip guard, and a codegen-drift check. CI is the forcing
function the whole remediation plan sequences around.

## Files

1. **`.github/workflows/ci.yml`** (new):
   - Triggers: `push` (branches `v1`, `feat/**`) and `pull_request` (base `v1`).
   - **Job `api`** (ubuntu-latest):
     - `services: postgres:` image `pgvector/pgvector:pg16`, env `POSTGRES_PASSWORD: postgres`,
       `POSTGRES_DB: advisordesk_test`, port mapping 5432, `pg_isready` health-cmd with retries.
     - Steps: checkout → `astral-sh/setup-uv` (pin the current major; pin a Python 3.12 toolchain) →
       job-level `env: TEST_DATABASE_URL: postgresql+psycopg://postgres:postgres@localhost:5432/advisordesk_test`
       (verify the driver prefix against what `apps/api/.env.example`/`app/config.py` expect before assuming) →
       run the five api gates. Prefer invoking the five `uv run …` commands as explicit separate steps
       (one step per gate, named) rather than `pnpm gates:api`, so CI failures pinpoint the gate; the
       command TEXT must match task-01's scripts verbatim.
     - Coverage (WR-50): add `pytest-cov` to `apps/api` dev dependencies via `uv add --dev pytest-cov`
       (lockfile change is intended and committed). The pytest gate step becomes
       `uv run pytest -q --cov=app --cov-fail-under=95` in CI ONLY if that does not force local runs to
       need pytest-cov flags — simplest compliant shape: keep `uv run pytest -q` as the gate step and add a
       separate `coverage` step running `uv run pytest -q --cov=app --cov-fail-under=95`. Choose one,
       document why in the report.
     - Mass-skip guard (WR-51): new file `apps/api/tests/test_ci_guard.py` — a single test that FAILS
       when `TEST_DATABASE_URL` is unset (message: "CI must provide a database; 28 DB test files would
       silently skip"), guarded so it only asserts when env var `CI=true` (GitHub sets it). Locally
       without the var it passes/skips harmlessly. This is the one pytest-able piece of this task —
       write it first, prove it RED by running with `CI=true` and `TEST_DATABASE_URL` unset (expect 1
       failed), then GREEN with both set. Keep it ruff/format-clean.
   - **Job `web`** (matrix `app: [admin, client]`): checkout → `corepack enable` (pnpm version comes
     from root `packageManager` field) → `pnpm install --frozen-lockfile` → the four gates
     (`lint`, `type-check`, `format:check`, `test`) + `build` as a fifth step.
   - **Codegen drift (WR-52)**, inside job `web`: `pnpm -C apps/${{ matrix.app }} codegen && git diff --exit-code -- apps/${{ matrix.app }}/src/types/generated` (codegen reads the committed `apps/api/openapi.json` — no API server needed; verify that claim against the codegen script before relying on it).
   - **Audit steps (WR-17)**: in `api` job, `uvx pip-audit` against `apps/api` (resolve how pip-audit consumes a uv project — `uv export --format requirements-txt | uvx pip-audit -r /dev/stdin` is the known-good shape; verify); in `web` job (or a third job once, not per-matrix), `pnpm audit --audit-level=high`. Both `continue-on-error: true` with a `# tighten after baseline triage` comment.
2. **`.github/dependabot.yml`** (new): weekly; `package-ecosystem: npm` at `/` (covers the pnpm workspace); `package-ecosystem: uv` at `/apps/api` — CHECK whether the runner supports `uv` (supported since 2025); if generation fails validation, fall back to `pip` and note it.
3. Commit split: (a) `test(api): CI mass-skip guard RED evidence (6R-02, WR-51)` if you follow the
   RED/GREEN split, else one commit; (b) `feat(ci): gates workflow + dependabot + audits + coverage gate (6R-02, WR-16/17/50/51/52)`.
   Path-scoped `git add` of exactly: `.github/**`, `apps/api/tests/test_ci_guard.py`, `apps/api/pyproject.toml`, `apps/api/uv.lock`. The 11 dirty files + untracked `infra/deploy/ec2-single-host.md` are owner-pending — do not touch.

## Constraints

- No live run is possible (branch never pushed; repo remote exists — do NOT push; owner pushes later).
  The workflow therefore gets desk-verification only; be explicit in the report about what remains
  unverified until first push.
- `actionlint` if available (`command -v actionlint`, or `uvx`/`npx` equivalents — do not install
  system packages); otherwise YAML-parse both files (`python -c "import yaml,sys; yaml.safe_load(open(...))"`
  via the api venv) and say which check ran.
- The five api gate commands and four web gate commands must match README.md §Gates verbatim — CI that
  drifts from the documented gates is a task failure.

## Acceptance (capture verbatim)

1. Mass-skip guard: `CI=true uv run pytest tests/test_ci_guard.py -q` with `TEST_DATABASE_URL` unset → 1 failed (RED); with it exported → passes (GREEN). Full suite locally (env exported) still 454 passed incl. the new test, and — critically — WITHOUT `CI` set and WITHOUT `TEST_DATABASE_URL` the suite still behaves as before (skips, exit 0).
2. actionlint or YAML-parse clean on both `.github` files.
3. `uv run ruff check .` / `format --check` / `mypy` clean after the pyproject change (mypy scope is `files=["app"]`, unaffected — confirm).
4. Coverage step command runs green locally: `uv run pytest -q --cov=app --cov-fail-under=95` (baseline is 97%).
5. `git status --short` shows exactly the original 11 dirty + 1 untracked owner-pending files.
