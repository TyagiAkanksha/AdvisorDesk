"""RED tests for the rate-limiter's within-day memory bound (task 6R-06, WR-06).

Task brief: `docs/plans/phase-6-remediation/task-06-ratelimit-memory-bound.md`. WR-06 (verifier-
corrected scope, `.superpowers/sdd/reports/p6-whole-repo-review.md`): `_prune_stale_entries`
(`app/routes/ratelimit.py:152-153`) only ever runs when the UTC day-bucket advances, so
`_minute_windows` grows without bound WITHIN a day — the verifier's own `tracemalloc` probe
measured ~874 B/distinct IP, ~834 MiB per 1M IPs, with 5,001 entries still held after every deque
had gone stale same-day. The "even a rejected request allocates a bucket" sub-claim was proven
vacuous by the verifier and is explicitly OUT of this task's scope (WR-06's corrected framing) —
nothing in this file exercises it.

PINNED INTERFACE DECISION (test-author, this file): the within-day bound is a module-level named
constant, `_MAX_TRACKED_IPS`, importable from `app.routes.ratelimit`. It does not exist yet —
every test in this file is expected to fail at COLLECTION
(`ImportError: cannot import name '_MAX_TRACKED_IPS' from 'app.routes.ratelimit'`) until the
implementer adds it. That import failure IS this file's RED evidence (clean-collection-failure
mode — `app.routes.ratelimit` itself already exists on disk, unlike `test_ratelimit.py`'s original
RED against a wholly-missing module, so this is an `ImportError`, not a `ModuleNotFoundError`).
The implementer MUST name the bound exactly `_MAX_TRACKED_IPS` (a module-level `int` in
`app/routes/ratelimit.py`) or STOP and take the naming disagreement back to the controller — this
file pins the NAME as the interface, per the brief's "pin the bound as a named constant import,
not a literal" instruction. The MECHANISM behind it (design pin 1's candidate shapes:
time-elapsed opportunistic prune vs. a hard entry cap with stale-first eviction) is entirely the
implementer's choice; nothing below assumes one over the other beyond what the brief's own
acceptance text requires of either — a concrete, checkable upper bound on `_minute_windows`'s
size, since "assert tracked-key count stays <= the bound" is only expressible at all if some such
bound exists no matter which mechanism produces it.

What each test pins (brief's "Test-author scope" bullets):

- `test_growth_bound_holds_across_fifty_thousand_distinct_ips_in_one_day`: growth is actually
  bounded relative to input size, not merely "the bound happens to be huge" — asserts both
  `<= _MAX_TRACKED_IPS` and `< ip_count` (55,000), so a compliant-looking-on-paper but practically
  unbounded constant cannot pass by accident.
- `test_stale_minute_window_eviction_does_not_reset_per_day_session_create_count`: the brief's
  "no cap-reset exploit" — per-day structures (`_session_create_counts`, `_session_day_counts`)
  are the brief's frozen, rollover-only-eviction stores; `_minute_windows` is "the unbounded-
  growth driver and the safe eviction target" (brief, bullet 2). An IP whose per-minute entry is
  evicted for genuine staleness must NOT regain any exhausted per-day allowance.
- `test_backward_clock_step_within_window_does_not_evict_or_reset_active_ips`: design pin 2 — a
  clock stepping backward by no more than the 60s window (an NTP correction, say) must not be
  mistaken for staleness, mirroring the existing per-IP deque prune's own `>=` comparison
  (`ratelimit.py:166`), which already has this property today.

Fakes: `FakeClock` below is a file-local, trimmed copy of `tests/test_ratelimit.py::FakeClock`'s
shape (CONVENTIONS.md §10 / this task's brief: no cross-test-file imports, even from a pinned
file — the pattern is reused, the file is not). All tests are pure unit tests against a fake
clock — no DB, no HTTP, no real sleeps; the 50k-IP growth test is a plain Python loop and is
expected to run in low single-digit seconds.

White-box note: like `tests/test_ratelimit_guards.py`'s M-2/M-3 precedent, these tests read
`RateLimiter`'s private stores (`_minute_windows`, `_session_create_counts`) directly — the
property under test (bounded growth, frozen-mid-day per-day stores) is exactly the kind of
internal invariant the module's own docstring advertises and no black-box test can observe.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.config import Settings
from app.routes.ratelimit import _MAX_TRACKED_IPS, RateLimiter
from app.services.errors import RateLimitedError

_DAY_SECONDS = 86400.0
# noon, day 46 — same fixed anchor as test_ratelimit.py
_MID_DAY_ANCHOR = 46 * _DAY_SECONDS + 43_200


@dataclass
class FakeClock:
    """A settable/advanceable epoch-seconds clock double — file-local trimmed copy of
    `tests/test_ratelimit.py::FakeClock`'s shape (no cross-test-file imports).
    """

    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_growth_bound_holds_across_fifty_thousand_distinct_ips_in_one_day() -> None:
    """Growth bound (brief bullet 1): flood the limiter with 55,000 distinct IPs, one message
    each, spread across ~15.3 hours of fake-clock time (`clock.advance(1.0)` per call) so the
    whole scenario stays within a single UTC day-bucket the entire time — exactly the condition
    under which the OLD `_prune_stale_entries` (gated on a day-bucket *advance*) never ran at all,
    per WR-06's own probe. `session_id=None` on every call keeps this test's assertions purely
    about `_minute_windows`; the per-day dicts are a separate, frozen-mid-day concern (see the
    next test).
    """
    ip_count = 55_000
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(), clock=clock)

    for i in range(ip_count):
        limiter.check_message(f"ip-{i}", None)
        clock.advance(1.0)

    tracked = len(limiter._minute_windows)
    assert tracked <= _MAX_TRACKED_IPS, (tracked, _MAX_TRACKED_IPS)
    assert tracked < ip_count, (tracked, ip_count)


def test_stale_minute_window_eviction_does_not_reset_per_day_session_create_count() -> None:
    """Eviction correctness (brief bullet 2): an IP whose per-minute window is evicted as stale
    must come back to a genuinely fresh per-minute window (correct — it really has been idle past
    the 60s window) WITHOUT regaining any exhausted PER-DAY allowance (`_session_create_counts` —
    the brief's "no cap-reset exploit"; per-day structures are frozen mid-day, only
    `_minute_windows` is the safe eviction target).
    """
    target_ip = "9.9.9.9"
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    limiter = RateLimiter(Settings(session_create_per_day=2), clock=clock)

    # Exhaust target_ip's per-IP daily session-create cap.
    limiter.reserve_session_create(target_ip)
    limiter.reserve_session_create(target_ip)
    with pytest.raises(RateLimitedError):
        limiter.check_session_create(target_ip)

    # Give target_ip an active per-minute window entry, then let it go idle past the 60s window.
    limiter.check_message(target_ip, None)
    assert target_ip in limiter._minute_windows
    clock.advance(61.0)

    # Flood enough distinct traffic to give whatever eviction mechanism the implementer chose
    # (a periodic sweep or a hard cap checked per-request) every chance to run and reclaim
    # target_ip's now-stale, untouched-since entry — it is the single stalest entry in the store
    # by construction, so any stale-first/oldest-first eviction order reclaims it first.
    for i in range(_MAX_TRACKED_IPS + 2_000):
        limiter.check_message(f"flood-{i}", None)

    assert target_ip not in limiter._minute_windows, "expected the stale entry to be reclaimed"

    # The per-day session-create cap is UNCHANGED by that eviction — still exhausted.
    with pytest.raises(RateLimitedError):
        limiter.check_session_create(target_ip)

    # A genuinely fresh per-minute window is correct (61s of real idle time passed) — not a bug.
    limiter.check_message(target_ip, None)


def test_backward_clock_step_within_window_does_not_evict_or_reset_active_ips() -> None:
    """Clock-step guard (brief bullet 3 / design pin 2): a clock stepping backward by no more than
    the 60s window (e.g. an NTP correction) must not be mistaken for staleness. Exhausts a tight
    per-minute cap for one IP, populates a batch of other active IPs, steps the clock backward
    30s, and asserts neither the exhausted cap is silently reset nor any of the other active IPs
    are evicted from `_minute_windows`.
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    limiter = RateLimiter(Settings(rate_limit_per_min=2), clock=clock)

    target_ip = "4.4.4.4"
    limiter.check_message(target_ip, None)
    limiter.check_message(target_ip, None)  # exhausts the per-minute cap of 2

    other_ips = [f"5.5.5.{i}" for i in range(50)]
    for ip in other_ips:
        limiter.check_message(ip, None)

    clock.advance(-30.0)  # backward step, well within the 60s window

    with pytest.raises(RateLimitedError):
        limiter.check_message(target_ip, None)  # still exhausted — not reset by the backward step

    for ip in other_ips:
        assert ip in limiter._minute_windows, (ip, sorted(limiter._minute_windows))
