# mcp-oauth task-10 — Verification record

**Scope:** this record documents the **local verification pass** for the whole `mcp-oauth`
branch (tasks 01–10, `feat/mcp-oauth`) — a full gate run, the narrative end-to-end test's 12
steps, and a real alembic round-trip on the test database. Merge, push, deploy, and the real
claude.ai Connect against the deployed API were **owner-gated and NOT performed** as part of
task 10 — see §4 below. They were performed afterwards, on 2026-09-08; the live outcome is
recorded in §5.

Base commit: `14b5af9` (mcp-oauth task 09 status built) plus this task's own working-tree edits
(config/doc edits + the e2e test file), committed together as this record's own commit. Run date:
2026-09-08.

**Final review fix wave (this section, 2026-09-08):** the whole-branch Opus review
(`.superpowers/sdd/mcp-oauth/task-10-review.md`, verdict "Ready to merge — With fixes") named one
fix wave of ten items (six code, four documentation; everything else DEFERRED or DROPPED per the
review's own triage). All ten landed in two commits on top of task 10's own commit `f365fcf`:
`70b9691` (code + tests — F-10/P7, P13, F-12, F-14, F-13, F-5) and the doc-only commit this
record's own update is part of (F-1/A-I1, F-4-doc, F-2+F-24, F-3, this refreshed §1). The counts
below are the REAL gate output re-run after `70b9691` landed, not carried over from task 10's
original pass.

---

## 1. Full gate run (real, this pass — 2026-09-08, after the final fix wave's code commit `70b9691`)

### `apps/api`

```
$ cd apps/api
$ export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' ../../.env | cut -d= -f2-)"

$ uv run ruff check --no-cache .
All checks passed!

$ uv run ruff format --check .
195 files already formatted

$ uv run mypy
Success: no issues found in 82 source files

$ uv run lint-imports
---------
Contracts
---------

Analyzed 82 files, 229 dependencies.
------------------------------------

app.models is a pure leaf KEPT
app.services imports only app.models and app.config KEPT
app.auth imports only app.services, app.models, and app.config KEPT
app.rag imports only app.services, app.models, and app.config KEPT
app.agent imports only app.mcp, app.services, app.models, and app.config KEPT
app.mcp never imports app.routes, app.agent, or app.db KEPT
app.routes never imports app.mcp or app.db directly KEPT
nothing imports app.main; only app.main imports app.factory KEPT

Contracts: 8 kept, 0 broken.

$ uv run pytest -q -p no:cacheprovider --cov=app --cov-fail-under=95
738 passed, 1 skipped in 188.30s (0:03:08)
Required test coverage of 95% reached. Total coverage: 96.50%
```

**Result: PASS** (ruff check, ruff format, mypy 0 issues across 82 source files, lint-imports
8/8 contracts kept, pytest **738 passed / 1 skipped** (+5 over task 10's `733`: one new test each
for P13's revoke-audit line, P13's admin-delete-audit line, F-12's deleted-mid-consent 400,
F-14's doubled-trailing-slash case, and F-13's control-character/whitespace redirect-URI case;
F-10/P7 extended an existing assertion rather than adding a new test), coverage **96.50%** — mypy
excludes `tests/`).

### Wire gate — OpenAPI/codegen drift

```
$ cd apps/api && uv run python scripts/export_openapi.py
$ pnpm -C apps/admin codegen && pnpm -C apps/client codegen
$ git status --short
 M apps/admin/src/components/connectedApps/ConnectedAppsScreen/useConnectedApps.ts
 M apps/api/app/config.py
 M apps/api/app/routes/oauth_admin_routes.py
 M apps/api/app/routes/oauth_routes.py
 M apps/api/app/routes/ratelimit.py
 M apps/api/app/services/oauth_clients.py
 M apps/api/tests/test_oauth_consent.py
 M apps/api/tests/test_oauth_register.py
 M apps/api/tests/test_oauth_revoke_admin.py
 M apps/api/tests/test_oauth_settings.py
```

(Captured right after the fix wave's code edits, before commit `70b9691` — the list is exactly the
ten files that commit contains.) **Result: PASS (no drift).** `apps/api/openapi.json` and both
generated `schema.d.ts` files (admin + client) do not appear in the status output — none of the
six fix-wave code items touch a route signature, request/response schema, or operation id (they
change response headers, log lines, a validator's normalisation, a guard clause, and dead
frontend state), so both codegens reproduced byte-identical output.

### `apps/admin` (via `pnpm gates`)

```
$ pnpm gates
...
$ pnpm -C apps/admin lint && pnpm -C apps/admin type-check && pnpm -C apps/admin format:check && pnpm -C apps/admin test
$ eslint .        -> clean
$ tsc --noEmit    -> clean
$ prettier --check . -> All matched files use Prettier code style!
$ vitest run
 Test Files  38 passed (38)
      Tests  127 passed (127)
```

**Result: PASS** (lint clean, type-check clean, format clean, **38 test files / 127 tests
passed** — matches the expected count exactly).

### `apps/client` (via `pnpm gates`)

```
$ pnpm -C apps/client lint && pnpm -C apps/client type-check && pnpm -C apps/client format:check && pnpm -C apps/client test
$ eslint .        -> clean
$ tsc --noEmit    -> clean
$ prettier --check . -> All matched files use Prettier code style!
$ vitest run
 Test Files  14 passed (14)
      Tests  58 passed (58)
```

**Result: PASS** (lint clean, type-check clean, format clean, 14 test files / 58 tests passed).

### `apps/api` via `pnpm gates:api` (no `TEST_DATABASE_URL` exported by the script itself)

```
$ pnpm gates:api
... 252 passed, 487 skipped in 5.80s ...
```

This is the same `uv run pytest -q` invocation the root `package.json` chains ahead of
`gates:admin`/`gates:client`; without `TEST_DATABASE_URL` exported in that shell, every
DB-backed test is skipped. Of the fix wave's 5 new tests, 4 request `tmp_engine`/`db_session`
(P13's two, F-12's one, F-13's one) and skip here, while F-14's
`test_issuer_doubled_trailing_slash_stripped` is a pure `Settings()` unit test with no DB fixture
and runs regardless — accounting for the move from task 10's `483 skipped`/`251 passed` to this
pass's `487 skipped`/`252 passed` (+4 / +1 = the same 5 new tests). The chain completing and
falling through to `gates:admin`/`gates:client` confirms ruff/mypy/lint-imports passed here too,
consistent with the explicit-env run above. The authoritative, full-coverage pytest run is the one
in the `apps/api` section above (738 passed / 1 skipped, 96.50% coverage, `TEST_DATABASE_URL`
exported explicitly in the same command).

### Gate summary

| Gate | Result |
|---|---|
| `apps/api` ruff check --no-cache | PASS |
| `apps/api` ruff format --check | PASS |
| `apps/api` mypy | PASS (0 issues, 82 source files) |
| `apps/api` lint-imports | PASS (8/8 contracts kept) |
| `apps/api` pytest (`--cov=app --cov-fail-under=95`) | PASS (738 passed, 1 skipped, **96.50%** coverage) |
| OpenAPI/codegen drift (`export_openapi.py` + both codegens + `git status`) | PASS (no diff) |
| `apps/admin` lint / type-check / format / test | PASS (38 files / 127 tests) |
| `apps/client` lint / type-check / format / test | PASS (14 files / 58 tests) |

**All gates green. No fudging, no skipped gate.**

---

## 2. Narrative end-to-end test — 12 steps ticked

File: `apps/api/tests/test_oauth_e2e_flow.py`. Test names: `test_full_connect_lifecycle` (the
narrative), `test_openapi_lists_every_oauth_operation`, `test_create_app_without_db_registers_oauth_routes`.
Written by a separate test-author (`.superpowers/sdd/mcp-oauth/task-10-testauthor-report.md`);
GREEN on first run against the built t01–t09 branch — the plan's own stated acceptance proof, not
a defect. Re-verified GREEN in this task's full-suite run above (738 passed includes these 3).

| # | Step | Covered by |
|---|---|---|
| 1 | `POST /api/v1/mcp` no auth → 401 + exact `WWW-Authenticate: Bearer resource_metadata="…"` | `test_full_connect_lifecycle`, lines 210–217 |
| 2 | `GET /.well-known/oauth-protected-resource` → `authorization_servers == ["https://api.example"]` | `test_full_connect_lifecycle`, lines 219–225 |
| 3 | `GET /.well-known/oauth-authorization-server` → parses `registration_endpoint`, `authorization_endpoint`, `token_endpoint`, `revocation_endpoint`; every later call uses the parsed path, not a literal | `test_full_connect_lifecycle`, lines 227–237 |
| 4 | `POST <registration_endpoint>` (DCR) → 201, `client_id` captured | `test_full_connect_lifecycle`, lines 239–244 |
| 5 | Authorize → 303; continue w/o session → 307 login; `login_as`; continue → 200 HTML consent; approve → 302 with `code`+`state` | `test_full_connect_lifecycle`, lines 246–277 |
| 6 | Token exchange via `token_endpoint` → access (`adk_…`) + refresh (`adkr_…`) | `test_full_connect_lifecycle`, lines 279–296 |
| 7 | `POST /api/v1/mcp tools/list` with access token → 200, exactly the 9 registered tools | `test_full_connect_lifecycle`, lines 298–303 |
| 8 | Refresh → new pair; old access token → 401; new access token → `tools/list` 200 | `test_full_connect_lifecycle`, lines 305–324 |
| 9 | Second authorize, same client → continue → 302 directly (consent remembered, no HTML hop) | `test_full_connect_lifecycle`, lines 326–342 |
| 10 | Admin `GET /api/v1/oauth/clients` (cookie) → one item, `active_access_tokens == 1`, `active_refresh_tokens == 1`, `last_used_at` not `None` | `test_full_connect_lifecycle`, lines 344–356 |
| 11 | Admin `DELETE /api/v1/oauth/clients/{client_id}` → 204; access token → 401 w/ `WWW-Authenticate`; refresh at `token_endpoint` → 401 `invalid_client` | `test_full_connect_lifecycle`, lines 358–377 |
| 12 | `POST /api/v1/mcp` with a CLI-style token (`ApiToken(client_id=None, resource=None)`) → still 200 (fallback path intact) | `test_full_connect_lifecycle`, lines 379–397 |

Additional coverage (not part of the 12-step narrative but required by the brief):

- `test_openapi_lists_every_oauth_operation` — all 11 OAuth operation ids present in `/openapi.json`
  on a DB-backed app.
- `test_create_app_without_db_registers_oauth_routes` — `create_app()` with no arguments still
  registers every OAuth route (DCR, authorize, admin list/revoke), per CONVENTIONS §5's
  no-DB-no-env-vars startup requirement.

---

## 3. Alembic round-trip on the TEST database

Run by the SDD controller (not by this task's implementer — this task never ran ad-hoc SQL or
alembic commands itself) in a fresh scratch schema, the same path `tests/conftest.py::tmp_engine`
uses (`MIGRATE_SCHEMA=sdd_t10_roundtrip`), against the **test** database. No connection string is
recorded anywhere in this repo or this record. Evidence file:
`.superpowers/sdd/mcp-oauth/task-10-alembic-roundtrip.txt` (gitignored working notes).

```
CREATE SCHEMA sdd_t10_roundtrip

uv run alembic upgrade head
  0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006 -> 0007 (oauth data model: four new tables +
  three nullable api_tokens columns)

uv run alembic downgrade 0006
  0007 -> 0006 (oauth data model reverted cleanly)

uv run alembic upgrade head
  0006 -> 0007 (re-applied cleanly)

uv run alembic current
  0007 (head)

DROP SCHEMA "sdd_t10_roundtrip" CASCADE  — done; public schema untouched
```

**Result: PASS.** The `0007` migration (oauth data model) upgrades cleanly from `0006`,
downgrades cleanly back to `0006`, and re-upgrades cleanly to `0007` again, ending at `0007
(head)`. Ran entirely in an isolated scratch schema against the test database; the scratch schema
was dropped afterward and no other schema was touched.

---

## 4. Owner-gated / deferred (NOT performed here)

The following remain explicitly deferred to the owner and were **not** executed by this task or
any agent:

- **Merge** — `feat/mcp-oauth` has not been merged to `main`.
- **Push** — no commit on this branch was pushed to any remote.
- **Deploy** — no image build/push/redeploy was performed. Deploying this feature requires, in
  THIS order (final fix round 2 correction — `docker compose exec` runs inside the OLD, already-
  running container and silently no-ops there, so the migration must come from the NEW image via
  a one-off `run --rm`, not `exec`; see `infra/deploy/prod/README.md`'s "Change procedure" step 2
  sub-bullet and `infra/deploy/database.md:10-17`'s own "Do this BEFORE bringing the API up"):
  1. **Merge + push** — merge `feat/mcp-oauth` to `main` and push.
  2. **Build + push the three images** at the merged SHA (`../push_ecr.sh`) and **bump the
     `api`/`admin`/`client` tags** in `infra/deploy/prod/docker-compose.yml` (both the box's copy
     and this committed copy — `prod/README.md`'s "Image tags" section) to that SHA — this is the
     step that actually selects the new image; `docker compose up -d` later only recreates the
     container from whatever tag is already in the file. Update the box-local `.env`/compose
     rendering so `OAUTH_ISSUER_URL` (now pinned in `infra/deploy/prod/docker-compose.yml`)
     actually reaches the `api` container.
  3. **`docker compose pull api && docker compose run --rm api uv run alembic upgrade head`** — a
     one-off container built from the NEW (just-bumped) image, not `docker compose exec` (which
     would run inside the OLD, still-running container, whose image has no `0007` and would
     silently no-op instead of migrating). Migrations are **not** run automatically by the api
     container's start command (`infra/deploy/database.md:41`); the prod `api` service has no
     `depends_on`, so `run --rm` starts nothing else. Equivalent alternative from a local checkout
     with network access to the DB: `infra/deploy/database.md:38-41`'s
     `cd apps/api && DATABASE_URL=… uv run alembic upgrade head`, no running container needed at
     all. Migration `0007` is additive and nullable, so migrating before `up -d` means there is no
     window where a NEW image is live against the OLD schema, which for THIS migration would 500
     not only `/oauth/*`/`/.well-known/*` but every request that resolves a bearer token
     (including the pre-existing CLI-minted connector path — `resolve_bearer_token` selects the
     three columns `0007` adds).
  4. **`docker compose up -d`** (per `infra/deploy/prod/README.md`'s "Change procedure") — only now,
     after the schema is already at `0007`.
  5. Re-run `infra/deploy/VERIFY.md` §5a's three curl checks against the live deployment (the
     `(recorded during deployment)` placeholders in that section are intentionally still empty —
     the feature is not deployed, so no output has been fabricated).
- **Real claude.ai Connect** — the exact checklist the owner runs once deployed:
  1. Run `infra/deploy/VERIFY.md` §5a's three curls against the live API and record the output in
     that file (RFC 9728 resource metadata, RFC 8414 AS metadata, unauthenticated MCP call now
     carrying the `WWW-Authenticate: Bearer resource_metadata="…"` challenge header).
  2. In claude.ai: Settings → Connectors → Add custom connector → URL
     `https://api.advisordesk.tyagiakanksha.com/api/v1/mcp` → **Connect**.
  3. Sign in with an allowlisted admin Google account when redirected, and **approve** the consent
     screen.
  4. From claude.ai, invoke a `search_content` tool call against the connector and confirm it
     returns real results.
  5. In the admin app's **Connected apps** page, confirm the new client appears with a live
     access/refresh token count and a stamped `last_used_at`.
  6. **Revoke** the client from Connected apps.
  7. Back in claude.ai, confirm the connector now shows as disconnected (the next call 401s /
     re-prompts for a fresh Connect).

None of the above was performed by this task. Everything in §1–§3 is real, locally-produced
output from commands actually run against this working tree and the test database.

## 5. Live outcome (2026-09-08, after task 10 — owner-driven)

What §4 deferred was then done, in order, on 2026-09-08:

- **Merge + push + deploy** — PR #23 merged → `main` `8f9cab3`; images pushed as `8f9cab3`; the
  migration ran via `compose run --rm api uv run alembic upgrade head` BEFORE `up -d` and walked
  prod **0004 → 0007** (0005/0006 had never been applied — see `infra/deploy/VERIFY.md` §5a's
  deploy-session note). §5a's three curls recorded in `VERIFY.md`; bookkeeping PR #24 → `main`
  `1557320`.
- **Real claude.ai Connect — steps 1–4 DONE, verified from the prod api access log** (read-only
  SSM `docker compose logs api`; times UTC). The successful run, connector added from the phone
  (mobile Chrome) with the detected defaults ("Always required", "No client ID — register one
  automatically" = DCR):

  ```
  16:25:06  160.79.106.x  POST /api/v1/mcp 401 → GET /.well-known/oauth-protected-resource 200
                          → GET /.well-known/oauth-authorization-server 200 → POST /api/v1/oauth/register 201
  16:26:28  phone         GET  /api/v1/oauth/authorize?response_type=code&client_id=adkc_QMvq…&redirect_uri=
                               https://claude.ai/api/mcp/auth_callback&code_challenge=…&code_challenge_method=S256
                               &state=…&scope=mcp&resource=https://api.adviso…            303
  16:26:28  phone         GET  /api/v1/oauth/authorize/continue                           200  (consent page)
  16:26:31  phone         POST /api/v1/oauth/authorize/decision                           302  (code issued)
  16:38:24  phone         GET  /api/v1/oauth/authorize?…client_id=adkc_QMvq…               303  (same client, re-Connect)
  16:38:25  phone         GET  /api/v1/oauth/authorize/continue                           302  (consent on file → code issued, no prompt)
  16:38:25  160.79.106.x  POST /api/v1/oauth/token                                        200  ← code exchanged
  16:38:26  160.79.106.x  POST /api/v1/mcp 200 ×2                                              (initialize + tools/list)
  16:38:29  160.79.106.x  POST /api/v1/mcp 200 ×2                                              (tool calls — "31 non-deleted content items")
  16:39:14  160.79.106.x  POST /api/v1/mcp 200 ×2
  ERROR/Traceback lines in the api log for the window: 0
  ```

  claude.ai's chat then reported "Connected. AdvisorDesk is live and responding — there are 31
  non-deleted content items" and listed the tool families (browse/search, drafts, tags,
  archive/delete, `report_content_gaps`). Observations worth keeping:
  - claude.ai sends the `resource` parameter on `/authorize` (from 16:25Z on; the very first
    attempts of the day did not) — the P8 `resource=""` fallback was not exercised.
  - Between 16:19Z and 16:26Z, **seven** approvals produced a `decision 302` but claude.ai never
    called `/oauth/token` — the code was issued and the redirect to
    `https://claude.ai/api/mcp/auth_callback?code=…&state=…` sent every time, yet the browser
    never delivered it. **Root cause (found 2026-09-09, after an eighth blocked approval on
    reconnect): our own bug, not the phone.** The consent page's
    `Content-Security-Policy: … form-action 'self'` header made Chrome/Edge refuse to follow the
    post-form-submission 302 to claude.ai (`form-action` is enforced against the redirects that
    follow a form POST, not just the form's target). The 16:38Z re-Connect succeeded precisely
    because consent was already on file — `/authorize/continue` issued the code via a plain GET
    redirect, no form submission, so the CSP check never applied. An earlier revision of this
    bullet claimed "server side was correct throughout"; the redirect was correct, but the header
    served with the consent page was the blocker. Fixed by `consent_csp(redirect_uri)` (PR #26,
    `fix/oauth-consent-csp`), which appends the client's DCR-validated redirect origin to
    `form-action`.
  - Two of the earlier attempts used a connector URL with a stray space (`/api%20/v1/mcp` → 404
    on every MCP POST and on the path-suffixed PRM lookup); claude.ai then fell back to the
    root PRM document and still registered a client. Re-adding with the exact URL fixed it.
  - A second tap on **Approve** after the 302 returns `400 {"error":"invalid_request",
    "error_description":"No pending authorization request."}` — single-use pending cookie, by
    design; harmless.
  - The retries left ~8 DCR client rows (`adkc_X2Cif…`, `adkc_3UX_q…`, `adkc_KvZPo…`,
    `adkc_DnnUs…`, `adkc_YCNyU…`, `adkc_fxAZU…`, `adkc_E2tyd…`, `adkc_QMvqA…` — the last one
    is the live connector); the others can be cleaned up from Admin → Connected apps → Revoke.
- **Steps 5–7 (Connected apps shows the client with live token counts + `last_used_at`; Revoke;
  claude.ai re-prompts) — still owner-pending.** Note: the owner's 2026-09-09 disconnect +
  reconnect attempt re-hit the CSP bug above (a deleted client means a fresh consent form, whose
  post-Approve redirect the header blocked) — a fresh Connect only works reliably once PR #26 is
  deployed (stopgap: Firefox, which does not enforce `form-action` on redirects).
- **CSP fix DEPLOYED + fresh-client Connect VERIFIED (2026-09-09).** PR #26 merged → `main`
  `6983941`, deployed ~05:20Z (images ×3 at `6983941`; admin/client digests identical to the
  `8f9cab3` builds — api/docs-only PRs; schema steady at `0007`, recorded before/after; box backup
  `docker-compose.yml.bak-8f9cab3`). At 14:05Z the owner reconnected: **fresh** DCR client
  (`adkc_nIhGO…`) → consent **form** rendered (`/authorize/continue` 200 — no consent-on-file
  shortcut this time) → Approve → `decision` 302 → **`POST /oauth/token` 200 within 0.5 s** →
  authenticated `POST /api/v1/mcp` 200 ×4. That is exactly the path that failed all eight times
  pre-fix, now completing — the `form-action` root-cause diagnosis and fix are both confirmed
  live. Post-deploy log sweep: the only errors since deploy are two isolated
  `GET /api/v1/public/content` 500s (05:54Z, 06:05Z, uptime poller) from
  `psycopg.OperationalError: … SSL connection has been closed unexpectedly` — stale pooled DB
  connections right after the container recreate, self-healed, none since; the engine sets no
  `pool_pre_ping` (`apps/api/app/db.py:45`), ledgered as a follow-up Minor.
