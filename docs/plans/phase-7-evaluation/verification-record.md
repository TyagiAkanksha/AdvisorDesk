# Phase-7 task-03 — Verification record

**Scope (Controller Ruling M/B):** this record documents the **local verification pass** only.
The deployed demo walk, merge-to-main, and prod redeploy are owner-gated and were **not
performed** — see the "Owner-gated / deferred" section at the end.

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

## 5. Owner-gated / deferred (NOT performed here — Controller Ruling M/B)

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

**Flagged for owner review:** the groundedness result — `58.8%` fully supported (10/17
answerable) — is real and measured, not a bug. All 17 answerable questions retrieved the correct
article (retrieval is sound); the shortfall is the `gpt-4o-mini` judge finding some answer
sentences unsupported by the cited chunks on 7 of 17 questions. This is the harness doing its
job (PRD §10 Phase 7's stated purpose), and is left as-is per Controller Ruling: record plainly,
do not inflate or hide.
