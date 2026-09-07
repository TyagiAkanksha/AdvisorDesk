# Phase-7 task-03 — Verification record

**Scope (Controller Ruling M/B):** this record documents the **local verification pass** —
including a real local clean-room README + `scripts/demo.sh` walk (§5, added fix round 1) — plus
the local §9.1 metrics, a full gate run, and the §2.2 story mapping. The deployed demo walk,
merge-to-main, and prod redeploy are owner-gated and were **not performed** — see the
"Owner-gated / deferred" section (§6) at the end.

---

## 1. §9.1 metrics (real, measured)

Measured on the **local seeded stack**: dedicated database `advisordesk_p7verify` (Postgres
container `advisordesk-test-db`, `127.0.0.1:5433`), **OpenAI provider**
(`LLM_PROVIDER=openai`, `EMBEDDING_MODEL=text-embedding-3-small`, `EMBEDDING_DIMENSIONS=1024`,
`CHAT_MODEL=gpt-4o-mini`), **`SIMILARITY_THRESHOLD=0.5`** (the `Settings` default — the root
`.env` does not override it). Run date: 2026-09-07. Full raw command output (seed logs, SQL,
harness table, latency samples) is captured in
`.superpowers/sdd/phase-7-evaluation/task-03a-metrics-capture.md` (gitignored working notes,
task t03a); the summary below is pasted from that capture verbatim.

| Metric | Value |
|---|---|
| Seeded documents (`content`) | `content_total = 21` (17 published + 4 drafts) |
| Seeded chunks (`chunks`) | `100` |
| MCP tools | `9` (`search_content, count_content, create_draft, edit_content, delete_content, tag_content, publish, archive, report_content_gaps`) |
| Groundedness | `groundedness: 58.8% fully supported; refusals 4/4 correct` (10/17 answerable fully supported; all 17 answerable questions retrieved the correct article; 4/4 unanswerable correctly refused) |
| First-token latency, `/public/chat` | `n = 30`, `p50 = 717 ms`, `p95 = 1602 ms` (nearest-rank; min 585 ms, max 2092 ms) |

**Groundedness honesty note:** all 17 answerable eval questions retrieved the correct source
article (`slugs_hit = True` on every row) — retrieval is sound. The sub-100% "fully supported"
figure comes from the `gpt-4o-mini` judge scoring some individual answer sentences as unsupported
by the cited chunks. This is exactly the evaluation signal the phase-7 harness is designed to
surface (PRD §10 Phase 7), not a retrieval bug — flagged below for owner review, not hidden or
rounded up.

Raw groundedness table (pasted from t03a):

```
answerable  slugs_hit  supported  refused  verdict question
-----------------------------------------------------------
True        True       True       False    PASS    What is a Roth IRA conversion and how is it taxed?
True        True       True       False    PASS    What's the difference between a traditional IRA and a Roth IRA?
True        True       True       False    PASS    How is the deadline for my first required minimum distribution determined, and what happens if I delay it?
True        True       False      False    FAIL    What factors should I consider when deciding what age to claim Social Security?
True        True       False      False    FAIL    How can tax-loss harvesting reduce my tax bill?
True        True       True       False    PASS    How do marginal tax brackets actually work?
True        True       False      False    FAIL    What are the tax advantages of a health savings account?
True        True       False      False    FAIL    What's the difference between a will and a trust, and do I need both?
True        True       True       False    PASS    Why do beneficiary designations on my retirement accounts matter so much?
True        True       False      False    FAIL    How does the federal estate tax exemption work, and can a surviving spouse use my unused amount?
True        True       True       False    PASS    What does a financial power of attorney let someone do on my behalf?
True        True       True       False    PASS    Why is diversification important when building an investment portfolio?
True        True       True       False    PASS    What is dollar-cost averaging and how does it work?
True        True       True       False    PASS    What is an index fund and how does it differ from an actively managed fund?
True        True       False      False    FAIL    What is a 529 plan and how does it help with saving for college?
True        True       True       False    PASS    What's the difference between term life insurance and whole life insurance?
True        True       False      False    FAIL    How does long-term disability insurance work, and how much of my income does it replace?
False       True       -          True     PASS    What does the firm recommend about cryptocurrency staking rewards?
False       True       -          True     PASS    Should I use a covered call options strategy to generate income on my portfolio?
False       True       -          True     PASS    Can you help me set up an offshore trust in the Cayman Islands?
False       True       -          True     PASS    How do I structure a real estate investment trust syndication for a rental property?
groundedness: 58.8% fully supported; refusals 4/4 correct
```

Raw first-token-latency samples (n=30, ms, `POST /api/v1/public/chat`, real OpenAI
`gpt-4o-mini` synthesis):

```
sorted: [585, 610, 613, 617, 621, 631, 642, 659, 662, 672, 676, 681, 691, 708,
         717, 732, 739, 765, 794, 803, 804, 804, 813, 839, 854, 855, 873, 893,
         1602, 2092]
p50 rank = ceil(0.50*30) = 15 -> index 14 = 717 ms
p95 rank = ceil(0.95*30) = 29 -> index 28 = 1602 ms
```

---

## 2. Full gate run (real, this pass — 2026-09-07)

All commands below were run from a clean working tree at `HEAD` (`abbddd4`) plus this task's own
edits (README + status flips, staged after the gates below). None of the frontend/backend source
changed as part of this task — only docs — so this is a genuine current-tree gate pass.

### `apps/api`

```
$ cd apps/api
$ export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' ../../.env | cut -d= -f2-)"

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
160 files already formatted

$ uv run mypy
Success: no issues found in 66 source files

$ uv run lint-imports
---------
Contracts
---------

Analyzed 66 files, 172 dependencies.
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

$ uv run pytest -q
........................................................................ [ 12%]
........................................................................ [ 25%]
........s............................................................... [ 38%]
........................................................................ [ 51%]
........................................................................ [ 63%]
........................................................................ [ 76%]
........................................................................ [ 89%]
............................................................             [100%]
563 passed, 1 skipped in 80.12s (0:01:20)
```

**Result: PASS** (ruff check, ruff format, mypy, lint-imports 8/8 contracts, pytest 563
passed / 1 skipped).

### `apps/admin`

```
$ pnpm -C apps/admin lint
$ eslint .
(no findings — clean exit)

$ pnpm -C apps/admin type-check
$ tsc --noEmit
(no findings — clean exit)

$ pnpm -C apps/admin test
$ vitest run
 Test Files  36 passed (36)
      Tests  118 passed (118)
   Duration  67.52s
```

**Result: PASS** (lint clean, type-check clean, 36 test files / 118 tests passed).

### `apps/client`

```
$ pnpm -C apps/client lint
$ eslint .
(no findings — clean exit)

$ pnpm -C apps/client type-check
$ tsc --noEmit
(no findings — clean exit)

$ pnpm -C apps/client test
$ vitest run
 Test Files  14 passed (14)
      Tests  58 passed (58)
   Duration  5.98s
```

**Result: PASS** (lint clean, type-check clean, 14 test files / 58 tests passed).

### Codegen drift check

```
$ git diff --exit-code apps/api/openapi.json apps/api/mcp-tools.json
$ echo $?
0
```

**Result: PASS** (clean — no drift between committed `openapi.json`/`mcp-tools.json` and the
current route/tool schemas).

### Compose profile validation

```
$ docker compose -f infra/docker-compose.yml config -q
$ echo $?
0

$ docker compose -f infra/docker-compose.yml --profile local-db config -q
$ echo $?
0
```

**Result: PASS** (both profiles — no `local-db`, and with `local-db` — parse cleanly). A full
`up` was not run for this task per the brief: the prod stack is already live, and t03a already
booted the API locally against `advisordesk_p7verify` for the latency/groundedness runs above.

### Gate summary

| Gate | Result |
|---|---|
| `apps/api` ruff check | PASS |
| `apps/api` ruff format --check | PASS |
| `apps/api` mypy | PASS |
| `apps/api` lint-imports | PASS (8/8 contracts) |
| `apps/api` pytest | PASS (563 passed, 1 skipped) |
| `apps/admin` lint / type-check / test | PASS (118 tests) |
| `apps/client` lint / type-check / test | PASS (58 tests) |
| `openapi.json` / `mcp-tools.json` drift | PASS (clean) |
| Compose config (both profiles) | PASS |

**All gates green. No fudging, no skipped gate.**

---

## 3. §2.2 cross-check — user story → proof mapping

Every PRD §2.2 user story, and where it is demonstrably proven (existing test or documented demo
step — no new tests written for this task).

### CMS admin

| # | User story | Proof |
|---|---|---|
| 1 | Sign in with Google (allowlisted email); dashboard of all content with status, tags, updated date | Backend: `apps/api/tests/test_auth_endpoints.py::test_login_redirects_to_fake_google_consent_url`, `::test_callback_allowlisted_email_creates_user_and_sets_session_cookie`, `::test_callback_unlisted_email_rejected_with_403_and_no_row_created`. Frontend: `apps/admin/src/components/auth/SignInScreen/Component.test.tsx`, `apps/admin/src/components/auth/RequireSession/Component.test.tsx`, `apps/admin/src/components/dashboard/DashboardScreen/Component.test.tsx`. Demo: README "Admin story" steps 1–2. |
| 2 | Create, edit, delete a content item (title, markdown body, tags, status); deletion permanent, no restore | Backend: `apps/api/tests/test_routes_content.py::test_create_get_patch_list_happy_path`, `::test_soft_deleted_content_404s_on_all_by_id_operations`. Frontend: `apps/admin/src/components/content/ContentEditorScreen/Component.test.tsx`, `apps/admin/src/components/content/ContentListScreen/deleteError.test.tsx`. Demo: README "Admin story" step 3 (Content list). |
| 3 | Move item through statuses `draft → published → archived` | Backend: `apps/api/tests/test_lifecycle_transitions.py::test_publish_content_from_draft_sets_published_at_once_legal_path_still_passes`, `::test_archive_content_from_published_removes_chunks_legal_path_still_passes`, `::test_archive_content_from_draft_raises_conflict_error_and_leaves_row_untouched`. Frontend: `apps/admin/src/components/content/ContentEditorScreen/publishGuard.test.tsx`. |
| 4 | Publishing embeds into the vector store; archiving/deleting removes it from retrieval | Backend: `apps/api/tests/test_lifecycle_transitions.py::test_republish_after_archive_preserves_published_at_and_rebuilds_chunks`, `apps/api/tests/test_mcp_write_tools.py::test_publish_draft_to_published_builds_chunks_and_sets_published_at`, `::test_archive_published_to_archived_removes_chunks`, `apps/api/tests/test_reembed_script.py`. |
| 5 | Filter/search content by title, tag, status | Backend: `apps/api/tests/test_routes_content.py::test_list_content_filters_by_status_tag_and_q`, `::test_list_content_q_omitted_and_q_empty_string_both_return_full_set`. Frontend: `apps/admin/src/components/content/ContentListScreen/Component.test.tsx`, `pagination.test.tsx`. |
| 6 | Agent panel: natural-language commands via MCP tools, live `tool_call`/`tool_result` rendering | Backend: `apps/api/tests/test_agent_loop.py::test_two_tool_script_emits_events_in_execution_order_with_full_done_summary`, `::test_draft_rule_agent_never_calls_publish_leaves_status_draft`, `apps/api/tests/test_mcp_write_tools.py::test_create_draft_returns_id_slug_draft_status_and_stamps_actor`, `::test_tag_content_adds_and_removes_tags_in_one_call`. Frontend: `apps/admin/src/components/agent/AgentPanel/Component.test.tsx`, `apps/admin/src/components/agent/useAgentStream.test.tsx`. Demo: README "Admin story" step 4 (all three example commands verbatim from PRD §2.2). |

### Client app

| # | User story | Proof |
|---|---|---|
| 7 | Browse published content (list + detail page rendering markdown) | Backend: `apps/api/tests/test_public_content.py::test_public_content_list_returns_only_the_published_item_with_sorted_tags`, `::test_public_content_get_returns_full_detail_for_the_published_slug`, `::test_public_content_get_404s_for_non_published_and_unknown_slugs`. Frontend: `apps/client/src/components/content/ContentListScreen/Component.test.tsx`, `apps/client/src/components/content/ArticleScreen/Component.test.tsx`, `apps/client/src/components/content/Markdown/Component.test.tsx`. Demo: README "Client story" step 1 (`GET /api/v1/public/content`). |
| 8 | Ask the assistant a question; streamed answer with numbered citations | Backend: `apps/api/tests/test_public_chat.py::test_happy_path_streams_tokens_then_citations_then_done`, `::test_citation_asymmetry_wire_deduped_content_level_row_chunk_level_from_one_exchange`, `apps/api/tests/test_synthesis_numbering.py`. Frontend: `apps/client/src/components/chat/ChatScreen/Component.test.tsx`, `apps/client/src/components/chat/CitationList/Component.test.tsx`, `apps/client/src/components/chat/useChatStream.test.ts`. Demo: README "Client story" step 2 (live SSE capture, Roth IRA conversion question, cited to `roth-ira-conversion-basics`). |
| 9 | Unanswerable question → assistant refuses, does not answer from general knowledge | Backend: `apps/api/tests/test_public_chat.py::test_outcome_recording_uncovered_question_refuses_with_zero_sources_and_retrieval_found_false`, `apps/api/tests/test_groundedness.py::test_uncovered_question_with_correct_refusal_counts_as_refusal_correct`, `::test_uncovered_question_with_hallucinated_answer_counts_as_refusal_incorrect`. Demo: README "Client story" step 3 (live refusal capture); groundedness harness metric above — refusals 4/4 correct on the real eval set. |

All nine §2.2 user stories have a passing automated test and/or a documented, live-captured demo
step. No story is unproven.

---

## 4. Status flips (Controller Ruling E)

Flipped `status: planned` → `status: built` in all 33 task files across phase-1 through
phase-7-evaluation (phase-6-remediation task files carry no `status:` frontmatter field — they
track completion per-task in `docs/plans/phase-6-remediation/00-INDEX.md`'s batch table instead,
which already reflects real commits/reviews and was left untouched). Flipped the `## Status`
line in all seven `00-INDEX.md` files that have one (phase-1 through phase-7 — phase-6-remediation's
INDEX uses the batch table, not a `## Status` line) from `planned` to `built`. Updated the phase-7
row and closing note in `docs/plans/README.md`'s registry table. The `snapshot only; git history
is authoritative` disclaimer was preserved verbatim everywhere.

Files touched (33 task files + 7 `00-INDEX.md` + `docs/plans/README.md` = 41 files):

```
docs/plans/phase-1-skeleton/task-01-repo-scaffold-python-tooling.md
docs/plans/phase-1-skeleton/task-02-db-models-alembic.md
docs/plans/phase-1-skeleton/task-03-app-factory-health-errors.md
docs/plans/phase-1-skeleton/task-04-frontend-scaffolds-theme-codegen.md
docs/plans/phase-1-skeleton/task-05-compose-dockerfiles.md
docs/plans/phase-1-skeleton/00-INDEX.md
docs/plans/phase-2-auth-cms-crud/task-01-google-oauth-sessions.md
docs/plans/phase-2-auth-cms-crud/task-02-content-tag-services.md
docs/plans/phase-2-auth-cms-crud/task-03-admin-rest-routes.md
docs/plans/phase-2-auth-cms-crud/task-04-admin-shell-auth-ui.md
docs/plans/phase-2-auth-cms-crud/task-05-admin-dashboard-list.md
docs/plans/phase-2-auth-cms-crud/task-06-admin-editor-transitions.md
docs/plans/phase-2-auth-cms-crud/00-INDEX.md
docs/plans/phase-3-publish-client-content/task-01-chunking.md
docs/plans/phase-3-publish-client-content/task-02-embedding-lifecycle.md
docs/plans/phase-3-publish-client-content/task-03-public-content-api.md
docs/plans/phase-3-publish-client-content/task-04-client-content-ui.md
docs/plans/phase-3-publish-client-content/00-INDEX.md
docs/plans/phase-4-rag-assistant/task-01-retrieval.md
docs/plans/phase-4-rag-assistant/task-02-chat-synthesis-sse.md
docs/plans/phase-4-rag-assistant/task-03-rate-limiting.md
docs/plans/phase-4-rag-assistant/task-04-seed-content-eval-set.md
docs/plans/phase-4-rag-assistant/task-05-client-chat-ui.md
docs/plans/phase-4-rag-assistant/00-INDEX.md
docs/plans/phase-5-mcp-agent/task-00-lifecycle-hardening.md
docs/plans/phase-5-mcp-agent/task-01-mcp-server-read-tools.md
docs/plans/phase-5-mcp-agent/task-02-mcp-write-tools.md
docs/plans/phase-5-mcp-agent/task-03-agent-loop-endpoint.md
docs/plans/phase-5-mcp-agent/task-04-admin-agent-panel.md
docs/plans/phase-5-mcp-agent/00-INDEX.md
docs/plans/phase-6-deployment/task-01-metrics-middleware.md
docs/plans/phase-6-deployment/task-02-aws-deployment.md
docs/plans/phase-6-deployment/task-03-readme-demo-script.md
docs/plans/phase-6-deployment/task-04-mcp-bearer-auth.md
docs/plans/phase-6-deployment/task-05-auth-hardening.md
docs/plans/phase-6-deployment/00-INDEX.md
docs/plans/phase-7-evaluation/task-01-report-content-gaps.md
docs/plans/phase-7-evaluation/task-02-groundedness-harness.md
docs/plans/phase-7-evaluation/task-03-metrics-final-verification.md
docs/plans/phase-7-evaluation/00-INDEX.md
docs/plans/README.md
```

Verification: `grep -rn "status: planned" docs/plans/` returns only one line — the literal verify
command shown inside `task-03-metrics-final-verification.md`'s own `## Verify` code block
(`grep -rn "status: planned" docs/plans/    # empty`), which is documentation text, not a status
declaration; no file's actual `status:` frontmatter or `## Status` line reads `planned` anymore.

---

## 5. Local clean-room README walk (DoD §10) — fix round 1

**Added in fix round 1** (2026-09-07, same day as the rest of this record): Controller Ruling M
required an actual LOCAL clean-room walk of the README's local-db path plus a real
`scripts/demo.sh` run — this was the §10 definition-of-done centerpiece ("a stranger can follow
the README, run the demo script end to end") and had been missed in the first pass. It is now
performed and recorded below, with real output throughout.

### Method

A genuinely fresh clone (not the working checkout) at
`/home/ak/.claude/jobs/9c940f15/tmp/cleanroom`, cloned from the local repo's own git objects
(`git clone /home/ak/Documents/github_akanksha/AdvisorDesk cleanroom`) rather than over the
network from GitHub — this reproduces exactly the same committed tree a `git clone
https://github.com/TyagiAkanksha/AdvisorDesk.git` would (git clone only ever copies committed
refs; no working-tree state leaks in), just without a network dependency, then checked out to
`feat/phase-7-evaluation` at the same commit as this record (`6766bd2`):

```
$ git clone /home/ak/Documents/github_akanksha/AdvisorDesk cleanroom
Cloning into 'cleanroom'...
done.
$ cd cleanroom && git checkout feat/phase-7-evaluation
Already on 'feat/phase-7-evaluation'
$ git log -1 --format='%H %s'
6766bd2ce06fc4e0c7aed1711774d65af8ca065e docs: metrics + definition-of-done verification record (phase-7 task-03)
```

### Step 1 — configure `.env` (README "1. Configure environment")

```
$ cp .env.example .env
```

Filled per README: `DATABASE_URL=postgresql://postgres:postgres@db:5432/postgres` (the
documented **Local Postgres (fully offline dev), canonical** value — README §"2. Choose a
database path"), a freshly generated `SESSION_SECRET` (`python3 -c "import secrets;
print(secrets.token_urlsafe(48))"`, per the README's own command), the real `OPENAI_API_KEY`
copied from the main checkout's `.env` (needed for the chat/embedding calls below — never printed
to any log or this record), and placeholder `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
`ADMIN_EMAILS` values (the client-story demo path this walk exercises is public/no-auth per PRD
§2.2; admin sign-in was already covered by existing tests in §3 above, not re-walked here).

### Step 2 — bring up the local-db profile (README "2. Choose a database path")

```
$ docker compose -f infra/docker-compose.yml --profile local-db up -d --build
...
 Image advisordesk-admin Built
 Image advisordesk-api Built
 Image advisordesk-client Built
 Network infra_default Created
 Volume infra_advisordesk_local_db Created
 Container infra-db-1 Created
 Container infra-admin-1 Created
 Container infra-client-1 Created
 Container infra-api-1 Created
 Container infra-admin-1 Started
 Container infra-db-1 Started
 Container infra-db-1 Waiting
 Container infra-client-1 Started
 Container infra-db-1 Healthy
 Container infra-api-1 Starting
 Container infra-api-1 Started

$ docker compose -f infra/docker-compose.yml --profile local-db ps
NAME             IMAGE                    COMMAND                   SERVICE   STATUS                            PORTS
infra-admin-1    advisordesk-admin        "docker-entrypoint.s…"    admin     Up (healthy)                      127.0.0.1:3001->3000/tcp
infra-api-1      advisordesk-api          "sh -c 'if [ -n \"$DA…"   api       Up (health: starting)             127.0.0.1:8000->8000/tcp
infra-client-1   advisordesk-client       "docker-entrypoint.s…"    client    Up (health: starting)             127.0.0.1:3000->3000/tcp
infra-db-1       pgvector/pgvector:pg16   "docker-entrypoint.s…"    db        Up (healthy)                      127.0.0.1:5432->5432/tcp
```

All three images built clean from the fresh clone (no cached layers from the main checkout's
prior builds carried over meaningfully — base layers cached by digest as normal, but the
`apps/api`/`apps/admin`/`apps/client` COPY layers rebuilt from the clone's own files) and all four
containers came up, `db` reporting healthy before `api` started — matching the README's
documented `depends_on: condition: service_healthy` behavior exactly.

```
$ docker compose -f infra/docker-compose.yml run --rm api uv run alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, chunks.embedding: vector(1536) -> vector(1024) (PRD §7.2, v1.5)
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, api_tokens: bearer tokens for the MCP endpoint (PRD §3, §9; phase-6 task-04)
INFO  [alembic.runtime.migration] Running upgrade 0003 -> 0004, users.session_epoch: server-side session revocation counter (PRD §9; phase-6 task-05)
INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, api_tokens.session_epoch: per-token revocation stamp (PRD §9; phase-6 remediation task-03)
INFO  [alembic.runtime.migration] Running upgrade 0005 -> 0006, api_tokens.expires_at: bearer-token expiry (PRD §9; phase-6 remediation task-09, WR-02 residual)
```

Migrations applied cleanly to head, exactly as the README documents.

### Step 3 — seed the corpus: a real bug found by this walk

The coordinator's fix-round instructions asked for
`docker compose -f infra/docker-compose.yml run --rm api uv run python -m app.seed` (needed so
the demo's chat/citation queries have real content to ground against — note this exact seed
invocation is **not** itself part of the README's own documented Dev-quickstart steps, which stop
at migrate + healthz/200 checks). Running it exposed a genuine, previously-undetected bug:

```
$ docker compose -f infra/docker-compose.yml run --rm api uv run python -m app.seed
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/app/app/seed.py", line 89, in <module>
    _REPO_ROOT: Path = Path(__file__).resolve().parents[3]
                       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^
  File "/usr/local/lib/python3.12/pathlib.py", line 282, in __getitem__
    raise IndexError(idx)
IndexError: 3
```

Root cause, confirmed directly against the built image:

```
$ docker run --rm advisordesk-api sh -c "ls /app; echo ---; ls /app/app | head -20"
alembic
alembic.ini
app
---
__init__.py
agent
auth
config.py
db.py
eval
factory.py
main.py
mcp
models
rag
routes
seed.py
services
```

Two independent problems, both real:

1. `app/seed.py`'s `_run_from_cli` computes `_REPO_ROOT = Path(__file__).resolve().parents[3]`
   (`apps/api/app/seed.py` module-docstring comment: "`app/seed.py` -> `app/` -> `apps/api/` ->
   `apps/` -> repo root: four `.parent`s up"). That arithmetic is correct for the **local host**
   layout (`<repo-root>/apps/api/app/seed.py`) but wrong inside the container: `infra/Dockerfile.api`
   copies `apps/api/app` to `/app/app` directly (not nested under `apps/api/`), so in-container
   `__file__` is `/app/app/seed.py` and `.parents` only has 3 entries (`[0]=/app/app`, `[1]=/app`,
   `[2]=/`) — `parents[3]` is out of range, raising `IndexError`.
2. Even if that resolved, it wouldn't matter: `infra/Dockerfile.api` never `COPY`s the repo-root
   `seed/` directory into the image at all (only `apps/api/app`, `apps/api/alembic`,
   `apps/api/alembic.ini` — confirmed by the `docker run` listing above, no `seed/` anywhere under
   `/app`). `seed/sample_content/` does not exist in the API image under any path.

**This is a real, previously-unrecorded finding, not fabricated and not something this task fixes**
(out of scope for a verification pass — task-03's brief is to record reality, not patch code).
Flagged below for owner/backlog triage: `docker compose run --rm api uv run python -m app.seed`
does not work today and would need (a) a container-aware repo-root/content-dir resolution in
`app/seed.py`, and (b) the seed corpus added to the API image's build context, to ever work.

**Fallback taken (per the fix-round HONESTY CLAUSE):** seeded via the host-side invocation the
README's own **Implementation notes** section already documents and pins as the real, working
command for this exact scenario (`cd apps/api && ... && uv run python -m app.seed`), pointed at
the clean-room stack's own `db` container over its host-published port
(`local-db` profile publishes `127.0.0.1:5432:5432`) instead of a bare `localhost` default:

```
$ cd apps/api
$ uv sync --frozen                                    # fresh venv for the clean-room clone
$ set -a; . ../../.env; set +a
$ export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/postgres"
$ uv run python -m app.seed
INFO:httpx:HTTP Request: POST https://api.openai.com/v1/embeddings "HTTP/1.1 200 OK"
INFO:__main__:seed: published 529-plan-basics (7 chunks)
... [17 published, 4 drafts, real OpenAI embedding calls throughout — identical corpus to t03a] ...
seed_all: created=21 published=17 skipped=0 chunk_count=100
```

This is the exact same host command (and `_REPO_ROOT` code path) already proven working in t03a
and in the container's own doc comments — no new mechanism invented, and it genuinely reached
`created=21 published=17 chunk_count=100` against the clean-room stack's real containerized
Postgres, with real OpenAI embedding calls.

### Step 4 — verify (README "3. Verify")

```
$ curl -s localhost:8000/api/v1/healthz
{"status":"ok"}
$ curl -sI localhost:3001 | head -1
HTTP/1.1 200 OK
$ curl -sI localhost:3000 | head -1
HTTP/1.1 200 OK
```

All three README step-3 checks pass exactly as documented, against the clean-room-built images.

### Step 5 — `scripts/demo.sh` (client story, full run, real output)

```
$ BASE_URL=http://localhost:8000 ./scripts/demo.sh
== 1. Browse published content: GET /api/v1/public/content ==
[{"title":"Wills vs Trusts Basics","slug":"wills-vs-trusts-basics", ...} ... 17 published items total ...]

== 2. Ask an answerable question (expects a streamed, cited answer) ==
event: token
data: {"text": "A"}
event: token
data: {"text": " Roth"}
... [SSE token stream, one word/punctuation mark per event] ...
event: token
data: {"text": "]."}

event: citations
data: {"citations": [{"content_id": "577bc9fd-1e2f-4ac0-9129-d38fbd023215", "title": "Roth IRA Conversion Basics", "slug": "roth-ira-conversion-basics"}, {"content_id": "8b07fda6-6874-418c-8b80-579af4c719b4", "title": "Traditional vs Roth IRA Basics", "slug": "traditional-vs-roth-ira-basics"}]}

event: done
data: {"session_id": "28004f42-1490-40bc-94c5-df44b48f3718", "message_id": "d7d5841e-7112-49dd-951f-d6f170b7cb9c"}

== 3. Ask an unanswerable question (expects a refusal, no general-knowledge answer) ==
event: token
data: {"text": "No"}
event: token
data: {"text": " published"}
... [token stream] ...
event: token
data: {"text": "."}

event: citations
data: {"citations": []}

event: done
data: {"session_id": "af853785-74f1-4bcd-85fb-d1df86178465", "message_id": "fb3e23d3-c97c-4df6-8c10-b6446dd664f9"}
```

Assembled answer 2 (grounded, cited): "A Roth IRA conversion involves moving money from a
traditional IRA or another pre-tax retirement account into a Roth IRA. When you convert, the
amount moved is treated as ordinary income in the year of the conversion, which means it is
taxable. However, once the funds are inside the Roth account, they grow tax-free, and withdrawals
can also be tax-free after meeting certain criteria, such as the five-year and age 59½ rules
[1]." — cited to `roth-ira-conversion-basics` (the exact slug `eval_questions.yaml` expects) and
`traditional-vs-roth-ira-basics`.

Assembled answer 3 (refusal): "No published guidance covers this. I suggest you ask the advisory
team for more information on cryptocurrency staking rewards." — the PRD §7.5 refusal, with an
empty `citations` array this time (unlike the deployed-stack capture in README, which happened to
surface a loosely-related chunk on a different question — both are legal per the retrieval
convention: the refusal wording, not the citations array, is the reliable signal).

```
$ BASE_URL=http://localhost:8000 ./scripts/demo.sh > /tmp/cleanroom_demo_rerun.log 2>&1; echo $?
0
```

**`scripts/demo.sh` ran end-to-end against the clean-room local stack and exited 0.** Both PRD
§2.2 client-story behaviors (grounded cited answer, correct refusal) are proven live, not just by
unit test.

### Step 6 — teardown

```
$ docker compose -f infra/docker-compose.yml --profile local-db down -v
 Container infra-client-1 Removed
 Container infra-api-1 Removed
 Container infra-db-1 Removed
 Container infra-admin-1 Removed
 Volume infra_advisordesk_local_db Removed
 Network infra_default Removed
$ docker rmi advisordesk-admin advisordesk-api advisordesk-client
Untagged/Deleted (all three)
$ rm -rf /home/ak/.claude/jobs/9c940f15/tmp/cleanroom
```

Confirmed clean: `docker ps -a` afterward shows only the pre-existing, unrelated
`advisordesk-test-db` throwaway container; no clean-room images or the temp clone directory
remain.

### Outcome

**The README local-db path, followed verbatim from a genuinely fresh clone, reaches a working
stack, and `scripts/demo.sh` runs end-to-end against it with real grounded/cited and refusal
output — the §10 definition of done, actually walked, not just asserted.** One real deviation is
disclosed above (container-side seeding is broken; host-side seeding — already the README's own
documented fallback — was used instead) and one real, previously-unknown bug was surfaced and
flagged for owner/backlog triage rather than silently worked around.

---

## 6. Owner-gated / deferred (NOT performed here — Controller Ruling M/B)

Per the controller's scope ruling, this task performed only the **local** verification pass. The
following are explicitly deferred to the owner and were **not** executed:

- **Deployed demo walk** — walking `docs/DEMO.md` / README's Demo section end-to-end against the
  live deployed stack (`https://advisordesk.tyagiakanksha.com`,
  `https://api.advisordesk.tyagiakanksha.com`, `https://admin.advisordesk.tyagiakanksha.com`).
  The README's existing "Captured live" callouts (2026-09-06) already document a prior live run;
  this task did not re-run it.
- **Merge to `main`** — this task's changes (README Metrics, status flips, this record) remain on
  the working branch pending owner review; no merge was performed.
- **Prod redeploy** — no image build/push/redeploy was performed. The `advisordesk_p7verify`
  metrics above are local-only and do not require or trigger any change to the deployed
  Supabase database or running containers.

**Flagged for owner review:**

1. The groundedness result — `58.8%` fully supported (10/17 answerable) — is real and measured,
   not a bug. All 17 answerable questions retrieved the correct article (retrieval is sound); the
   shortfall is the `gpt-4o-mini` judge finding some answer sentences unsupported by the cited
   chunks on 7 of 17 questions. This is the harness doing its job (PRD §10 Phase 7's stated
   purpose), and is left as-is per Controller Ruling: record plainly, do not inflate or hide.
2. **New finding (fix round 1, §5 above):** `docker compose -f infra/docker-compose.yml run --rm
   api uv run python -m app.seed` is broken — `app/seed.py`'s `_REPO_ROOT` path-depth arithmetic
   is wrong for the container's shallower `/app` layout (`IndexError: 3`), and independently,
   `infra/Dockerfile.api` never copies the repo-root `seed/` directory into the image at all. This
   is not something a README/demo user hits on the **documented** path (seeding isn't itself a
   Dev-quickstart step), but it means "seed inside the container" specifically does not work
   today. Left unfixed here — task-03 records reality, it does not patch code — and flagged for a
   follow-up task/backlog item.

---

## 7. Root-level plan doc note (Minor)

`advisordesk-task-breakdown-plan.md:183` contains the literal text `status: planned` — but it sits
inside a fenced ```markdown``` code block (§5 "Task file format") that documents the **generic
template shape** every `task-NN-*.md` file follows (`id`, `phase`, `depends_on`, `status`,
`spec` frontmatter keys), not a real task's actual status. The document's own header (line 3)
already reads "**Status:** EXECUTED 2026-07-28 ... everything in §3 now exists in the repo; this
document remains as the design rationale" — i.e. the whole file is already correctly marked done;
the `status: planned` string is illustrative template text, not a live status declaration, and
flipping it would corrupt the example. It is also outside this task's stated scope (`docs/plans/`
only, per Ruling E and the brief's own Verify command). Left unchanged, noted here per the
fix-round instruction.
