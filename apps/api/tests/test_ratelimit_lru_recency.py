"""LRU-recency pin for the rate-limiter's within-day memory bound (task 6R-06, WR-06 fix round 1).

Review finding I-1 (`.superpowers/sdd/reports/p6r-t06-review.md`): deleting the single
`self._minute_windows.move_to_end(ip)` touch at `app/routes/ratelimit.py` — the entire
LRU-vs-insertion-order-FIFO distinction `_touch_minute_window` provides over a plain `dict` —
left all 22 existing rate-limit tests green (mutations M1/M6 in the review's mutation battery),
while measurably letting a throttled IP self-evict its own per-minute window under a distinct-IP
flood and get readmitted early inside the same 60s window: a measured 5x per-minute cap leak (50
admitted messages against a nominal cap of 10, instead of 10). Nothing in the existing suite —
including the pinned `tests/test_ratelimit_memory.py`
(sha256 e37d8415292f4ece3b88c10c6a8bdcd340e858a6ad16628dfea6d4265ed32e37, untouched by this file)
— pinned that recency property: none of its tests re-touch a target IP while a flood runs
concurrently, so none of them can distinguish LRU from FIFO eviction order.

This is a NEW test file, added per the review's fix-round instruction rather than edited into the
pinned `test_ratelimit_memory.py` (which must stay byte-identical). It reuses that file's
file-local `FakeClock` pattern (CONVENTIONS.md §10 / this task's own precedent: no
cross-test-file imports, even between this task's own files) rather than importing it.

Mutation-bite evidence (recorded here per the fix-round instruction; the underlying mutation was
applied only in a scratch edit, verified, and immediately reverted — never committed):

    $ git stash  # (illustrative — the actual check used a local, uncommitted one-line edit)
    # apps/api/app/routes/ratelimit.py:221, delete the line:
    #     self._minute_windows.move_to_end(ip)
    $ uv run pytest -q tests/test_ratelimit_lru_recency.py
    F
    ...
    AssertionError: 20 != 10
    assert 20 == 10
    1 failed in 0.09s
    # restore the deleted line, re-run:
    $ uv run pytest -q tests/test_ratelimit_lru_recency.py
    1 passed in 0.09s
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.routes.ratelimit import _MAX_TRACKED_IPS, RateLimiter
from app.services.errors import RateLimitedError

_DAY_SECONDS = 86400.0
# noon, day 46 — same fixed anchor as test_ratelimit.py / test_ratelimit_memory.py
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


def test_throttled_ip_is_not_evicted_while_it_keeps_retrying() -> None:
    """An IP already at its per-minute cap keeps being *touched* by its own rejected retries
    (every `check_message` call touches `_minute_windows`, admitted or not — module docstring's
    "Within-day memory bound" section), so a concurrent flood of never-seen IPs must never evict
    it: LRU order (`move_to_end` on every touch), not plain insertion-order FIFO. Its cap stays
    exactly `rate_limit_per_min` (10) for the whole frozen 60s window, no matter how large the
    flood grows past `_MAX_TRACKED_IPS`.

    As committed (LRU): `admitted == 10`, target never evicted. Under the I-1 mutation (delete
    `move_to_end`, degrading `_minute_windows` to insertion-order FIFO): the target's own retries
    no longer refresh its position, so it ages out and is evicted mid-flood — its window resets
    and it is readmitted for a fresh 10, doubling `admitted` to 20 over this test's flood size (a
    5x leak was measured over a larger flood in the review's own probe; this test's smaller,
    fast-running flood still cleanly separates 10 from 20 — see module docstring for the exact
    verified before/after run).
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)  # frozen: one 60s window throughout
    limiter = RateLimiter(Settings(rate_limit_per_min=10), clock=clock)
    target = "198.51.100.7"
    admitted = 0
    for i in range(_MAX_TRACKED_IPS * 2):
        limiter.check_message(f"flood-{i}", None)
        if i % 10 == 0:
            try:
                limiter.check_message(target, None)
                admitted += 1
            except RateLimitedError:
                pass
    assert admitted == 10, admitted
    assert target in limiter._minute_windows
