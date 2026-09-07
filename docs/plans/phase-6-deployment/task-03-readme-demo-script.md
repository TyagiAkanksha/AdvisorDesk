---
id: task-03
phase: phase-6-deployment
depends_on: [task-02]
status: built
spec: advisordesk-prd.md §9 (local development), §10 Phase 6 + DoD, §1 implementer contract
---

# task-03 — README and the demo script

## Goal

A stranger can follow the README end-to-end (§10 definition of done, first pass): setup on either
DB path, migrate, seed, run, test, deploy — and walk the demo script (publish → ask → agent
command). The accumulated "Implementation notes" ledger is complete and `SUGGESTIONS.md` is
tidied.

## Context (read ONLY these)

- `advisordesk-prd.md` §9 "Local development" (both DB paths documented, Supabase default), §10
  Phase 6 + definition of done, implementer contract point 2 (Implementation notes).
- `infra/deploy/*` (task-02); every "implementation note" flagged in phases 1–6 task files.

## Files

- Modify: `README.md` (full rewrite of the stub)
- Create: `docs/DEMO.md`
- Modify: `SUGGESTIONS.md` (tidy accumulated entries)

## Interfaces

- **Consumes:** everything shipped in phases 1–6.
- **Produces:**
  - `README.md` sections: What is AdvisorDesk (one paragraph + the §3 diagram) · Quickstart
    (Supabase path AND `--profile local-db` path: env → migrate → seed → run) · Development
    (gate commands for api/admin/client; test-DB setup) · Architecture map (§3.1 tree with
    one-liners) · Deployment (pointer to `infra/deploy/`) · **Implementation notes** (the §11
    defaults ledger — healthz path, pagination envelope, pnpm, ports, tiktoken, markdown
    renderer, seed idempotency, 429-before-stream, metrics-as-logs, groundedness judge method,
    day-bucket reset) · Metrics (placeholder table phase-7 task-03 fills).
  - `docs/DEMO.md` — the §10 walkthrough with exact clicks/commands and expected outcomes:
    1) admin: create + publish an article (real embed); 2) client: ask a question it answers →
    streamed cited answer, click the citation; 3) ask an uncovered question → refusal;
    4) agent panel: "Draft an article on X and tag it Y" → watch tool events → the §6 draft rule
    (not published); 5) "How many published pieces on tax-planning?" → count.
  - `SUGGESTIONS.md` — deduplicated enhancement list (never scope).

## Steps (TDD)

*(Docs task — the "test" is a clean-room walkthrough.)*

- [ ] **Step 1: Write the README** per the section list; every command copy-pasteable; both DB
  paths verified as written by actually running them.
- [ ] **Step 2: Write `docs/DEMO.md`**; run the full demo against the deployed stack once and
  against local-db once; fix any step that didn't match reality.
- [ ] **Step 3: Clean-room check** — fresh clone in a temp dir, follow README only (local-db
  path): reach a running stack with seeded content and a passing gate run. Record the elapsed
  time in the README's Implementation notes.
- [ ] **Step 4: Tidy `SUGGESTIONS.md`**; cross-check every task file's "implementation note"
  entries landed in the README ledger.
- [ ] **Step 5: Commit:** `docs: readme + demo script (phase-6 task-03)`

## Verify

```bash
git clone . /tmp/advisordesk-cleanroom && cd /tmp/advisordesk-cleanroom
# follow README quickstart (local-db) verbatim:
docker compose -f infra/docker-compose.yml --profile local-db up -d
docker compose -f infra/docker-compose.yml run --rm api uv run alembic upgrade head
docker compose -f infra/docker-compose.yml run --rm api uv run python -m app.seed
curl -s localhost:8000/api/v1/public/content | head -c 200   # seeded list
# then walk docs/DEMO.md end to end
```

## Acceptance

- Clean-room clone reaches a working seeded stack using README instructions alone (§10 DoD first
  pass; final walk happens in phase-7 task-03).
- Demo script matches reality step-for-step on both local and deployed stacks.
- Implementation-notes ledger is complete; SUGGESTIONS.md contains suggestions only.
