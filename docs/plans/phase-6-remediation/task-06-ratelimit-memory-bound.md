# Task 6R-06 — Rate-limiter memory bound

WR-id: WR-06 (verifier-corrected scope: the growth limb only — the "rejected request allocates"
sub-claim was proven vacuous; do not implement anything for it). Effort M. Full three-agent SDD.
Independent of other 6R tasks. File: `apps/api/app/routes/ratelimit.py` (+ new test files only).

## Problem (verified numbers)

~874 B per distinct IP; per-minute/per-day structures prune only when the UTC day-bucket advances,
so within one day growth is unbounded (verifier probe: 5,001 entries held after every deque went
stale). A 404-scan botnet on a 2 GiB box is the realistic threat.

## Design pins

1. Bound memory WITHIN a day. Mechanism = implementer freedom; candidate shapes (pick one, justify):
   time-elapsed opportunistic prune (evict empty/stale deques when older than the window, triggered
   every N observes), or a hard entry cap with stale-first eviction. Constraints either way:
   - NO behavior change for any legitimate request pattern: every existing rate-limit test (incl.
     the pinned `test_ratelimit.py` bd223717 and `test_ratelimit_guards.py`) must pass UNMODIFIED.
     Pinned files are untouchable — stop rule applies.
   - The two-step `check_session_create`/`note_session_created` public API and
     `reserve_session_create` atomicity are frozen contracts.
   - Single coarse lock stays (no new lock-ordering surface); prune cost must stay O(evicted), not
     O(all-keys) per request (t01's I-1 history: full-scan-per-request was already found and fixed
     once — don't reintroduce it via the prune).
2. Backward clock steps must not mass-evict (existing `>=` prune survives one; keep that property).

## Test-author scope (new file `tests/test_ratelimit_memory.py`)

- growth bound: simulate ≥50k distinct IPs within one fake-clock day; assert tracked-key count stays
  ≤ the chosen bound (pin the bound as a named constant import, not a literal)
- eviction correctness: an IP evicted as stale and returning gets fresh, correct limiting (no
  cap-reset exploit: an IP evicted mid-day must NOT regain its per-day allowance — if the chosen
  mechanism cannot preserve per-day counts for evicted IPs, per-day structures may only be evicted
  at day rollover; the per-minute window is the unbounded-growth driver and the safe eviction target)
- clock-step guard: backward step ≤ window doesn't evict
- fake epoch-clock pattern from `test_ratelimit.py` reused via new helpers (no edits to pinned files)

## Acceptance

Full suite green env-exported; five api gates clean; pinned hashes verified before/after; a
measured before/after memory probe (repeat the verifier's shape) in the implementer report;
path-scoped adds only; owner-pending files untouchable.
