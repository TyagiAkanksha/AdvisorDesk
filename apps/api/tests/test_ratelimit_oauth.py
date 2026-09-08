"""Failing (RED) tests for `RateLimiter.check_oauth_request` — the per-IP OAuth rate-limit
cap shared by every `/api/v1/oauth/*` endpoint (mcp-oauth plan, task 04).

Task brief: docs/plans/mcp-oauth/task-04-dcr-register.md. Spec: docs/plans/mcp-oauth/DESIGN.md
§"Security / threat model" ("Rate-limit `/register`, `/authorize`, and `/token` (reuse
`app.routes.ratelimit`)") and its Global Constraints §"Rate limiting" (a sliding per-IP
one-minute window, cap `oauth_rate_limit_per_min=30` by default, keyed independently of the
existing public-chat caps).

Today `app.routes.ratelimit.RateLimiter` has no `check_oauth_request` method at all — every test
below fails at RUNTIME (`AttributeError: 'RateLimiter' object has no attribute
'check_oauth_request'`) on its first call, not at collection: `RateLimiter`/`Settings`/
`RateLimitedError` all already exist on this branch (tasks 01-03), only the new method is
missing. See the test-author report for the literal per-test failure output.

`FakeClock` is a trimmed, local copy of `tests/test_ratelimit.py::FakeClock`'s exact shape
(CONVENTIONS.md §10: no cross-test-file imports) — a settable epoch-seconds clock double for
`RateLimiter`'s injectable `clock` seam, so no test here ever sleeps.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.config import Settings
from app.routes.ratelimit import RateLimiter
from app.services.errors import RateLimitedError

_OAUTH_RATE_LIMIT_MESSAGE = (
    "Too many authorization requests from this IP in the last minute. Please slow down."
)


@dataclass
class FakeClock:
    """A settable epoch-seconds clock double for `RateLimiter`'s injectable `clock` seam —
    trimmed local copy of `tests/test_ratelimit.py::FakeClock` (CONVENTIONS.md §10).
    """

    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_oauth_window_allows_up_to_cap() -> None:
    """`oauth_rate_limit_per_min=3`: three calls from one IP pass, the fourth raises
    `RateLimitedError` — the sliding-window admission shape `check_message` already has, applied
    to the new OAuth-endpoint cap.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(oauth_rate_limit_per_min=3), clock=clock)

    for _ in range(3):
        limiter.check_oauth_request("1.2.3.4")

    with pytest.raises(RateLimitedError):
        limiter.check_oauth_request("1.2.3.4")


def test_oauth_window_slides() -> None:
    """Sliding one-minute window: three calls at t=0 exhaust a cap of 3; advancing the fake
    clock 61s (past the whole 60s window) admits a fourth.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(oauth_rate_limit_per_min=3), clock=clock)

    for _ in range(3):
        limiter.check_oauth_request("1.2.3.4")

    clock.advance(61.0)

    limiter.check_oauth_request("1.2.3.4")  # must not raise


def test_oauth_window_is_per_ip() -> None:
    """The OAuth cap is keyed by IP: exhausting it for one IP leaves a different IP's own budget
    completely untouched.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(oauth_rate_limit_per_min=2), clock=clock)

    limiter.check_oauth_request("10.0.0.1")
    limiter.check_oauth_request("10.0.0.1")
    with pytest.raises(RateLimitedError):
        limiter.check_oauth_request("10.0.0.1")

    limiter.check_oauth_request("10.0.0.2")  # different IP, must not raise
    limiter.check_oauth_request("10.0.0.2")


def test_oauth_window_independent_of_message_window() -> None:
    """`check_message` and `check_oauth_request` key two INDEPENDENT sliding windows (Interfaces
    block: `check_oauth_request` stores its admissions under key `f"oauth:{ip}"` in the same
    `_minute_windows` dict `check_message` uses under a plain `ip` key) — proven in both
    directions, each on its own IP so a fully-exhausted window is never re-tested against
    itself: exhausting `check_message`'s budget for `ip_a` leaves `check_oauth_request`'s own
    budget for `ip_a` fully intact (and vice versa for `ip_b`).
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(rate_limit_per_min=2, oauth_rate_limit_per_min=2), clock=clock)

    ip_a = "1.2.3.4"
    limiter.check_message(ip_a, "session-a")
    limiter.check_message(ip_a, "session-a")
    with pytest.raises(RateLimitedError):
        limiter.check_message(ip_a, "session-a")

    # The oauth window for the SAME ip is untouched: still admits its own full cap of 2, then
    # genuinely trips on the 3rd — proving check_message's exhaustion didn't consume it.
    limiter.check_oauth_request(ip_a)
    limiter.check_oauth_request(ip_a)
    with pytest.raises(RateLimitedError):
        limiter.check_oauth_request(ip_a)

    ip_b = "5.6.7.8"
    limiter.check_oauth_request(ip_b)
    limiter.check_oauth_request(ip_b)
    with pytest.raises(RateLimitedError):
        limiter.check_oauth_request(ip_b)

    # The message window for that SAME second ip is untouched: still admits its own full cap of
    # 2, then genuinely trips on the 3rd — proving check_oauth_request's exhaustion didn't
    # consume it.
    limiter.check_message(ip_b, "session-b")
    limiter.check_message(ip_b, "session-b")
    with pytest.raises(RateLimitedError):
        limiter.check_message(ip_b, "session-b")


def test_oauth_error_message_exact() -> None:
    """`RateLimitedError`'s message string equals the exact text pinned in the task brief's
    Interfaces block — a caller (the DCR route's `OAuthError`/`ErrorEnvelope` rendering) depends
    on this exact wording, not just the exception type.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(oauth_rate_limit_per_min=1), clock=clock)

    limiter.check_oauth_request("9.9.9.9")
    with pytest.raises(RateLimitedError) as exc_info:
        limiter.check_oauth_request("9.9.9.9")

    assert str(exc_info.value) == _OAUTH_RATE_LIMIT_MESSAGE
