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
| B3 SUBSET (owner-chosen 2026-09-06) | `task-07-import-contracts-ws.md` | WR-07, t04-M7 | ✅ RED c321f72 + impl abcaf8c + comment-fix cf3f639; review APPROVED (8 contracts, allow_indirect_imports proven load-bearing; WS guard mutation-verified; sole finding = a false hang-claim in a comment, corrected) |
| B3 SUBSET | `task-08-held-txn-agent-tests-metrics.md` | WR-09, WR-10, t01-N2 | ✅ RED 72350e7 + impl bcf78c6; review APPROVED first round (0 C/I, 2 Minors; metrics bucket bounded-cardinality independently proven — 5 mount sub-paths → 1 key) |
| B3 SUBSET | `task-11-frontend-tagdrop-aria-tsstrict.md` | WR-11, WR-13, WR-66, TS-strictness (B4) | ✅ RED 6df171e + impl 7a909c9 + fix r1 d829ab4; confirm APPROVED (WR-11 live-proven; chip-delete regression found+fixed reason-aware; aria + avatar; 14 strictness sites fixed). Minor: Next re-adds allowJs on build (committed clean) |
| B3 residual | `task-09-bearer-expiry-allowlist.md` | WR-02 residual (expiry + ADMIN_EMAILS re-check) | ✅ RED 06f42fd + impl 7510997; opus review APPROVED (0 C/I, mutation battery no survivors, offboarding-kills-token live-proven, no oracle; 2 pinned files re-pinned data-only). Minor: settings=None fail-open for future caller (latent). FOLLOW-UP: mint-time allowlist enforcement deferred |
| B3 residual | `task-10-ratelimit-perday-bound.md` | WR-06 residual (per-day counters) | ✅ RED 7f14b07 + impl e5bc912; opus review APPROVED (0 C/I; fail-closed no-cap-reset; memory 40→2.6 MiB hard cap; prune-first makes fail-closed the O(1) equivalent). Minor: fail-closed 429s indistinguishable in logs |
| B3 DEFERRED (owner: skip for now) | — | WR-12 SSE-package, WR-14/15 EC2 IaC+monitoring, WR-18 README+demo | ledgered, ready to brief if revisited |
| B4 owner decisions | RESOLVED 2026-09-06: TS noUncheckedIndexedAccess ON + drop allowJs (→t11); mypy app/-scope documented as policy (CONVENTIONS §9, done); t01-N2 metrics bucket FIX (→t08); t04-M7 WS abort opportunistic (→t07); MSW keep hand mocks (no-op); t04-M1 raw ORM leave (ratified, no-op); UI-polish → one task later (`task-12-ui-polish.md` backlog stub); residuals 9+10 → DO BOTH (→t09/t10) | — | resolved |
| B5 minors | 2–3 cleanup tasks; WR-51 limbs; whole-branch-triage Minors | — | pending |

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
