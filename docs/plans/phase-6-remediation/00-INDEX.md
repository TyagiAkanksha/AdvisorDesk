# Phase 6R — Whole-Repo Review Remediation

Source: the 2026-08-30 whole-repo standards review — findings in
`.superpowers/sdd/reports/p6-whole-repo-review.md`, batch plan in
`.superpowers/sdd/reports/p6-remediation-plan.md` (both gitignored; WR-ids below refer to them).
Owner approved the remediation plan 2026-08-31 ("go"). Branch: `feat/phase-6-deployment`
(continues the open phase-6 line; the pre-existing uncommitted docs==reality pass stays owner-review-pending
and MUST NOT be touched by any task here — path-scoped `git add` only, per CONVENTIONS §12).

## Batch → task map

| Batch | Task file | WR-ids | Status |
|---|---|---|---|
| B0 credential rotation | owner-executed runbook (remediation plan Batch 0) — no task file | WR-01 | ⏳ owner |
| B2 process backstop | `task-01-root-gates-and-hooks.md` | WR-16 (scripts limb), WR-74 | planned |
| B2 process backstop | `task-02-ci-workflow.md` | WR-16, WR-17, WR-50, WR-51, WR-52 | planned |
| B1 security | `task-03-bearer-lifecycle-and-audit-log.md` (to be authored) | WR-02, WR-05 | pending |
| B1 security | `task-04-prod-config-in-repo.md` (to be authored; needs files fetched from the box via SSM) | WR-03, WR-14 (restore-target limb), WR-70 | pending |
| B1 security | `task-05-security-headers.md` (to be authored; depends on task-04) | WR-04 | pending |
| B1 security | `task-06-ratelimit-memory-bound.md` (to be authored) | WR-06 | pending |
| B3 code/arch | task-07.. (import contracts WR-07, held txn WR-09, agent-route tests WR-10, tag-drop WR-11, sse package WR-12, aria WR-13, EC2 reproducibility WR-14, monitoring WR-15, README+demo WR-18) | — | pending |
| B4 owner decisions | batched at next checkpoint (8 items, remediation plan Batch 4) | — | pending |
| B5 minors | 2–3 cleanup tasks after CI exists | — | pending |

## Sequencing (from the approved plan)

B0 now (owner) → task-01 → task-02 (CI is the forcing function; land before B1/B3 fixes) →
B1 and B3 in parallel riding CI → B4 decisions at the next owner checkpoint → B5 opportunistic.

## Execution model

Three-agent SDD per CLAUDE.md with the seven standing rules from the ledger (env-export verbatim,
prettier/ruff-clean authored tests, pinned-file stop rule, live-server evidence where RSC is touched,
verbatim finding persistence, cold-cache ruff in final reviews, sha256 re-verification).
Deviation for config-only tasks (01/02): no test-author (nothing pytest-able exists before the config
does — p6-t02 doc-task precedent); instead each brief pins explicit local verification commands as the
RED/GREEN equivalent, and the reviewer verifies against those. One reviewer covers tasks 01+02
together (one cohesive process-backstop change).
