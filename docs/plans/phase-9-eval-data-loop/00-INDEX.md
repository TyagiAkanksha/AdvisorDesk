# Phase 9 — Evaluated, self-improving loop + designed corpus — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Every task runs as a **three-agent SDD task**
> (test-author → implementer → reviewer; reviewer ≠ implementer — `CLAUDE.md`). Reviewers are
> Sonnet unless the task's frontmatter says `review: opus`; the whole-branch final review is Opus.

**Spec:** [`docs/plans/phase-9-eval-data-loop/DESIGN.md`](DESIGN.md) — authoritative on any
conflict with this plan (owner-approved 2026-09-12). Product spec: [`advisordesk-prd.md`](../../../advisordesk-prd.md).
Conventions: [`CONVENTIONS.md`](../../../CONVENTIONS.md) (apps/api), [`docs/FRONTEND-CONVENTIONS.md`](../../FRONTEND-CONVENTIONS.md)
(the feedback UI task only).

**Goal:** by ~2026-09-22, AdvisorDesk can show — with persisted data, not slides — weak queries
detected and classified, a failure cause per failed eval question, a proposal that becomes a
draft, and an eval harness (answers *and* agent trajectories, judged by a calibrated judge,
reported with run-to-run spread) that gates acceptance of that fix. On a corpus a technical
audience can judge live.

**Architecture:** one additive migration (`0009_eval_and_feedback`) adds the feedback/latency
columns and the `eval_runs` / `eval_results` / `content_proposals` tables. The harness
(`app/eval/groundedness.py`) stays pure and grows metrics; persistence and comparison live in
`app/services/eval_runs.py` (reachable from MCP under the import-linter contracts). Weak-query
classification reuses `content_gaps()`'s pairing. Content is authored as seed markdown files with
their eval questions, fact-checked against primary sources, and published to prod via MCP.

**Tech stack:** unchanged — FastAPI, SQLAlchemy 2 + Alembic, pgvector, OpenAI (`gpt-4o-mini`
answerer, `gpt-4o` judge, `text-embedding-3-small@1024`), pytest with throwaway schemas; Next.js
16 / MUI 9 for the feedback UI. **No new runtime dependencies** (argparse is stdlib; RAGAS is a
one-off dev cross-check, not a dependency).

## Global Constraints

Every task's requirements implicitly include this section.

- **TDD, three agents** (CLAUDE.md, CONVENTIONS §10): the test-author writes the failing tests
  and proves they fail (RED evidence = command + pasted failure lines); the implementer makes
  them pass and may add tests but never weakens/modifies/deletes an authored test without
  controller approval; any other pre-existing test that fails is a **stop rule**.
- **Gates before every commit** (apps/api): `uv run ruff check --no-cache . && uv run ruff format
  --check . && uv run mypy && uv run lint-imports && uv run pytest -q` with **only**
  `TEST_DATABASE_URL` exported (from the ROOT `.env` via `grep`/`cut` — never `source .env`,
  never print its values). Frontend tasks: `pnpm -C apps/client type-check && lint &&
  format:check && (cd apps/client && npx vitest run)`.
- **Wire-surface baselines (CONVENTIONS §8):** any route change regenerates
  `apps/api/openapi.json` + both apps' `schema.d.ts` in the same commit; any MCP tool change
  regenerates `apps/api/mcp-tools.json` and its baseline test in the same commit.
- **Schema parity:** `tests/test_models_schema.py` compares ORM metadata with the migrated
  schema (incl. server defaults) — every column exists identically in the model and in `0009`;
  enums are `text` + `CheckConstraint` (like `Content.status`), never Postgres ENUM types.
- **Settings zero-env (CONVENTIONS §5):** every new setting has a default; `Settings()` with no
  env still constructs. New settings: `judge_model: str = "gpt-4o"`.
- **Import-linter contracts** (`apps/api/pyproject.toml`): `app.services` never imports
  `app.rag`/`app.eval`; `app.mcp` imports `app.services` only; the harness (`app.eval`) may
  import `app.rag` and `app.services`. Put shared code where the contracts allow.
- **Judge determinism:** every judge call is `temperature=0`; the answerer is
  `temperature=0` (closeout 2026-09-11). Seeded fixtures in tests; no real network in unit tests
  (fake embedder/LLM/judge protocols already exist in `tests/test_groundedness.py`).
- **Never touch prod data from tests.** DB tests use the throwaway-schema fixture. Prod changes
  happen only through the CMS/MCP publish path or the documented runbook.
- **Content rules (DESIGN §C):** frontmatter `title`/`tags`/`status`; footer line verbatim
  `Sample content for demonstration purposes — not financial advice.`; filename = slugified
  title; tag vocabulary = the six PRD tags + `equity-compensation`, `our-firm`, `north-carolina`
  (extend the `test_seed.py` pin in the same commit); real sourced rules, fictional firm
  (**Queen City Wealth Planning**); "_Current as of 2026-09_" line; a `## Sources` section.
- **Commits** on `feat/eval-data-loop` only (never `main`), conventional prefixes, RED and GREEN
  commits per task where practical.

## Task table

| # | File | Step (DESIGN) | Review |
|---|---|---|---|
| 01 | `task-01-migration-0009-and-signals.md` | A + migration: `feedback`, `latency_ms`, `eval_runs`, `eval_results`, `content_proposals` models + migration; `citations.similarity`; latency written | opus |
| 02 | `task-02-feedback-endpoint.md` | A: `POST /public/chat/{message_id}/feedback` + `openapi.json` + codegen | sonnet |
| 03 | `task-03-eval-persistence-and-compare.md` | B1: `services/eval_runs.py` (record_run, corpus_fingerprint, compare_runs, latest_runs); harness argparse `--label/--questions/--no-persist/--compare-to/--runs`; `EvalRow` + `top_similarity`/`answer_text`; stability summary | opus |
| 04 | `task-04-eval-yaml-v2.md` | B2: optional `class`/`persona`/`expected_chunks`/`reference_answer`; loader + `test_seed.py` pins; `expected_chunks` resolution by heading | sonnet |
| 05 | `task-05-metrics-v2.md` | Approach: recall@k / precision@k / MRR; answer-relevance, context-precision, context-recall rubric judges; `judge_model` setting; per-class rollups | opus |
| 06 | `task-06-failure-taxonomy.md` | Approach: per-failed-question cause (`retrieval_miss` / `corpus_gap` / `threshold_refusal` / `generation_unfaithful` / `judge_disagreement`) persisted on `eval_results`; distribution in the report | sonnet |
| 07 | `task-07-agent-trajectory-suite.md` | Approach: `seed/agent_tasks.yaml` loader; recording tool wrapper around the real agent loop on a scratch schema; task success / tool precision-recall / steps / loops; persisted as `eval_runs.kind='agent'` | opus |
| 08 | `task-08-judge-scorecard.md` | Approach: `seed/judge_labels.yaml` loader; κ vs human labels; self-consistency ×3; position/verbosity spot-check; `python -m app.eval.judge_scorecard` report; unlabelled-rows exporter for the labelling session | sonnet |
| 09 | `task-09-baseline-runs.md` | B3: 3× harness on the current corpus, persisted; README/verification-record note retiring 58.8% | sonnet |
| 10–13 | `task-10..13-corpus-wave-1-*.md` | C: 16 articles in four batches (4 each) with their eval questions; fact-check reports; seed + prod publish | opus (batch reviews) |
| 14 | `task-14-golden-set-persona-questions.md` | B2: the ~15 persona-first questions + class balance to 80; agent tasks file; labelling-session export | sonnet |
| 15 | `task-15-weak-queries.md` | D: `weak_queries()` + grouping + `report_weak_queries` MCP tool (+ `mcp-tools.json`) | opus |
| 16 | `task-16-proposals.md` | D: `services/proposals.py`, four MCP tools, acceptance gate | opus |
| 17 | `task-17-feedback-ui.md` | A/D2: client 👍/👎 under assistant bubbles | sonnet |
| 18 | `task-18-replay-and-rehearsal.md` | C4 + demo: traffic replay against prod, before/after run ids, run sheet incl. the "rejected its own fix" rehearsal | sonnet |

Task files are written in batches as the phase advances (01–09 first; 10–14 after the harness
lands so the content authoring can run the real metrics; 15–18 last). Order of execution: 01 →
02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → (10–14 in parallel with 15–16) → 17 → 18.

## Plan-time rulings (controller)

- **Task 04/05 split:** the YAML loader + `expected_chunks` resolution (04) lands before the
  metrics that consume them (05), so 05's tests can use real fixtures.
- **`eval_runs.kind`** (`answer` | `agent`) is added to the table in task 01 so the agent suite
  (07) needs no second migration — DESIGN's "one migration" rule.
- **`content_proposals` is created in 01** and left inert until 16 (DESIGN §D).
- **Judge scorecard labels:** the harness writes an unlabelled `seed/judge_labels.pending.yaml`
  (task 08); the owner and Abhishek fill `human_verdict`; the labelled file is committed as
  `seed/judge_labels.yaml`. Until then the scorecard reports self-consistency only.
- **RAGAS cross-check** is a one-off script run recorded in the verification record, not a
  task (cut first per DESIGN).
- **Cut order** (DESIGN): RAGAS cross-check → corpus wave 2 → feedback UI (17) → proposal tools
  (16; table stays) → spot-checks in 08 → `latency_ms` writes.

## Whole-branch final review (after 18)

- [ ] Opus reviewer on `main..feat/eval-data-loop`; API gates incl. `lint-imports`; both
      frontend gate sets; `next build` (client); `openapi.json`/`mcp-tools.json` baselines
      regenerated; migration 0009 round-trip; seed on a scratch DB; harness `--runs 3`; agent
      suite 10/10 scored; scorecard report; loop rehearsal recorded.
- [ ] One fix wave, one scoped re-review.
- [ ] PR → merge → deploy (0009 additive: migrate first, then `up -d`) → publish wave 1 on prod
      via MCP → baseline runs against prod-shaped data → run sheet.
