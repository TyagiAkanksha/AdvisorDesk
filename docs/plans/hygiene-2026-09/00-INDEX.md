# Hygiene batch 2026-09 — the phase-8 "ride" list — Implementation Plan (ALL TASKS DONE — final review clean)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Every task runs as a **three-agent SDD task**
> (test-author → implementer → reviewer; reviewer ≠ implementer — `CLAUDE.md`). Reviewers are
> Sonnet unless the task's frontmatter says `review: opus`; the whole-branch final review is Opus.

**Spec:** this file is the spec — each task below quotes the reviewer finding it closes
verbatim from the phase-8 ledger, and that finding is the authority on intent. Conventions:
[`docs/FRONTEND-CONVENTIONS.md`](../../FRONTEND-CONVENTIONS.md) (tasks 01–07, 09),
[`CONVENTIONS.md`](../../../CONVENTIONS.md) (task 08). Design principles from
[`phase-8-ui-polish/DESIGN.md`](../phase-8-ui-polish/DESIGN.md) §2 still bind any visible change.

**Goal:** close every Minor that the phase-8 sub-phase C final review and the t24 review
deferred ("RIDE") — no new features, no visual redesign — in one branch (`chore/hygiene-ride`),
one PR, one deploy of all three images.

**Architecture:** nothing structural changes. The batch dedups one helper, moves one wrapper
boundary (`RequireSession` inside `AppShell`), splits two oversized admin hooks/screens along
their existing seams, tidies test harnesses, drops one dev dependency, and adds one lint guard.
Public component/hook result shapes stay identical unless a task says otherwise.

**Tech stack:** unchanged — Next.js 16 App Router, React 19, MUI 9, vitest 4 + RTL (jsdom),
ESLint 9 flat config, Vite 8 (via vitest), FastAPI + pytest (task 08 only).
**No new runtime dependencies. One dev dependency removed (`vite-tsconfig-paths`).**

## Global Constraints

Every task's requirements implicitly include this section.

- **TDD, three agents.** The test-author writes the task's failing tests and proves they fail
  (RED evidence = command + pasted failure lines in the report); the implementer makes them pass
  and may add tests but may not weaken, modify, or delete an authored test without controller
  approval. Where a task says a pin must be *rewritten* (a behaviour is deliberately changed),
  the test-author does the rewrite and the task file names the pin. Any other pre-existing test
  is a **stop rule**: if it fails, stop and report — do not edit it.
- **Gates.** Frontend: `pnpm -C apps/<app> type-check`, `pnpm -C apps/<app> lint`,
  `pnpm -C apps/<app> format:check` (or `prettier --check`), and the suite via
  `cd apps/<app> && npx vitest run [pattern]` — **`pnpm -C apps/<app> test -- <filter>` drops
  the filter**, use `npx vitest run` for focused runs. API: `cd apps/api && uv run ruff check .
  && uv run mypy && uv run pytest tests/<file>` — export **only** `TEST_DATABASE_URL` (never
  `source .env`: it leaks `MCP_HTTP_ENABLED` and breaks `test_oauth_discovery.py`). Never print
  `.env` values.
- **Boundaries.** `src/components/common/` is the only MUI importer (lint-enforced); UI components
  render props and raise events, logic lives in hooks/`lib/`; copy strings live in
  `src/lib/copy.ts`; every `common/` hook re-exported from the barrel into a Server Component
  carries `'use client'`. Twin files across apps (`theme.ts`, `Markdown`, `lib/markdown.ts`, and
  task 02's new `lib/href.ts`) stay byte-identical and twin-guarded.
- **Screenshots** only where a task changes something visible (task 05 only).
- **Commits** on `chore/hygiene-ride`, conventional prefix (`refactor(admin): …`,
  `chore(client): …`, `test(api): …`), one commit per RED step and one per GREEN step where
  practical. Never commit to `main`.

## Task table

| # | File | Closes | Apps | Review |
|---|---|---|---|---|
| 01 | [`task-01-chat-welcome-label.md`](task-01-chat-welcome-label.md) | t24 M3 (welcome region label echoes the h1), t24 M4 (two expressions for one condition) | client | sonnet |
| 02 | [`task-02-is-internal-href.md`](task-02-is-internal-href.md) | FINAL(C) X8 / t14 M2 (`isInternalHref` ×5) | admin + client | sonnet |
| 03 | [`task-03-empty-state-live-region.md`](task-03-empty-state-live-region.md) | t23 M5 (buttons inside `EmptyState`'s `role="status"` live region) | admin + client | sonnet |
| 04 | [`task-04-drop-vite-tsconfig-paths.md`](task-04-drop-vite-tsconfig-paths.md) | t22 M2 (`vite-tsconfig-paths` deprecation banner) | admin + client | sonnet |
| 05 | [`task-05-shell-outside-session-gate.md`](task-05-shell-outside-session-gate.md) | FINAL(C) X4 (`RequireSession`/`AppShell` layout inversion — shell-less spinner) | admin | opus |
| 06 | [`task-06-content-list-tidy.md`](task-06-content-list-tidy.md) | t18 M1/M2/M6/M7 | admin | opus |
| 07 | [`task-07-editor-hook-tidy.md`](task-07-editor-hook-tidy.md) | t19 M1/M2/M3, t20 M4 | admin | opus |
| 08 | [`task-08-oauth-discovery-env-isolation.md`](task-08-oauth-discovery-env-isolation.md) | t13 minor (`test_oauth_discovery.py` bare `Settings()`) | api | sonnet |
| 09 | [`task-09-testing-import-lint-guard.md`](task-09-testing-import-lint-guard.md) | FINAL(C) RIDE "testing-import lint guard" | admin | sonnet |

Order: 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 (all independent; 04 before 09 so the
ESLint change lands on the final vitest config; 06 and 07 are the two largest and go last among
the admin tasks so the shared-harness work in 07 sees the final `EmptyState`).

## Plan-time rulings (controller)

- **Task 01 label.** t24 M3 was parked as an owner call; the owner approved the hygiene batch
  as presented with the default **"Suggested questions"**. Ruling: ship the default.
- **Task 04 and task 08 have no meaningful RED step** (a config swap; an env-isolation fixture).
  Task 04's "test" is the full suite of both apps resolving `@/` imports without the plugin.
  Task 08 does have a RED: the test currently fails when `MCP_HTTP_ENABLED=true` is exported,
  and must pass after. Both still get a reviewer.
- **Task 05 trade-off.** A signed-out visitor to an `(app)` route now sees the empty shell
  chrome for the instant before the `/signin` redirect (today: a bare spinner). Accepted — the
  common case (signed-in hard load / refresh) stops flashing a shell-less spinner on every page.
- **Task 09 is admin-only.** `apps/client` has no `src/testing/` directory, so a client guard
  would be inert (YAGNI); add it when the directory appears.
- **Dropped from the ride list**, with reasons: `test_oauth_discovery.py` docstring wrap
  (openapi churn — already dropped at FINAL(C)); DESIGN.md §5's `EditorForm`-takes-the-hook-
  result ruling is not reopened by task 07.

## Whole-branch final review (after 09)

- [x] Opus reviewer on the full `main..chore/hygiene-ride` diff — "Ready with one fix wave"
      (0 Critical, 2 Important — both in the t09 lint composition — 3 Minor); gates, builds,
      twins, boundary, openapi, lockfile all independently verified; full API suite with the DB
      747 passed / 1 skipped.
- [x] One fix wave (`e63a3b8`, 15 of 16 items; B7 "gate the Agent button on `me`" rides — three
      pre-existing shell tests query it pre-session) + one scoped Opus re-review: CLEAR TO MERGE.
- [x] PR #36 merged → main `387af39`; `push_ecr.sh` pushed api/admin/client:387af39; SSM
      rollout on the box (backup `docker-compose.yml.bak-bda5084`, alembic no-op, `up -d`);
      live-verified over HTTPS (healthz, 27 public items, callback bad state → 303, admin
      /signin copy + /content prerender carries the shell with one `<main>` + 404, client / +
      /chat + ?tag=, welcome region "Suggested questions", grounded chat SSE 91 tokens +
      citations + done). Compose bump PR follows. **PROD == MAIN at 387af39.**

## Ride list after this batch (ledger `.superpowers/sdd/hygiene-2026-09/progress.md`)

- Agent button live pre-auth (gate on `me`; needs the three AppShell tests to await the session).
- t05 M4: mobile cold load prerenders the 240 px permanent drawer until hydration — owner eyeball
  on a phone; MUI `ssrMatchMedia` if it bothers.
- t03 M1: `getAllByRole('button', { name: 'Clear filters' })[1]` is render-order coupled.
- Lint guard latents: a future `common/**/testing/**` file cannot import `@/testing/*`; the
  `**/testing/**` glob would also catch npm paths like `rxjs/testing`.
