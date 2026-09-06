"""RED tests for the rate-limiter's per-DAY memory bound (task 6R-10, WR-06 residual).

Task brief: `docs/plans/phase-6-remediation/task-10-ratelimit-perday-bound.md`. 6R-06 bounded the
per-MINUTE structure (`_minute_windows`) via a hard-cap LRU (`_MAX_TRACKED_IPS`,
`app/routes/ratelimit.py`). The per-DAY structures — `_session_create_counts` (keyed by
`(ip, day_bucket)`, backs `SESSION_CREATE_PER_DAY`) and `_session_day_counts` (keyed by
`(session_id, day_bucket)`, backs `RATE_LIMIT_PER_DAY`) — still grow rollover-only: nothing bounds
them WITHIN a single UTC day under a distinct-IP/distinct-session flood.

Design pin (the brief's hard constraint): a naive LRU-with-eviction, applied to the per-day stores
the way 6R-06 applied it to `_minute_windows`, is WRONG here — evicting a same-day entry and later
re-inserting it as "new" would hand that identity a FRESH daily allowance (the cap-reset exploit).
The brief's preferred mechanism (design pin 2) is instead: bound the store's size; when full,
evict only PRIOR-day (stale-by-rollover) entries; if every entry is same-day (a true >cap
distinct-identity flood within one day), STOP admitting new session-creates rather than evicting a
live counter (fail-closed under flood). This file pins that contract behaviorally — it does not
prescribe the mechanism beyond what the brief's own acceptance text requires (a concrete, checkable
upper bound + the specific fail-closed/no-reset behaviors below).

PINNED INTERFACE DECISION (test-author, this file): the per-day bound is a module-level named
constant, `_MAX_TRACKED_DAY_KEYS`, importable from `app.routes.ratelimit` (an `int`). The
implementer MUST name it exactly this and apply it as the size bound for BOTH
`_session_create_counts` and `_session_day_counts` (one interface, one number, covering both
per-day dicts named in the brief's Context section) — or STOP and take a naming/shape disagreement
back to the controller,
mirroring 6R-06's `_MAX_TRACKED_IPS` precedent (`tests/test_ratelimit_memory.py`'s own "PINNED
INTERFACE DECISION" note). The MECHANISM (design pin 2's stale-first-eviction-else-fail-closed, or
any other conforming approach) is entirely the implementer's choice.

CRITICAL RED-EVIDENCE HAZARD (explicitly called out by this task's brief, and the exact failure
mode that bit 6R-06's own test-author round): `_MAX_TRACKED_DAY_KEYS` does not exist yet. Importing
it at MODULE scope (`from app.routes.ratelimit import _MAX_TRACKED_DAY_KEYS`) would raise
`ImportError` at COLLECTION time — which, under a concurrent full-suite pytest run, aborts
collection of every other test module bundled into the same worker, not just this file. This file
therefore imports only `app.routes.ratelimit` itself (which already exists on disk — that import is
always safe) and fetches the constant via `getattr(...)` INSIDE each test body through the
`_day_bound_cap()` helper below, so a not-yet-implemented constant fails as an ordinary
`AssertionError` raised while a test is RUNNING — behavioral RED, never collection RED.

What each test pins (brief's "Test-author scope" bullets):

- `test_growth_bound_holds_for_session_create_counts_...` /
  `test_growth_bound_holds_for_session_day_counts_...`: bullet 1 (bounded structure) for each of
  the two per-day dicts named in the brief's Context section.
- `test_no_cap_reset_exhausted_ip_still_rejected_after_distinct_ip_flood`: bullet 2, the CRITICAL
  property — an IP whose `SESSION_CREATE_PER_DAY` cap is already exhausted must stay rejected after
  a same-day flood of far more than `_MAX_TRACKED_DAY_KEYS` other distinct IPs, even though the
  exhausted IP is untouched (and so "least-recently-touched") throughout the flood. A naive-LRU
  implementation (design pin's explicitly-forbidden option 1) evicts it as stale-by-recency and
  re-admits it fresh — this test fails against that implementation and passes against a fail-closed
  one, exactly the distinction the brief requires.
- `test_fail_closed_new_ip_rejected_without_evicting_a_live_counter`: bullet 3 (fail-closed) — once
  the store holds `_MAX_TRACKED_DAY_KEYS` distinct same-day entries, a brand-new IP's
  `reserve_session_create` is rejected outright; nothing already in the store is evicted to make
  room (checked directly against the private dict, white-box, same precedent as
  `tests/test_ratelimit_guards.py`'s M-2/M-3 pins and `tests/test_ratelimit_memory.py`'s own note).
- `test_rollover_restores_capacity_after_day_bucket_advance`: bullet 4 — once every entry is from a
  PRIOR day (a UTC day-bucket advance), the store is no longer fail-closed-stuck: a brand-new IP is
  admitted again without needing any same-day eviction.

Fakes: `FakeClock` below is a file-local, trimmed copy of `tests/test_ratelimit.py::FakeClock`'s
shape (CONVENTIONS.md §10 / this task's brief: no cross-test-file imports, even from a pinned
file). All tests are pure unit tests against a fake clock — no DB, no HTTP, no real sleeps; every
flood loop is a plain Python loop over simple dict/lock operations, expected to run in low
single-digit seconds even at `_MAX_TRACKED_DAY_KEYS`-plus-a-few-thousand iterations (same order of
magnitude as `tests/test_ratelimit_memory.py`'s own 55,000-iteration growth test).

White-box note: like the pinned files' own precedent, these tests read `RateLimiter`'s private
stores (`_session_create_counts`, `_session_day_counts`) and call its private `_day_bucket` helper
directly — the property under test (bounded growth, no-reset-on-eviction, fail-closed-not-evict) is
exactly the kind of internal invariant no black-box test can observe.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import app.routes.ratelimit as ratelimit_module
from app.config import Settings
from app.routes.ratelimit import RateLimiter
from app.services.errors import RateLimitedError

_DAY_SECONDS = 86400.0
# noon, day 46 — same fixed anchor as test_ratelimit.py / test_ratelimit_memory.py
_MID_DAY_ANCHOR = 46 * _DAY_SECONDS + 43_200

_DAY_BOUND_CONSTANT_NAME = "_MAX_TRACKED_DAY_KEYS"


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


def _day_bound_cap() -> int:
    """Fetch the pinned per-day bound constant at RUNTIME (never at module import time).

    This is the module's whole RED-safety mechanism (see the module docstring's "CRITICAL
    RED-EVIDENCE HAZARD" note): before the implementer adds `_MAX_TRACKED_DAY_KEYS`, every test
    below fails HERE, on an ordinary `AssertionError`, the moment it runs — never at collection.
    """
    cap = getattr(ratelimit_module, _DAY_BOUND_CONSTANT_NAME, None)
    assert cap is not None, (
        f"expected app.routes.ratelimit.{_DAY_BOUND_CONSTANT_NAME} to exist as the pinned "
        "per-day bound constant (task 6R-10's named interface) — not yet implemented"
    )
    assert isinstance(cap, int) and cap > 0, cap
    return cap


# ---------------------------------------------------------------------------
# Bullet 1: the per-day structures are actually bounded, not merely "usually small".
# ---------------------------------------------------------------------------


def test_growth_bound_holds_for_session_create_counts_across_distinct_ips_in_one_day() -> None:
    """`_session_create_counts` (keyed by `(ip, day_bucket)`, backs `SESSION_CREATE_PER_DAY`):
    flooding far more distinct IPs than `_MAX_TRACKED_DAY_KEYS` in a single UTC day must not grow
    the dict past that bound. `session_create_per_day` is set generously high so only the STORE's
    own size bound (never an individual IP's own cap) can be the thing limiting growth here.
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    limiter = RateLimiter(Settings(session_create_per_day=1_000_000), clock=clock)
    cap = _day_bound_cap()

    ip_count = cap + 5_000
    for i in range(ip_count):
        try:
            limiter.reserve_session_create(f"ip-{i}")
        except RateLimitedError:
            pass  # fail-closed rejection once the store is full is expected, not a bug here.

    tracked = len(limiter._session_create_counts)
    assert tracked <= cap, (tracked, cap)
    assert tracked < ip_count, (tracked, ip_count)


def test_growth_bound_holds_for_session_day_counts_across_distinct_sessions_in_one_day() -> None:
    """`_session_day_counts` (keyed by `(session_id, day_bucket)`, backs `RATE_LIMIT_PER_DAY`): the
    brief's Context section names this dict alongside `_session_create_counts` as needing the same
    bound. One fixed source IP is reused for every call (with a very high per-minute cap) so only
    `check_message`'s per-SESSION day bucketing is exercised — the per-minute/per-IP store is a
    separate, already-bounded concern (6R-06).
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    cap = _day_bound_cap()
    session_count = cap + 5_000
    limiter = RateLimiter(
        Settings(rate_limit_per_min=session_count + 10, rate_limit_per_day=1_000_000), clock=clock
    )

    for i in range(session_count):
        try:
            limiter.check_message("1.1.1.1", f"session-{i}")
        except RateLimitedError:
            pass  # fail-closed rejection once the store is full is expected, not a bug here.

    tracked = len(limiter._session_day_counts)
    assert tracked <= cap, (tracked, cap)
    assert tracked < session_count, (tracked, session_count)


# ---------------------------------------------------------------------------
# Bullet 2: the CRITICAL no-cap-reset property.
# ---------------------------------------------------------------------------


def test_no_cap_reset_exhausted_ip_still_rejected_after_distinct_ip_flood() -> None:
    """The brief's critical property: an IP whose `SESSION_CREATE_PER_DAY` cap is already
    exhausted must NOT regain a fresh allowance merely because a same-day flood of far more than
    `_MAX_TRACKED_DAY_KEYS` other distinct IPs came in afterward — even though `target_ip` is
    completely untouched (and so "least-recently-touched") for the whole flood, which is exactly
    the condition under which a naive LRU (the brief's explicitly-forbidden option 1) would select
    it for eviction and let it come back as "new" with a reset count. This test fails against that
    naive-LRU shape and passes against a fail-closed (or any other never-evict-a-same-day-entry)
    shape — the distinction the brief's design pin exists to draw.
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    cap = _day_bound_cap()
    limiter = RateLimiter(Settings(session_create_per_day=2), clock=clock)

    target_ip = "9.9.9.9"
    limiter.reserve_session_create(target_ip)
    limiter.reserve_session_create(target_ip)
    with pytest.raises(RateLimitedError):
        limiter.check_session_create(target_ip)  # cap of 2 already exhausted

    flood_count = cap + 2_000
    for i in range(flood_count):
        try:
            limiter.reserve_session_create(f"flood-{i}")
        except RateLimitedError:
            pass  # fail-closed rejection once the store is full is expected, not a bug here.

    # CRITICAL: still exhausted — never evicted-and-reset by the flood.
    with pytest.raises(RateLimitedError):
        limiter.check_session_create(target_ip)


# ---------------------------------------------------------------------------
# Bullet 3: fail-closed under a true same-day flood — never evict a live counter to admit new.
# ---------------------------------------------------------------------------


def test_fail_closed_new_ip_rejected_without_evicting_a_live_counter() -> None:
    """Once `_session_create_counts` holds `_MAX_TRACKED_DAY_KEYS` distinct same-day entries, a
    brand-new (never-seen, own cap unexhausted) IP's `reserve_session_create` must be rejected
    outright (fail-closed) — NOT admitted by evicting one of the existing live, same-day entries to
    make room. Checked two ways: the rejected IP never gains an entry, and the store's size and an
    arbitrarily-chosen existing entry are byte-for-byte unchanged by the rejected attempt.
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    cap = _day_bound_cap()
    limiter = RateLimiter(Settings(session_create_per_day=1_000_000), clock=clock)

    for i in range(cap):
        limiter.reserve_session_create(f"flood-{i}")  # every one of these must be admitted

    day_bucket = limiter._day_bucket(clock.now)
    before_size = len(limiter._session_create_counts)
    sample_key = ("flood-0", day_bucket)
    assert limiter._session_create_counts.get(sample_key) == 1

    with pytest.raises(RateLimitedError):
        limiter.reserve_session_create("brand-new-not-yet-seen-ip")

    assert len(limiter._session_create_counts) == before_size, (
        "fail-closed rejection must not evict anything to make room"
    )
    assert limiter._session_create_counts.get(sample_key) == 1, (
        "a live same-day counter must survive a fail-closed rejection of a different IP"
    )
    assert ("brand-new-not-yet-seen-ip", day_bucket) not in limiter._session_create_counts, (
        "the rejected IP must not be admitted into the store"
    )


# ---------------------------------------------------------------------------
# Bullet 4: rollover restores capacity once every stuck entry is from a PRIOR day.
# ---------------------------------------------------------------------------


def test_rollover_restores_capacity_after_day_bucket_advance() -> None:
    """Once the store is fail-closed-stuck (bullet 3, reproduced here as setup), crossing a UTC
    day-bucket boundary must restore capacity: every one of the prior day's entries is now stale
    by rollover (evictable per the brief's design pin), so a brand-new IP is admitted again WITHOUT
    needing any same-day eviction on the new day.
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    cap = _day_bound_cap()
    limiter = RateLimiter(Settings(session_create_per_day=1_000_000), clock=clock)

    for i in range(cap):
        limiter.reserve_session_create(f"day-n-{i}")

    with pytest.raises(RateLimitedError):
        limiter.reserve_session_create("late-arrival-still-day-n")  # fail-closed, still day N

    clock.advance(_DAY_SECONDS + 10.0)  # cross into the next UTC day bucket

    limiter.reserve_session_create("day-n-plus-1-ip")  # must NOT raise: capacity restored

    tracked_after = len(limiter._session_create_counts)
    assert tracked_after <= cap, (tracked_after, cap)
    new_day_bucket = limiter._day_bucket(clock.now)
    assert limiter._session_create_counts.get(("day-n-plus-1-ip", new_day_bucket)) == 1
