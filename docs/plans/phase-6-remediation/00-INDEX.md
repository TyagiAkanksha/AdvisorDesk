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
| B0 credential rotation | owner-executed runbook (remediation plan Batch 0) — no task file | WR-01 | ❎ DECLINED by owner 2026-08-31 ("dev project") — accepted risk, runbook stands if revisited |
| B2 process backstop | `task-01-root-gates-and-hooks.md` | WR-16 (scripts limb), WR-74, **WR-83** | ✅ df4552a (review r1 clean for t01) |
| B2 process backstop | `task-02-ci-workflow.md` | WR-16 (incl. its mass-skip + codegen sub-items), WR-17, WR-50, WR-52 — **NOT WR-51** (separate untouched finding; commits 83d111f/19dccb1 mis-cite it, correction of record here per reviewer I4) | ✅ 19dccb1 + fix r1 36bcbc6; confirm pass APPROVED (Spec PASS / Quality Approved, 0 C/I; 14 Minors ledgered in `reports/p6r-t01t02-review.md`) |
| — WR-51 ownership (was un-owned per confirm-pass M14) | both limbs → **B5 cleanup**: (a) MCP bearer DB-down envelope test (t04-M6), (b) p6-t05 M9 duplicate-coverage trim; 6R-03's reviewer asked to note if (a) falls out of that task's new tests naturally | WR-51 | routed |
| B1 security | `task-03-bearer-lifecycle-and-audit-log.md` | WR-02 (revocation half), WR-05 | ✅ f189453 + fix r1 3652adb; confirm pass APPROVED (0 C/I; log-leak mutants M12/M13 now killed; 8 Minors ledgered incl. M4 cookie-replay-unaudited, M5→B4-item-9, M6, M10) |
| B1 security | `task-04-prod-config-in-repo.md` | WR-03, WR-14 (restore-target limb), WR-70 (staged) | ✅ d091e11 + fix r1 0aefdd0; confirm pass APPROVED (comment-aware header_up pin mutation-proven) |
| B1 security | `task-05-security-headers.md` (depends on task-04 ✅) | WR-04 | ✅ f386d20 (RED ffc7f18); review APPROVED first round, 0 findings (HSTS apex-scope safe, live curl verified, CSP-content deferred to follow-up) |
| B1 security | `task-06-ratelimit-memory-bound.md` | WR-06 (per-minute limb) | ✅ 768324a + fix r1 be12475; confirm pass APPROVED (hard-cap LRU, memory flat ~17 MiB under 300k-IP flood; self-eviction bypass dominated ~2000:1; LRU-recency mutant now killed). Per-day limb → B4 item 10 |
| B3 code/arch | task-07.. (import contracts WR-07, held txn WR-09, agent-route tests WR-10, tag-drop WR-11, sse package WR-12, aria WR-13, EC2 reproducibility WR-14, monitoring WR-15, README+demo WR-18) | — | pending |
| B4 owner decisions | batched at next checkpoint (8 items, remediation plan Batch 4) + TWO new residual-scope items surfaced during B1 review: (9) WR-02 residual — bearer token EXPIRY + ADMIN_EMAILS re-check on resolve (t03 closed the logout-revocation half; expiry/allowlist halves were out of the brief's scope, review M5); (10) WR-06 residual — per-day `_session_create_counts` still grows ~144 B/IP within a day (~137 MiB/1M IPs), rollover-only by design pin 2 (t06 review M-2); recommend a follow-up 6R task capping/evicting the day structures too | — | pending |
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
