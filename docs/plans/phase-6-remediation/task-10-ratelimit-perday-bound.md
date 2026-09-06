# Task 6R-10 — Bound the per-day rate-limiter counters (WR-06 residual)

WR-id: WR-06 residual (per-day limb; 6R-06 review M-2). Effort M. Full three-agent SDD. File:
`apps/api/app/routes/ratelimit.py` + new tests. Independent of other tasks.

## Context

6R-06 bounded the per-MINUTE structure via hard-cap LRU. The per-DAY structures
(`_session_create_counts` keyed by IP; `_session_day_counts` keyed by session) still grow rollover-only
— measured ~144 B/IP within a day (~137 MiB/1M IPs). Smaller per-entry than the pre-fix minute dicts,
but still unbounded within a UTC day under a distinct-IP flood.

## Design pins — the hard constraint

The per-day caps enforce actual abuse limits (SESSION_CREATE_PER_DAY etc.), so eviction MUST NOT hand
an evicted IP a fresh daily allowance (the cap-reset exploit the 6R-06 pinned test guards against for
the minute window). Options, implementer's choice with justification:
1. **Cap + LRU like the minute store**, BUT only safe if an evicted IP that returns is treated as
   NEW — which resets its daily count. That is the exploit. So a naive LRU is WRONG here.
2. **Preferred: a larger cap sized so eviction is effectively unreachable by legitimate traffic, and
   when the cap is hit, evict the LEAST-RECENTLY-SEEN entry only if it is from a PRIOR day** (stale by
   rollover) — never evict a same-day entry that still carries an unexhausted-or-exhausted count.
   If all entries are same-day (a true >cap distinct-IP flood in one day), STOP admitting new
   session-creates (fail-closed: return the create-cap rejection) rather than evicting a live counter.
   This caps memory AND preserves every same-day cap. Document the chosen cap and the fail-closed
   behavior.
3. Whatever mechanism: O(1) amortized per request, single coarse lock, the 6R-06 minute-store
   behavior unchanged, ALL pinned ratelimit tests (bd223717, 9d227ebc, e37d8415, +6R-06's LRU test)
   pass unmodified.

The fail-closed-under-flood tradeoff (a >cap one-day distinct-IP flood stops NEW session creation but
never resets an existing IP's cap and never evicts a live counter) is the correct security posture and
must be pinned by a test + documented in the module docstring.

## Test-author scope (RED, new file `tests/test_ratelimit_perday_bound.py`)

- per-day structure bounded: ≥ (cap) distinct IPs same-day → tracked day-entries ≤ named constant.
- NO cap-reset: an IP whose create-cap is exhausted, after a flood, still rejected same-day (the
  critical property — must fail if a naive-LRU evicts-and-resets it).
- fail-closed: at the day cap with all-same-day entries, a brand-new IP's session-create is rejected,
  not admitted-by-evicting-a-live-counter.
- rollover: prior-day entries evictable; a new day restores capacity.
Reuse 6R-06's fake-clock helpers via new file-local helpers; pinned files untouchable.

## Acceptance

Full suite green env-exported; five gates clean; before/after memory probe (day structures under a
300k-IP one-day flood, verbatim numbers); all ratelimit pinned hashes re-verified; path-scoped add of
ratelimit.py + new test file. Owner-pending files untouchable. Commit
`feat(api): bound per-day rate-limiter counters, fail-closed under flood (6R-10, WR-06 residual)`.
