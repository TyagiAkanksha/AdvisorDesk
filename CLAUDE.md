# AdvisorDesk — Claude Code Guide

This file is an **index + working rules** only. To keep a single source of truth it points to the
canonical documents instead of restating them.

| Area | Source of truth |
|---|---|
| Product spec (authoritative on any conflict) | [`advisordesk-prd.md`](advisordesk-prd.md) |
| Python house rules (apps/api) | [`CONVENTIONS.md`](CONVENTIONS.md) |
| Frontend house rules (apps/admin + apps/client) | [`docs/FRONTEND-CONVENTIONS.md`](docs/FRONTEND-CONVENTIONS.md) |
| Task system: phase plans + task files | [`docs/plans/README.md`](docs/plans/README.md) |
| Execution ledger (gitignored, durable progress state) | `.superpowers/sdd/progress.md` |

## Working rules for AI-assisted development

These bind every session and every dispatched agent working in this repo.

### Scope & planning

- **Plan Mode first.** Before changing anything non-trivial, read and understand the existing
  code and the relevant PRD/plan sections; produce a plan the owner can review.
- **Break complex work into small tasks.** The unit of work is one `docs/plans/.../task-NN-*.md`
  file (or something equally scoped). Never hand an agent a multi-task blob.
- **Never a bare "implement this."** Every dispatch states HOW: the task brief with exact file
  paths, interfaces, values, and acceptance criteria. Exact values live in the brief, not in
  chat history.

### Agent separation (one responsibility per agent)

- **Test-author, implementer, and reviewer are three separate agents.**
  - The *test-author* writes the task's failing tests (the RED steps) from the brief and proves
    they fail.
  - The *implementer* makes them pass (the GREEN steps). It may add tests, but may not weaken,
    modify, or delete the authored tests without controller approval.
  - The *reviewer* is never the implementer.
- **Fresh agent per task; close instances after an implementation.** No context accumulation
  across tasks — a finished agent's knowledge lives in its report file and the ledger, not in a
  lingering session. Hand artifacts over as files (briefs, reports, review packages), not pasted
  text.
- **Model policy: Sonnet for initial iterations.** Escalate to a more capable model only when a
  task demonstrably needs it (deep design judgment, subtle correctness, the final whole-branch
  review). Record the choice.

### Verification discipline

- **Run the type-checker after every implementation or significant change** — `uv run mypy`
  (apps/api), `pnpm type-check` (each frontend app) — not only at the pre-commit gate.
- **Tests are part of the task. No test means the task is not complete.** TDD is mandatory: RED
  evidence before GREEN, both recorded in the task report.
- Full gate sets (see the conventions docs) run clean before every commit.

### Code review

- **Every implementation gets a real review — never a rubber stamp.** The reviewer verifies
  against the brief with evidence (file:line), covering all five dimensions: functionality,
  tests, maintainability, coupling, and overall design.
- Critical/Important findings get a fix round and a re-review; Minors are ledgered and triaged
  at the whole-branch final review. Findings that conflict with the plan's own text go to the
  owner — the plan does not grade its own work.

### Structure (details in the conventions docs)

- Keep files small; each function or component serves one purpose.
- UI components stay dumb: they render props and raise events; business logic lives outside them.
- No tight coupling between modules — no exceptions. The backend enforces this with
  import-linter contracts; the frontend with the layering rules in FRONTEND-CONVENTIONS.
