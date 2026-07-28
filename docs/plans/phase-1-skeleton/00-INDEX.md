# phase-1-skeleton — Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Implement with superpowers:test-driven-development;
> claim completion only via superpowers:verification-before-completion.

**Spec:** `advisordesk-prd.md` §10 Phase 1 — **authoritative for every table/endpoint/behavior in
this phase.** Primary sections: §3.1 (layout), §4 + §4.1 (schema), §9 (env roster, local-db
profile, tests). Task files repeat what an implementer needs; on any conflict the PRD wins.
**Conventions:** `CONVENTIONS.md` (Python) · `docs/FRONTEND-CONVENTIONS.md` (both Next.js apps).

**Goal:** the §10 Phase 1 definition of done — monorepo scaffold in place, FastAPI app boots,
schema migrated via Alembic, `docker compose up` runs (including the `local-db` profile), health
endpoint answers — plus the tooling gates (ruff/mypy/import-linter/pytest, eslint/prettier/vitest)
that every later phase's Global Constraints assume.

**Architecture:** PRD §3.1 monorepo (two Next.js apps + one FastAPI backend + Postgres/pgvector).
Backend layering per CONVENTIONS.md §2 (routes → services → models, import-linter-enforced);
`create_app()` factory with DB-less construction; Alembic-only DDL. Frontends per
FRONTEND-CONVENTIONS.md: MUI theme as design tokens, folder-per-component, openapi-typescript
codegen boundary.

**Tech Stack:** Python 3.11+/uv/FastAPI/SQLAlchemy 2.0/Alembic/pgvector · pnpm/Next.js (App
Router, TS strict)/@mui/material/@mui/material-nextjs · Docker Compose (`pgvector/pgvector:pg16`
behind `--profile local-db`).

## Global Constraints

Every task's requirements implicitly include this section.

- Work on the feature branch (`v1`); **path-scoped `git add` only** — never `git add .` / `-A`;
  never stage `.env` or secrets. Conventional commits with scope + task id (CONVENTIONS.md §12),
  trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Python gates before every commit touching `apps/api`** (run from `apps/api/`):
  `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy` · `uv run lint-imports` ·
  `uv run pytest -q` — all clean. DB tests skip without `TEST_DATABASE_URL`; a skip is recorded,
  never a pass.
- **Frontend gates before every commit touching an app:** `pnpm -C apps/<app> lint`,
  `type-check`, `test` — all clean.
- **PRD contract (§ implementer contract):** ambiguities resolved per §11 defaults philosophy →
  note in README "Implementation notes" and continue; schema- or protocol-affecting questions are
  RAISED, not guessed. Enhancements → `SUGGESTIONS.md`, never scope expansion.

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 1 | Repo scaffold + Python tooling gates | `task-01-repo-scaffold-python-tooling.md` | — |
| 2 | DB models + Alembic baseline migration | `task-02-db-models-alembic.md` | task-01 |
| 3 | App factory, config, error envelope, healthz | `task-03-app-factory-health-errors.md` | task-02 |
| 4 | Frontend scaffolds, MUI theme, codegen wiring | `task-04-frontend-scaffolds-theme-codegen.md` | task-01 (codegen step: task-03) |
| 5 | Compose + Dockerfiles (incl. `--profile local-db`) | `task-05-compose-dockerfiles.md` | task-03, task-04 |

Order: 1 → 2 → 3 → 5, with 4 parallel to 2–3 (its final codegen step waits on task-03's
`openapi.json` export). Rationale: task-01 pins the package layout and gate commands every other
task's Steps assume; task-02 pins model names the factory's session dependency and all later
services import; task-03 pins `create_app`/`Settings`/error-envelope names used by every route
task in phases 2–7.

## Status

planned — snapshot only; git history is authoritative.
