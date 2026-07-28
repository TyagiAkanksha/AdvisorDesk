# AdvisorDesk — Task Breakdown & Conventions Plan (for review)

**Status:** EXECUTED 2026-07-28 (overnight, owner-approved) — everything in §3 now exists in the
repo; this document remains as the design rationale. Review the deliverables directly:
`CONVENTIONS.md`, `docs/FRONTEND-CONVENTIONS.md`, `docs/plans/README.md`, `docs/plans/phase-*/`.
**Spec:** `advisordesk-prd.md` v1.4 (authoritative). **Reference studied:** `reference_project/span-agent/`.

> Late additions folded in during execution (owner request, 2026-07-27 night):
> - Every task file leads with a `## Goal` section; INDEXes carry Goal/Architecture/Tech-Stack
>   headers (superpowers:writing-plans format).
> - TDD runs through the installed **superpowers** plugin: INDEX banners require
>   `subagent-driven-development`/`executing-plans`; constraints require
>   `test-driven-development` + `verification-before-completion`. Prerequisites documented in
>   `docs/plans/README.md`.
> - Steps are bite-sized checkbox TDD cycles (failing test → run FAIL → implement → run PASS →
>   gates → commit) with exact commands and expected output; every task also carries a `## Files`
>   block with exact paths.

---

## 1. What this plan does

Breaks the PRD into an executable task system in the reference project's proven format, and captures
the codebase style learned from the reference as conventions documents that every task cites.

From studying `reference_project/span-agent/`:

- **Work-breakdown format** (`docs/superpowers/plans/`): a folder per initiative containing
  `00-INDEX.md` (goal, global constraints, task table, ordering rationale) plus one
  `task-NN-<slug>.md` per task. Each task file carries YAML frontmatter (`id`, `depends_on`,
  `status`, `spec`) and sections Purpose / Context / Interfaces / Steps (TDD, checkboxes) / Verify /
  Acceptance. **Subtasks are the checkboxed steps inside a task file** — deliberately not separate
  files, so one implementer (or subagent) gets a whole task in a single read.
- **Backend style** (`content_platform`): layered FastAPI (routes → DTO schemas + services →
  models), session-first service functions that `flush()` but never `commit()`, a typed exception
  family mapped to HTTP once via `register_error_handlers` (no try/except in routes),
  a `create_app(session_factory=None, config=None)` factory with no module-level globals, explicit
  stable `operation_id` on every route feeding `openapi-typescript` codegen, committed
  wire-surface baselines (`openapi.json`, `mcp-tools.json`) as refactor oracles, uv + ruff + strict
  mypy + import-linter layering contracts enforced as tests.
- **Frontend style** (`cms_ui`): folder-per-component (`<Name>/{Component.tsx, interface.ts,
  index.ts, Component.test.tsx}`), thin `page.tsx` (import + render only), screens under
  `components/<domain>/`, a `components/common/` primitives layer that wraps the UI library so call
  sites never import it directly, `src/types/` as the only layer touching generated API types,
  RTK Query with per-domain injected endpoints and tag invalidation, vitest with node-default env.

Two things from the reference deliberately **not** copied:

1. Its private design system (`span-ui` + HeroUI + MDI webfont) — unavailable to this repo.
2. Its no-migration-tool `create_all` bootstrap — its own README documents a production incident
   caused by this; AdvisorDesk uses **Alembic** instead.

## 2. Decisions (owner-confirmed)

| # | Decision |
|---|---|
| 1 | **Structure**: reference style — one folder per PRD §10 phase under `docs/plans/`, `00-INDEX.md` + `task-NN-<slug>.md` files, subtasks as checkboxes inside task files. The PRD's own phase structure is the organizing axis (no epic/unit vocabulary). |
| 2 | **Conventions docs are part of this deliverable**: root `CONVENTIONS.md` (Python) + `docs/FRONTEND-CONVENTIONS.md` (shared by both Next.js apps), authored before any task executes so tasks can cite their section numbers. |
| 3 | **UI stack: Material UI** — `@mui/material` + `@mui/icons-material` + `@mui/material-nextjs` (App Router SSR), Emotion styling, `createTheme()` as the design-token system, **no Tailwind**. Recorded as a PRD edit (v1.4: §11 row 6, §3.1 comments, changelog). |

## 3. Deliverables

```
CONVENTIONS.md                              # Python house rules (outline in §6)
docs/FRONTEND-CONVENTIONS.md                # both Next.js apps (outline in §6)
docs/plans/README.md                        # registry: 7-row phase table + status snapshot note
docs/plans/phase-1-skeleton/                # 00-INDEX.md + 5 task files
docs/plans/phase-2-auth-cms-crud/           # 00-INDEX.md + 6 task files
docs/plans/phase-3-publish-client-content/  # 00-INDEX.md + 4 task files
docs/plans/phase-4-rag-assistant/           # 00-INDEX.md + 5 task files
docs/plans/phase-5-mcp-agent/               # 00-INDEX.md + 4 task files
docs/plans/phase-6-deployment/              # 00-INDEX.md + 3 task files
docs/plans/phase-7-evaluation/              # 00-INDEX.md + 3 task files
advisordesk-prd.md                          # EDIT → v1.4 (MUI deviation, §7 below)
```

**30 task files + 7 INDEX files + registry + 2 conventions docs + 1 PRD edit.**

## 4. Task breakdown

### Phase 1 — Skeleton (`phase-1-skeleton/`) — PRD §10 P1, §3.1, §4, §9

| # | Task | Depends on | Scope |
|---|---|---|---|
| 01 | `repo-scaffold-python-tooling` | — | §3.1 monorepo skeleton (`apps/{admin,client,api}`, `infra/`, `seed/`); apps/api uv project with runtime-vs-dev dependency discipline; ruff (line 100, E/F/I/UP/B, FastAPI `Depends` B008 exemption), mypy strict over explicit file list, import-linter layering contracts (routes/mcp/agent/rag → services → models; routes and mcp never import each other); gates-as-tests (`test_lint_clean.py`, `test_import_contracts.py`); `.env.example` with all §9 vars; README + SUGGESTIONS.md stubs |
| 02 | `db-models-alembic` | 01 | SQLAlchemy 2.0 models for all 7 §4 tables (pgvector `Vector(1536)`); Alembic init + initial migration (vector extension, HNSW index, the 3 §4.1 FK indexes); define-once active-row filter helper (§4.1); throwaway-schema pytest fixture via `alembic upgrade head`, skipping when `TEST_DATABASE_URL` unset |
| 03 | `app-factory-health-errors` | 02 | `create_app(session_factory=None, config=None)` with `app.state` wiring and DB-less construction; pydantic-settings config (§9 env roster + defaults); typed error family + `register_error_handlers` → `{error:{code,message}}` (§9); CORS from `CORS_ORIGINS`; `/api/v1` prefix + healthz; `scripts/export_openapi.py`; boot smoke test |
| 04 | `frontend-scaffolds-theme-codegen` | 01 (codegen step: 03) | pnpm workspace; two Next.js App Router TS-strict apps (client :3000, admin :3001) with MUI + `AppRouterCacheProvider` + `src/theme/theme.ts`; `components/common/` seeded (`Icon` with a11y contract, `PageContainer`); eslint/prettier/vitest parity in both apps; `openapi-typescript` codegen → committed `src/types/generated/schema.d.ts` |
| 05 | `compose-dockerfiles` | 03, 04 | Multi-stage uv `Dockerfile.api`; shared `Dockerfile.web` (build ARG selects app, §3.1); compose with api + admin + client, loopback-only ports, `--profile local-db` (`pgvector/pgvector:pg16`, §9); migration invocation documented. Verify = §10 P1 definition of done |

### Phase 2 — Auth + CMS CRUD (`phase-2-auth-cms-crud/`) — §10 P2, §5.1–5.2, §4.1

| # | Task | Depends on | Scope |
|---|---|---|---|
| 01 | `google-oauth-sessions` | phase-1 | All four §5.1 routes; signed HttpOnly session cookies; `ADMIN_EMAILS` allowlist rejection; soft-deleted-user reactivation on upsert + 401 for soft-deleted sessions (§4.1/§9); `require_admin` dependency producing the principal consumed by admin routes, `/agent/chat`, and MCP actor stamping |
| 02 | `content-tag-services` | phase-1 (∥ 01) | Services: create_draft (slug gen + `-N` collision incl. deleted slugs), get/list/update (`updated_by`/`updated_at`), soft delete (tombstone + chunk removal, one tx); **publish/archive behind an explicit lifecycle seam** (no-op embedder — phase 3 fills it; this resolves the P2-vs-P3 split); tags get-or-create with reactivation + usage counts; stats. Session-first, flush-never-commit, actor as parameter — the exact functions MCP tools wrap in phase 5. §9 tests: slug permanence, tag reactivation, soft-delete invisibility |
| 03 | `admin-rest-routes` | 01, 02 | All nine §5.2 routes with `require_admin`, explicit `operation_id`s, Pydantic DTOs, pagination envelope; 404 semantics for soft-deleted rows; **first committed `openapi.json` baseline + codegen refresh** (standing same-commit gate from here on); §9 `/stats` smoke test |
| 04 | `admin-shell-auth-ui` | p1-04, 01 | MUI AppBar/Drawer shell, thin pages; RTK Query `baseApi` (`credentials:'include'`) + store + Providers; sign-in flow, `/auth/me` guard, logout |
| 05 | `admin-dashboard-list` | 03, 04 | Stats dashboard cards; content list table with status/tag/q filters + pagination; per-domain `injectEndpoints` + tag invalidation; delete confirm dialog ("permanent — no restore", §2.2); `common/` additions: StatusChip, ConfirmDialog, Empty/ErrorState |
| 06 | `admin-editor-transitions` | 03, 04 (∥ 05) | Create/edit screen (markdown body + preview, tag Autocomplete with lowercase-hyphen normalization, immutable slug display); publish/archive/delete transitions per current status; error envelope → snackbar (§9); works unchanged when phase 3 makes publish real (seam is server-side) |

### Phase 3 — Publish pipeline + client content (`phase-3-publish-client-content/`) — §10 P3, §4 lifecycle, §7.1–7.2, §5.3

| # | Task | Depends on | Scope |
|---|---|---|---|
| 01 | `chunking` | phase-1 | §7.1: heading split → ~500-token chunks, 50-token overlap (tiktoken), pure + deterministic, `chunk_index` preserved; §9 chunking unit tests |
| 02 | `embedding-lifecycle` | 01, p2-02 | OpenAI `text-embedding-3-small` behind a protocol seam (fake in tests); fills the phase-2 lifecycle seam: publish / edit-of-published / archive / delete transactions exactly per §4, incl. atomicity + rollback-on-embedding-failure tests; produces the service functions phase-5 tools wrap |
| 03 | `public-content-api` | p2-03 (∥ 01–02) | §5.3 list + detail (published AND non-deleted; deleted slug 404s, never reassigned); public DTOs; baseline + codegen refresh; visibility-matrix tests (draft/published/archived/deleted × list/detail) |
| 04 | `client-content-ui` | p1-04, 03 | **Server components** fetch the public API (SEO matters here; no RTK Query in the client app — recorded in FRONTEND-CONVENTIONS); list + detail pages, `react-markdown` + `remark-gfm` mapped onto MUI Typography; §8 disclaimer footer visible; `notFound()` on 404 |

### Phase 4 — RAG assistant (`phase-4-rag-assistant/`) — §10 P4, §7, §5.3 chat, §8, §9 rate limits

| # | Task | Depends on | Scope |
|---|---|---|---|
| 01 | `retrieval` | p3-02 | §7.3: query embed → HNSW top-6 → threshold filter; **`similarity = 1 − (embedding <=> query)` defined once**; `SIMILARITY_THRESHOLD` from config; §9 similarity conversion pin test + pgvector integration test |
| 02 | `chat-synthesis-sse` | 01 | §7.5 system prompt (verbatim intent: context-only, `[n]` citations, refusal wording, no personalized advice); `POST /public/chat` SSE (`token`/`citations`/`done`/`error`), session get-or-create; content-level citation dedup vs chunk-level persistence (§4 asymmetry, documented in code comments at both shapes); `retrieval_found`/`top_similarity` recording; refusal path; produces shared SSE utilities reused by `/agent/chat` |
| 03 | `rate-limiting` | 02 | §9's three caps (per-min/IP, per-day/session, session-create/IP); in-memory store, injectable clock; 429 + standard envelope, rejected before the stream opens |
| 04 | `seed-content-eval-set` | p3-02 (∥ 01–03) | ~20 original articles (§8: six tags, YAML frontmatter, 3–4 drafts, disclaimer footer); `seed.py` through the real services + real embed pipeline, idempotent; `eval_questions.yaml` authored against these articles (§8.1: ~12 answerable with `expected_slugs`, ~3 uncovered) |
| 05 | `client-chat-ui` | 02, p3-04 | `'use client'` chat island; `useChatStream` (fetch + `ReadableStream` SSE parser); `localStorage` session_id resent per request; numbered `[n]` citations linking to `/content/[slug]`; refusal + 429 states |

### Phase 5 — MCP + agent (`phase-5-mcp-agent/`) — §10 P5, §6, §5.4, §3 exposure rule

| # | Task | Depends on | Scope |
|---|---|---|---|
| 01 | `mcp-server-read-tools` | p2-02, p3-02 | Official Python MCP SDK, in-process (§3); tool pattern: Pydantic-validated args, handler calls services with session + actor; in-process invocation seam for the agent loop; `MCP_HTTP_ENABLED=false` default + admin-auth-when-enabled pin test; `search_content` + `count_content`; **committed `mcp-tools.json` baseline** (standing gate) |
| 02 | `mcp-write-tools` | 01 | The six §6 write tools wrapping existing services: `create_draft`, `edit_content`, `delete_content`, `tag_content`, `publish`, `archive`; actor stamping (§4.1/§6); soft-deleted id → structured not-found; §9 happy + failure test per tool |
| 03 | `agent-loop-endpoint` | 02, p2-01, p4-02 | Hand-rolled OpenAI tool loop (§11 row 7) over the MCP tool schemas; **cap 8** with completed-vs-remaining report (§6); tool error surfaced to the model once, then graceful failure; agent drafts never auto-published; stateless `POST /agent/chat` SSE (§5.4 events, reuses phase-4 SSE utils); statelessness pin test (no rows written) |
| 04 | `admin-agent-panel` | 03, p2-04 | Persistent MUI Drawer chat (§2.2); history in component state, resent whole (§5.4); live `tool_call`/`tool_result` cards interleaved with streamed tokens; on `done` → invalidate Content/Stats/Tags so lists reflect agent writes |

### Phase 6 — Deployment (`phase-6-deployment/`) — §10 P6, §9, §9.1

| # | Task | Depends on | Scope |
|---|---|---|---|
| 01 | `metrics-middleware` | p4-02 | First-token latency on `/public/chat` + request timing; rolling p50/p95 to logs (§9, §9.1); injectable clock; unit-tested percentile math |
| 02 | `aws-deployment` | phases 1–5 | ECR + App Runner (ECS Fargate alternative noted); frontends as containers (§11 row 5); Supabase as deployed DB (§9); prod `CORS_ORIGINS` (no wildcard), Secure cookies, OAuth redirect URIs; deployed checklist: 429 verified live (§10 P6), SSE unbuffered, healthz, seed live |
| 03 | `readme-demo-script` | 02 | README with both DB paths (§9), setup/migrate/seed/run/test, accumulated "Implementation notes"; demo script publish → ask → agent walkthrough (§10 P6); SUGGESTIONS.md tidy |

### Phase 7 — Evaluation & analytics (`phase-7-evaluation/`) — §10 P7, §6, §8.1, §9.1

| # | Task | Depends on | Scope |
|---|---|---|---|
| 01 | `report-content-gaps` | p4-02, p5-01 (∥ 02) | §6 gap query (user messages whose next assistant message in-session has `retrieval_found=false`, newest first); MCP tool #9; `mcp-tools.json` update; §9 tests against seeded rows |
| 02 | `groundedness-harness` | p4-04, p4-02 | Runs `eval_questions.yaml` through the real chat path; answerable: `expected_slugs` ⊆ cited slugs + per-claim support via LLM judge (`gpt-4o-mini`, temp 0 — implementation note); uncovered: refusal + `retrieval_found=false` + zero citations; summary table output (§10 P7) |
| 03 | `metrics-final-verification` | 01, 02, p6-03 | Capture §9.1 metrics into README (docs/chunks counts, 9 tools, groundedness %, p50/p95); full gate run (all suites + lint + compose both profiles + deployed smoke); §10 definition-of-done walk; flip statuses in INDEXes + registry |

### Ordering notes

- Phases run 1 → 7; true cross-phase edges are recorded in task frontmatter with folder-qualified
  ids (e.g. `depends_on: [phase-3-publish-client-content/task-02]`); intra-phase deps use bare `task-NN`.
- Intra-phase parallelism: p1 (04 ∥ 02–03) · p2 (01 ∥ 02; 05 ∥ 06) · p3 (01 ∥ 03) · p4 (04 ∥ 01–03) · p7 (01 ∥ 02).
- Standing gates once they exist: any route change regenerates `openapi.json` + both apps' codegen
  in the same commit (from p2-03); any tool-schema change regenerates `mcp-tools.json` (from p5-01).
- Controller checkpoints (⚠️ in the INDEX): live visual pass after p2-06 (admin app), p4-05 (client
  chat), p5-04 (agent panel).

### PRD coverage cross-check

| PRD item | Owning task(s) |
|---|---|
| §5.1 all 4 auth routes | p2-01 |
| §5.2 all 9 admin routes | p2-03 (publish/archive internals p3-02) |
| §5.3 public content + `POST /public/chat` + session cap | p3-03 · p4-02 · p4-03 |
| §5.4 `/agent/chat` + events | p5-03 |
| §6 tools 1–8 / tool 9 / agent-loop rules | p5-01, p5-02 / p7-01 / p5-03 |
| §7 steps 1–7 | p3-01, p3-02, p4-01, p4-02 |
| §8 + §8.1 seed + eval set | p4-04 |
| §9 CORS/config/envelope/cookies · rate limits · latency middleware | p1-03, p2-01 · p4-03 · p6-01 |
| §9 every listed test | chunking p3-01 · lifecycle+rollback p3-02 · soft-delete visibility p2-02/p3-03/p5-02 · tag reactivation p2-02 · slug permanence p2-02 · similarity pin p4-01 · MCP happy+failure p5-01/02, p7-01 · `/stats` smoke p2-03 |
| §9 local-db profile · §10 DoD + demo | p1-05 · p6-03, p7-03 |

PRD silences resolved as **implementation notes** (per §11 defaults philosophy; none schema/protocol-affecting):
healthz path, pagination envelope field names, pnpm as JS package manager, frontend ports, markdown
renderer, tiktoken for token counting, seed idempotency strategy, 429-before-stream, metrics via
logs only, groundedness judge method.

## 5. Task file format (what each of the 30 files looks like)

```markdown
---
id: task-NN
phase: phase-N-<slug>
depends_on: [task-MM, phase-K-<slug>/task-LL]
status: planned
spec: advisordesk-prd.md §A, §B
---
# task-NN — <imperative title>

## Purpose            what exists after this task; which PRD requirements it discharges; who consumes it
## Context (read ONLY these)    PRD §s, conventions §s, repo paths — a bounded reading list
## Interfaces         Consumes (from earlier tasks) · Produces (later tasks rely on — produce exactly)
## Steps (TDD)        - [ ] RED: failing tests first  - [ ] GREEN: implement  - [ ] baseline/codegen  - [ ] Gates → commit
## Verify             pasteable commands with expected output in comments
## Acceptance         observable facts only
```

Each `00-INDEX.md`: spec pointer (PRD wins on conflict) + conventions pointers, goal paragraph,
**Global Constraints** (feature branch; path-scoped `git add` only; conventional commits; the exact
Python and frontend gate commands; wire-surface same-commit gate; §11 defaults philosophy — raise
schema-affecting questions, log the rest as implementation notes, enhancements → SUGGESTIONS.md),
the task table, ordering rationale, checkpoints, status line.

## 6. Conventions documents (outlines)

**`CONVENTIONS.md`** (Python, apps/api): house style (`from __future__ import annotations`
everywhere, full annotations + docstrings on public symbols, `collections.abc` types) · layering
table + import-linter contracts + the deliberate-violation verification ritual · services rules
(session-first, `flush()` never `commit()`, actor as parameter, typed error family +
`register_error_handlers`, no try/except in routes) · app construction (`create_app` factory,
`app.state`, DB-less build, wiring only in `main.py`, explicit `operation_id` on every route) ·
SQLAlchemy 2.0-only + define-once active-row filter + **Alembic-only DDL** (recorded deviation from
the reference, with the why) · config/secrets (pydantic-settings, §9 roster, tracked `.env.example`
only) · tooling (uv; exact ruff/mypy/import-linter/pytest commands) · tests (throwaway schema via
`alembic upgrade head`, skip-by-fixture without `TEST_DATABASE_URL`, gates-as-tests, no
`__init__.py` in tests, unique basenames) · committed baselines · docker/dev.

**`docs/FRONTEND-CONVENTIONS.md`** (both apps): pnpm workspace, pinned ports, scripts-are-gates
table · **MUI stack** (`@mui/material-nextjs` `AppRouterCacheProvider`, `theme.ts` = the
design-token system; repeated styles become theme variants or `styled()`, not copy-pasted `sx`) ·
folder-per-component + thin `page.tsx` + screens in `components/<domain>/` + colocated VM hooks ·
`components/common/` wraps MUI — call sites never import `@mui/*` (only theme, Providers, common/);
`Icon` a11y contract (label → `role="img"` + aria-label; absent → `aria-hidden`) · `src/types/` as
the sole importer of generated `schema.d.ts`; `as const` unions, no TS enums, no classes · data
fetching split: admin = RTK Query (single `baseApi`, per-domain `injectEndpoints`, tag
invalidation); client = server components for content pages, hand-rolled SSE hooks for chat ·
vitest (node default, per-file jsdom pragma, `globals:false`) · eslint flat + prettier all-keys
explicit · codegen output committed, never hand-edited.

## 7. PRD edits (v1.3 → v1.4, the MUI deviation)

1. Header: `Version 1.3` → `Version 1.4`.
2. §3.1 layout comments: both app lines → `# Next.js 14+ (App Router, TypeScript, Material UI)`.
3. §11 row 6 default → `Material UI (@mui/material + @mui/icons-material + @mui/material-nextjs
   App Router integration, Emotion, createTheme() as the design-token system); minimal clean UI; no
   Tailwind`; alternatives → `Tailwind (+ shadcn/ui) — original default, superseded 2026-07-27`.
4. §14 changelog: new v1.4 bullet (styling switch, owner decision 2026-07-27, no behavioral or API
   change).

## 8. Execution order (once approved)

1. PRD v1.4 edits.
2. `CONVENTIONS.md` + `docs/FRONTEND-CONVENTIONS.md` (so task files can cite section numbers).
3. `docs/plans/README.md` registry.
4. Phase folders 1 → 7: `00-INDEX.md`, then task files per §4's tables.

Verification: file tree matches §3; every `depends_on` resolves to a real file; every INDEX row
links to a real task; every `spec:` §ref exists in the PRD; coverage table §4 holds; no stray
Tailwind references remain in the PRD (`grep -ni tailwind advisordesk-prd.md`).
