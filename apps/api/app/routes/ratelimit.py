"""In-app rate limiting for the public chat surface (PRD §9, §5.3; phase-4 task-03).

Three independent §9 caps, all enforced by one `RateLimiter` instance shared across requests
(`app.state.rate_limiter`, wired by `app.factory.create_app` / `app/main.py`, same per-seam shape
as `chat_llm`/`embedder`):

- `RATE_LIMIT_PER_MIN` (default 10) — a SLIDING one-minute window, per IP.
- `RATE_LIMIT_PER_DAY` (default 50) — a fixed UTC-midnight-bucketed window, per session.
- `SESSION_CREATE_PER_DAY` (default 20) — a fixed UTC-midnight-bucketed window, per IP; the cap
  that closes the "mint a fresh session to reset the per-session cap" loophole (PRD §5.3, §9).

Task brief amendment (`docs/plans/phase-4-rag-assistant/task-03-rate-limiting.md`, commit
`5a2e65b`): the injectable `clock` returns POSIX EPOCH SECONDS (default `time.time`, not
`time.monotonic` — a monotonic clock cannot express "UTC midnight"). A day bucket is
`floor(clock() / 86400)`, which IS the UTC-midnight reset boundary, since epoch second 0 is UTC
midnight and every multiple of 86400 seconds after it is another UTC midnight.

Store shape (implementer's choice, documented per the brief's invitation to do so): a `deque` of
admission timestamps per IP for the sliding per-minute window (only entries within the trailing
60s ever matter, so the deque is pruned from the left on every check); a plain
`dict[(key, day_bucket), int]` counter for each of the two day-scoped caps, since a day bucket is
a single integer and a fixed window only needs a count, not individual timestamps. All three
stores are pure in-memory, per-process state — PRD §9 explicitly allows this for a single
container ("in-memory store is acceptable").

Pruning: stale day-bucket entries (any `day_bucket` strictly less than the current one) are
dropped opportunistically, at most once per observed day-bucket advance, so the two day-keyed
dicts stay bounded to "today's" distinct sessions/IPs rather than growing for the process's
entire lifetime. The per-minute `deque`s are pruned on every `check_message` call (the sliding
window itself requires this), but an IP's now-empty deque is left in the dict rather than
removed — one empty `deque` per distinct IP ever seen is a few dozen bytes, not worth the extra
bookkeeping to reclaim.

Thread-safety: `starlette.testclient.TestClient` (this repo's test surface) drives requests
single-threaded, but a real `uvicorn` deployment may not (multiple worker threads sharing one
process's `app.state.rate_limiter`). A single `threading.Lock` guards every read-modify-write
across all three stores — check-then-record is a few dict/deque operations, microseconds under
the lock, so one coarse lock is simpler and cheap enough rather than three finer-grained ones.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from app.config import Settings
from app.services.errors import RateLimitedError

__all__ = ["RateLimiter"]

_MINUTE_SECONDS = 60.0
_DAY_SECONDS = 86400.0

_PER_MIN_MESSAGE = "Too many messages from this IP in the last minute. Please slow down."
_PER_DAY_MESSAGE = "This session has reached its daily message limit. Please try again tomorrow."
_SESSION_CREATE_MESSAGE = (
    "Too many new sessions started from this IP today. Please try again tomorrow."
)


class RateLimiter:
    """Enforces the three PRD §9 public-chat caps against an injectable epoch-seconds clock.

    One instance is meant to be shared across every request for the lifetime of the app
    (`app.state.rate_limiter`) — all state (the sliding per-minute windows, the two day-bucketed
    counters) lives on the instance, not per-call, so callers must reuse the same `RateLimiter`
    across requests for the caps to mean anything.
    """

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        """Build a limiter reading its caps from `settings` and its notion of "now" from `clock`.

        Args:
            settings: supplies `rate_limit_per_min`, `rate_limit_per_day`,
                `session_create_per_day` (PRD §9 defaults, env-tunable) — read on every check, not
                copied at construction, so a caller mutating a shared `Settings` instance (tests
                only; production `Settings` is effectively immutable after boot) sees the new
                value on the next check.
            clock: returns the current time as POSIX epoch seconds (default `time.time`).
                CONVENTIONS.md §10's injectable-clock seam: tests pass a settable fake so no test
                ever sleeps. Day buckets are `floor(clock() / 86400)` — the controller-ruled
                UTC-midnight reset (module docstring).
        """
        self._settings = settings
        self._clock = clock
        self._lock = threading.Lock()

        # Sliding one-minute window, per IP: admission timestamps, oldest first. Pruned from the
        # left in `check_message` — only entries within the trailing 60s of `clock()` ever count.
        self._minute_windows: dict[str, deque[float]] = {}

        # Fixed UTC-midnight-bucketed counters. Keys are (identity, day_bucket); a day bucket only
        # needs a count, never individual timestamps, since the whole bucket resets together.
        self._session_day_counts: dict[tuple[str, int], int] = {}
        self._session_create_counts: dict[tuple[str, int], int] = {}

        # The most recent day bucket `_prune_stale_days` has already cleaned up through — lets
        # pruning run at most once per observed day-bucket advance instead of on every call.
        self._last_pruned_day_bucket: int | None = None

    def _day_bucket(self, now: float) -> int:
        """The UTC-midnight bucket `now` (POSIX epoch seconds) falls into."""
        return int(now // _DAY_SECONDS)

    def _prune_stale_days(self, current_day_bucket: int) -> None:
        """Drop counter entries from strictly earlier day buckets (caller holds `self._lock`).

        Safe unconditionally: a key's `day_bucket` component never becomes relevant again once a
        strictly larger day bucket has been observed (buckets only ever increase as `clock()`
        advances in every test and in real wall-clock time), so evicting anything older than
        `current_day_bucket` can never affect a future check. A no-op once already caught up to
        `current_day_bucket`, so normal request traffic within the same day pays this cost at
        most once.
        """
        if self._last_pruned_day_bucket == current_day_bucket:
            return
        self._session_day_counts = {
            key: count
            for key, count in self._session_day_counts.items()
            if key[1] >= current_day_bucket
        }
        self._session_create_counts = {
            key: count
            for key, count in self._session_create_counts.items()
            if key[1] >= current_day_bucket
        }
        self._last_pruned_day_bucket = current_day_bucket

    def check_message(self, ip: str, session_id: str | None) -> None:
        """Admit or reject one `/public/chat` message (PRD §9's first two caps).

        Always enforces `RATE_LIMIT_PER_MIN` (sliding one-minute window, keyed by `ip`). Also
        enforces `RATE_LIMIT_PER_DAY` (fixed UTC-midnight window, keyed by `session_id`) — but
        ONLY when `session_id` is not `None`. Controller-approved semantics (test-author report
        `p4-t03-test-author.md`, judgment call #2): the wiring-order pin (limits are checked
        BEFORE `get_or_create_session` ever mints an id) means a brand-new session's very first
        message necessarily carries `session_id=None` — there is no id yet to key a per-session
        bucket on, so that one message is unavoidably exempt from the per-day cap. It is never
        exempt from the per-minute cap, which is keyed by IP, not session.

        Both admitted-state updates (the minute-window append, the day-bucket increment) happen
        only once the message is confirmed admitted — a rejected call records nothing, so retrying
        after a 429 does not itself consume any budget.

        Args:
            ip: the caller's IP address (`request.client.host`, per-IP key for the per-minute
                cap).
            session_id: the chat session id as a string, or `None` for a brand-new session's first
                message (see above).

        Raises:
            RateLimitedError: either cap is exceeded.
        """
        now = self._clock()
        day_bucket = self._day_bucket(now)
        with self._lock:
            self._prune_stale_days(day_bucket)

            window = self._minute_windows.setdefault(ip, deque())
            while window and now - window[0] >= _MINUTE_SECONDS:
                window.popleft()
            if len(window) >= self._settings.rate_limit_per_min:
                raise RateLimitedError(_PER_MIN_MESSAGE)

            day_key = (session_id, day_bucket) if session_id is not None else None
            if day_key is not None:
                day_count = self._session_day_counts.get(day_key, 0)
                if day_count >= self._settings.rate_limit_per_day:
                    raise RateLimitedError(_PER_DAY_MESSAGE)

            # Admitted: record against both caps now, not before either check above, so a
            # rejection never leaves a partial/inconsistent update behind.
            window.append(now)
            if day_key is not None:
                self._session_day_counts[day_key] = day_count + 1

    def check_session_create(self, ip: str) -> None:
        """Check (without recording) whether `ip` may mint one more session today (PRD §9/§5.3).

        Pure check — pairs with `note_session_created`, called by the caller only once a session
        is actually about to be minted (the two-step API the unit tests pin: a rejected attempt
        must not itself consume a slot, so checking never has a side effect).

        Args:
            ip: the caller's IP address — `SESSION_CREATE_PER_DAY` is a per-IP cap.

        Raises:
            RateLimitedError: `SESSION_CREATE_PER_DAY` sessions have already been created from
                `ip` in the current UTC day.
        """
        day_bucket = self._day_bucket(self._clock())
        with self._lock:
            self._prune_stale_days(day_bucket)
            count = self._session_create_counts.get((ip, day_bucket), 0)
            if count >= self._settings.session_create_per_day:
                raise RateLimitedError(_SESSION_CREATE_MESSAGE)

    def note_session_created(self, ip: str) -> None:
        """Record that `ip` actually minted one new session just now (pairs with
        `check_session_create`).

        Callers must only call this after `check_session_create` has passed AND a session mint is
        actually going to happen for this request — never speculatively, and never for a request
        that turned out to reuse an existing session.

        Args:
            ip: the caller's IP address, same key `check_session_create` reads.
        """
        day_bucket = self._day_bucket(self._clock())
        with self._lock:
            self._prune_stale_days(day_bucket)
            key = (ip, day_bucket)
            self._session_create_counts[key] = self._session_create_counts.get(key, 0) + 1
