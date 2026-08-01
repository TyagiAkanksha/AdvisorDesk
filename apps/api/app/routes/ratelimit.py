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

Pruning (review round 1, finding M-3 — revised from round 0's docstring, whose "a few dozen
bytes per IP forever" cost claim a reviewer probe measured as wrong: an IP that stops calling
keeps its stale deque entry indefinitely, ~814 bytes/IP, ~776 MiB per 1M distinct IPs ever seen).
`_prune_stale_entries` runs at most once per *observed* day-bucket advance (an amortized,
roughly-once-daily linear pass, not a per-request cost) and now does three things in that one
pass: drops day-bucket dict entries strictly older than the current bucket (safe unconditionally
— a key's day-bucket component never becomes relevant again once a strictly larger bucket has
been observed); prunes every IP's per-minute `deque` down to entries within the trailing 60s of
"now"; and evicts any IP whose deque is left empty. This bounds `_minute_windows` to "IPs active
within roughly the last day", not the process's entire lifetime — an idle IP is reclaimed within
one day-bucket advance of going quiet, not never.

Thread-safety (review round 1, finding I-1): a single `threading.Lock` guards every
read-modify-write across all three stores — `starlette.testclient.TestClient` (this repo's test
surface) drives requests single-threaded, but a real `uvicorn` deployment runs `public_chat` (a
sync `def` route) in FastAPI's threadpool, concurrently by default. `check_message` was always
correctly atomic (its check-then-record for a message happens inside one lock acquisition,
`:210-227` below). The session-create cap's two-step public API
(`check_session_create`/`note_session_created`, pinned by the brief's Interfaces block and by
`tests/test_ratelimit.py`'s unit tests) is NOT atomic on its own — a caller doing
"check, do other work, note" across two separate lock acquisitions leaves a TOCTOU window a
reviewer probe measured concretely: 32 concurrent requests against a cap of 5 minted 32 sessions.
`reserve_session_create` closes that window: check-and-increment in ONE lock acquisition, used by
the route instead of the two-step pair. `check_session_create`/`note_session_created` remain,
unchanged in their own individual atomicity (each still one lock acquisition), for the pinned
unit tests and any future caller that genuinely needs the two-step "may I?" / "I did" split; all
three methods now share the same two lock-held private helpers
(`_session_create_full_locked`/`_increment_session_create_locked`) so there is exactly one
implementation of "is the cap full" and one of "record one more", never two copies to drift.

Accepted trade-off (controller-ruled, round 1): if `reserve_session_create` succeeds (the slot is
charged) but the session mint that follows it fails for an unrelated reason (e.g. a DB error
inside `get_or_create_session`), that slot is still burned — the caller already committed to
minting when it reserved, and un-reserving on a downstream failure would need a third call this
route never makes (mirrors `check_message`'s existing per-minute/per-day slots, which are burned
by admission, not by successful persistence — `app/routes/public_routes.py`'s own docstring, probe
P-K in the review report).
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
        # left in `check_message` (every call) and swept for full eviction of empty entries in
        # `_prune_stale_entries` (once per observed day-bucket advance — module docstring, M-3).
        self._minute_windows: dict[str, deque[float]] = {}

        # Fixed UTC-midnight-bucketed counters. Keys are (identity, day_bucket); a day bucket only
        # needs a count, never individual timestamps, since the whole bucket resets together.
        self._session_day_counts: dict[tuple[str, int], int] = {}
        self._session_create_counts: dict[tuple[str, int], int] = {}

        # The most recent day bucket `_prune_stale_entries` has already cleaned up through — lets
        # pruning run at most once per observed day-bucket advance instead of on every call.
        self._last_pruned_day_bucket: int | None = None

    def _day_bucket(self, now: float) -> int:
        """The UTC-midnight bucket `now` (POSIX epoch seconds) falls into."""
        return int(now // _DAY_SECONDS)

    def _prune_stale_entries(self, now: float, current_day_bucket: int) -> None:
        """Drop everything stale, at most once per observed day-bucket advance (caller holds
        `self._lock`).

        Three sweeps in one pass (module docstring, review round 1 finding M-3):

        1. Day-bucket dict entries strictly older than `current_day_bucket` — safe
           unconditionally, since a key's day-bucket component never becomes relevant again once
           a strictly larger bucket has been observed (buckets only ever increase as `clock()`
           advances in every test and in real wall-clock time).
        2. Every IP's per-minute `deque`, pruned down to entries within the trailing 60s of `now`
           — the same left-prune `check_message` already does per-call, run here too so an IP
           that has gone quiet is not left with a growing shadow deque nobody else prunes for it.
        3. Any IP whose deque is left empty after (2) is evicted from `_minute_windows` entirely —
           the fix for the docstring's previously-wrong "a few dozen bytes forever" claim (a
           reviewer probe measured 776 MiB/1M distinct IPs under the old never-evict behavior).

        A no-op once already caught up to `current_day_bucket`, so normal request traffic within
        the same day pays this cost at most once.
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
        stale_ips: list[str] = []
        for ip, window in self._minute_windows.items():
            while window and now - window[0] >= _MINUTE_SECONDS:
                window.popleft()
            if not window:
                stale_ips.append(ip)
        for ip in stale_ips:
            del self._minute_windows[ip]
        self._last_pruned_day_bucket = current_day_bucket

    def _session_create_full_locked(self, ip: str, day_bucket: int) -> bool:
        """Whether `ip` has already used its `SESSION_CREATE_PER_DAY` budget for `day_bucket`.

        Caller must hold `self._lock`. Shared by `check_session_create`, `reserve_session_create`,
        and nothing else — the single place "is the create cap full" is decided, so
        `check_session_create` (pure check) and `reserve_session_create` (check + record) can
        never disagree about what "full" means.
        """
        count = self._session_create_counts.get((ip, day_bucket), 0)
        return count >= self._settings.session_create_per_day

    def _increment_session_create_locked(self, ip: str, day_bucket: int) -> None:
        """Record one more session create for `ip` in `day_bucket`. Caller must hold `self._lock`.

        Shared by `note_session_created` and `reserve_session_create` — the single place a create
        is actually recorded.
        """
        key = (ip, day_bucket)
        self._session_create_counts[key] = self._session_create_counts.get(key, 0) + 1

    def check_message(self, ip: str, session_id: str | None) -> None:
        """Admit or reject one `/public/chat` message (PRD §9's first two caps).

        Always enforces `RATE_LIMIT_PER_MIN` (sliding one-minute window, keyed by `ip`). Also
        enforces `RATE_LIMIT_PER_DAY` (fixed UTC-midnight window, keyed by `session_id`) — but
        ONLY when `session_id` is not `None`. Controller-approved semantics (test-author report
        `p4-t03-test-author.md`, judgment call #2): the wiring-order pin (limits are checked
        BEFORE a session is actually minted) means a brand-new session's very first message
        necessarily carries `session_id=None` — there is no id yet to key a per-session bucket on,
        so that one message is unavoidably exempt from the per-day cap. It is never exempt from
        the per-minute cap, which is keyed by IP, not session. (Review round 1, finding C-1: the
        route now resolves a real, already-known `session_id` via a read-only PK lookup before
        calling this method whenever the client supplied one that turns out to exist — so `None`
        reaching here means "genuinely about to mint", never "client sent an id but we didn't
        bother checking it".)

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
            self._prune_stale_entries(now, day_bucket)

            window = self._minute_windows.setdefault(ip, deque())
            while window and now - window[0] >= _MINUTE_SECONDS:
                window.popleft()
            if len(window) >= self._settings.rate_limit_per_min:
                raise RateLimitedError(_PER_MIN_MESSAGE)

            day_key = (session_id, day_bucket) if session_id is not None else None
            day_count = 0
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

        Pure check — pairs with `note_session_created`, called by a caller only once a session is
        actually about to be minted (the two-step API the unit tests pin: a rejected attempt must
        not itself consume a slot, so checking never has a side effect). Individually atomic (one
        lock acquisition), but the check-then-note PAIR is NOT atomic across two separate calls —
        `app/routes/public_routes.py` uses `reserve_session_create` instead, precisely to avoid
        that gap (review round 1, finding I-1; module docstring).

        Args:
            ip: the caller's IP address — `SESSION_CREATE_PER_DAY` is a per-IP cap.

        Raises:
            RateLimitedError: `SESSION_CREATE_PER_DAY` sessions have already been created from
                `ip` in the current UTC day.
        """
        now = self._clock()
        day_bucket = self._day_bucket(now)
        with self._lock:
            self._prune_stale_entries(now, day_bucket)
            if self._session_create_full_locked(ip, day_bucket):
                raise RateLimitedError(_SESSION_CREATE_MESSAGE)

    def note_session_created(self, ip: str) -> None:
        """Record that `ip` actually minted one new session just now (pairs with
        `check_session_create`).

        Callers must only call this after `check_session_create` has passed AND a session mint is
        actually going to happen for this request — never speculatively, and never for a request
        that turned out to reuse an existing session. Same non-atomic-as-a-pair caveat as
        `check_session_create` above — prefer `reserve_session_create` for a single request that
        needs check-and-record together.

        Args:
            ip: the caller's IP address, same key `check_session_create` reads.
        """
        now = self._clock()
        day_bucket = self._day_bucket(now)
        with self._lock:
            self._prune_stale_entries(now, day_bucket)
            self._increment_session_create_locked(ip, day_bucket)

    def reserve_session_create(self, ip: str) -> None:
        """Atomically check-and-record one `SESSION_CREATE_PER_DAY` slot for `ip`.

        Review round 1, finding I-1: `check_session_create` then `note_session_created` as two
        separate calls leaves a check-then-act race — under concurrency (`public_chat` is a sync
        route, run in FastAPI's threadpool), multiple requests can all pass the check before any
        of them records, over-admitting past the cap (a reviewer probe: cap 5, 32 concurrent
        minters -> 32 admitted). This method does both under ONE `self._lock` acquisition, so no
        other call can observe or mutate the create-cap state in between — the fix
        `app/routes/public_routes.py` actually calls for the "is this request about to mint a
        session" gate. `check_session_create`/`note_session_created` remain as the separately
        pinned two-step public methods (delegating to the same
        `_session_create_full_locked`/`_increment_session_create_locked` helpers this method
        uses), unchanged, for the unit tests and any caller that genuinely needs the split.

        Args:
            ip: the caller's IP address — `SESSION_CREATE_PER_DAY` is a per-IP cap.

        Raises:
            RateLimitedError: `SESSION_CREATE_PER_DAY` sessions have already been created from
                `ip` in the current UTC day. Nothing is recorded when this raises.
        """
        now = self._clock()
        day_bucket = self._day_bucket(now)
        with self._lock:
            self._prune_stale_entries(now, day_bucket)
            if self._session_create_full_locked(ip, day_bucket):
                raise RateLimitedError(_SESSION_CREATE_MESSAGE)
            self._increment_session_create_locked(ip, day_bucket)
