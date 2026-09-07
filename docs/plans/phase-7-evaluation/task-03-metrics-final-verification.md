---
id: task-03
phase: phase-7-evaluation
depends_on: [task-01, task-02, phase-6-deployment/task-03]
status: built
spec: advisordesk-prd.md §9.1, §10 (definition of done)
---

# task-03 — Metrics capture and the definition-of-done walk

## Goal

The §9.1 metrics are captured into the README's Metrics section with real recorded values, every
gate across the repo runs green in one recorded pass, the demo script is walked end-to-end on the
deployed stack, and all plan statuses flip to reflect reality. This closes the build: "a stranger
can follow the README, run the demo script end to end, and every capability described in this
document works as specified."

## Context (read ONLY these)

- `advisordesk-prd.md` §9.1 (the four metrics) + §10 definition of done.
- `README.md` Metrics placeholder (p6-t03); the p7-t02 recorded harness output; p6-t01's
  `chat_latency` log line; p6-t02's `VERIFY.md`.

## Files

- Modify: `README.md` (fill Metrics), `docs/plans/README.md` + all seven `00-INDEX.md` + task
  frontmatter `status:` fields (flip to `built`)
- Create: `docs/plans/phase-7-evaluation/verification-record.md` (the pasted real outputs)

## Interfaces

- **Consumes:** everything. **Produces:** the finished, verified, honestly-labeled repo.

## Steps (TDD)

*(Closing gate — every step pastes REAL output into `verification-record.md`; no claim without
evidence, per superpowers:verification-before-completion.)*

- [ ] **Step 1: Metrics capture (§9.1)** into README:
  - seeded documents + chunks: `SELECT count(*) FROM content; SELECT count(*) FROM chunks;` on
    the deployed DB;
  - MCP tools: `python -c "import json;print(len(json.load(open('mcp-tools.json'))))"` → 9
    (8 core + report_content_gaps);
  - groundedness: the p7-t02 summary line from a fresh run;
  - p50/p95 first-token: grep the latest `chat_latency` line from deployed logs after the demo
    walk.
- [ ] **Step 2: Full gate run**, all pasted:
  `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy &&
  uv run lint-imports && TEST_DATABASE_URL=... uv run pytest -q` ·
  `pnpm -C apps/admin lint && pnpm -C apps/admin type-check && pnpm -C apps/admin test` · same
  for `apps/client` · `git diff --exit-code apps/api/openapi.json apps/api/mcp-tools.json` ·
  both compose profiles boot.
- [ ] **Step 3: Definition-of-done walk:** fresh clean-room clone follows README (local-db
  path) to a working stack; then walk `docs/DEMO.md` on the DEPLOYED stack end to end. Record
  outcomes step-by-step.
- [ ] **Step 4: Cross-check §2.2** — every user story demonstrably works; note where each was
  proven (test name or demo step).
- [ ] **Step 5: Flip statuses** — task frontmatter, INDEX Status lines, registry table → `built`;
  the snapshot disclaimer stays.
- [ ] **Step 6: Commit:** `docs: metrics + definition-of-done verification record (phase-7 task-03)`

## Verify

```bash
grep -A6 "## Metrics" README.md          # four real values, no placeholders
grep -rn "status: planned" docs/plans/    # empty
cat docs/plans/phase-7-evaluation/verification-record.md | head -40  # real pasted output
```

## Acceptance

- README Metrics table holds four real measured values (§9.1).
- `verification-record.md` contains genuine command output for every gate, the clean-room
  clone, and the full deployed demo walk — the §10 definition of done, evidenced.
- No plan file claims a status its evidence doesn't support.
