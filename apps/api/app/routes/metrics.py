"""Log-based request-timing + first-token latency metrics (PRD §9 "a simple middleware logs
p50/p95", §9.1 "p50/p95 first-token latency on `/public/chat`"; phase-6 task-01). No new endpoint
— the §5 REST surface stays frozen (task brief's own Implementation note): every metric this
module produces is either read back directly off `app.state.latency_tracker` (tests only) or
surfaced through the log lines below.

`LatencyMiddleware` (installed by `app.factory.create_app`) times every HTTP request end to end
and logs one `route=... status=... duration_ms=...` line per request, recording the same duration
into `LatencyTracker` under a `request:`-prefixed per-route key — never the reserved
`PUBLIC_CHAT_KEY` literal below (controller adjudication, phase-6 task-01 dispatch: the two
metrics must never share a bucket, even for `/public/chat` itself, whose own Starlette route name
also happens to be `"public_chat"`). It is a raw ASGI middleware, not
`starlette.middleware.base.BaseHTTPMiddleware`, which buffers a streaming response through an
internal `anyio` memory stream — unacceptable for `/public/chat`'s SSE body (task brief: "wrap,
don't modify event semantics").

`/public/chat`'s first-*token* latency (distinct from the whole-request duration above) is a
metric this middleware cannot see on its own — the SSE body generator, not the ASGI envelope,
knows when the first event is actually produced. `app.routes.public_routes.public_chat` wires
`observe_and_maybe_log_chat_latency` (below) as `app.routes.sse.sse_response`'s optional
`on_first_event` hook — called once, right before the first SSE block is yielded (see that
module's docstring), filtered there to genuine `token` events only (fix round 1, finding I-2) —
which records the sample under `PUBLIC_CHAT_KEY` and, every 100 samples, logs the greppable
`chat_latency p50=<ms> p95=<ms> count=<n>` line phase-7 task-03 greps for the §9.1 metric.

Fix round 1, finding C-1: the cadence (and the log line's own `count=<n>` field) is driven by a
per-key LIFETIME observation counter (`LatencyTracker.lifetime_count`, incremented on every
`observe()` call, never capped) — NOT `snapshot()`/`stats()`'s own `count` field, which is the
CURRENT window size and therefore permanently pinned at `window` once a route's samples exceed
it (a rolling window can never serve as a request counter). `p50`/`p95` in the log line still
come from the current window (`LatencyTracker.stats`, a targeted single-key read — fix round 1,
finding I-1: no full `snapshot()` on this hot path) — only the cadence gate and the reported
`count` needed a lifetime source.

`LatencyTracker.snapshot()` returns SECONDS, the same unit `observe()` receives — millisecond
formatting is applied exactly once, here, at each of the two places a log line is built from it
(controller adjudication) — this keeps the tracker itself a small, generic, unit-agnostic
rolling-window percentile store, reusable for any future route-timing need.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from typing import TypedDict

from fastapi.routing import APIRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

__all__ = [
    "LatencyMiddleware",
    "LatencyTracker",
    "PUBLIC_CHAT_KEY",
    "RouteStats",
    "observe_and_maybe_log_chat_latency",
]

# The reserved first-token snapshot key (controller adjudication, phase-6 task-01 dispatch).
# `LatencyMiddleware`'s own general per-request keys are always built with `_REQUEST_KEY_PREFIX`
# below, so a request's general timing sample can never land in this same bucket.
PUBLIC_CHAT_KEY = "public_chat"

# Prefix for `LatencyMiddleware`'s general per-request timing keys — applied uniformly, to every
# route, guaranteeing no collision with `PUBLIC_CHAT_KEY` above rather than relying on a
# case-by-case check.
_REQUEST_KEY_PREFIX = "request:"

# Fix round 1, finding I-1: every request whose route never matched an `APIRoute` (a 404, or a
# path inside a `Mount` this middleware can't name) buckets into this ONE constant key, never the
# raw request path — `LatencyTracker` never evicts *keys*, only samples within a key, so keying on
# the raw path let an unauthenticated scanner walking N distinct 404 paths grow the tracker's key
# set (and the per-request work under its lock) without bound.
_UNMATCHED_ROUTE_KEY = "unmatched"

# Task brief: "every 100 chat requests logs `chat_latency p50=<ms> p95=<ms> count=<n>`".
_CHAT_LATENCY_LOG_EVERY = 100


class RouteStats(TypedDict):
    """One route's rolling-window percentile summary — `LatencyTracker.snapshot()`'s per-key
    value shape (task brief Interfaces block: `dict[str, {p50, p95, count}]`). `p50`/`p95` are in
    the same unit `observe()` received (seconds — module docstring).
    """

    p50: float
    p95: float
    count: int


def _nearest_rank(sorted_ascending: Sequence[float], percentile: float) -> float:
    """The nearest-rank `percentile` (0-100) over `sorted_ascending`.

    `rank = max(1, ceil(percentile / 100 * n))`, 1-indexed into values already sorted ascending
    (test-author report, phase-6 task-01: the formula every pinned unit test's expected literal
    was hand-computed against).

    Args:
        sorted_ascending: latency samples, ascending order, at least one element.
        percentile: 0-100.

    Returns:
        The value at the computed rank.
    """
    n = len(sorted_ascending)
    rank = max(1, math.ceil(percentile / 100 * n))
    return sorted_ascending[rank - 1]


class LatencyTracker:
    """Rolling-window, per-route latency percentile tracker (task brief Interfaces block).

    One instance is meant to be shared across every request for the lifetime of the app
    (`app.state.latency_tracker`, wired by `app.factory.create_app` — same per-process-singleton
    shape as `app.routes.ratelimit.RateLimiter`), so a `threading.Lock` guards every read and
    write: `public_chat` is a sync route (like every `RateLimiter` caller), run in FastAPI's
    threadpool concurrently by default in a real deployment.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic, window: int = 500) -> None:
        """Build a tracker keeping, per route, only the `window` most recent observations.

        Args:
            clock: CONVENTIONS.md §10's injectable-clock seam (mirrors `RateLimiter`'s own
                `clock` parameter). Stored but never called by this class — `observe()` takes an
                already-measured duration directly, per the task brief's own Interfaces block
                signature — kept only so this constructor's produced interface matches that
                signature exactly, and so a future caller wanting the tracker to measure elapsed
                time itself (rather than being handed one) has a seam to inject a fake clock into.
            window: how many of the most recent observations each route keeps; older ones are
                evicted FIFO as new ones arrive (task brief Step-1: "rolling window evicts
                oldest").
        """
        self._clock = clock
        self._window = window
        self._lock = threading.Lock()
        self._observations: dict[str, deque[float]] = {}
        # Fix round 1, finding C-1: a per-key LIFETIME observation counter, independent of the
        # window-capped `deque` above and never itself capped or evicted. `snapshot()`/`stats()`'s
        # own `count` field stays exactly what it always was (the CURRENT window size, pinned by
        # the unit tests) — this is a second, separate number, read only by `lifetime_count()`
        # below, that a route's own rolling window can never substitute for once samples exceed
        # `window`.
        self._lifetime_counts: dict[str, int] = {}

    def observe(self, route: str, seconds: float) -> None:
        """Record one latency sample for `route`, evicting the oldest sample once `window` is
        full (`collections.deque(maxlen=...)`'s own FIFO eviction).

        Args:
            route: the snapshot key this sample accumulates under.
            seconds: the measured duration, in seconds.
        """
        with self._lock:
            bucket = self._observations.setdefault(route, deque(maxlen=self._window))
            bucket.append(seconds)
            self._lifetime_counts[route] = self._lifetime_counts.get(route, 0) + 1

    def snapshot(self) -> dict[str, RouteStats]:
        """The current per-route `{p50, p95, count}` (task brief Interfaces block), computed
        fresh from each route's current window. `{}` if nothing has ever been observed.
        """
        with self._lock:
            result: dict[str, RouteStats] = {}
            for route, bucket in self._observations.items():
                values = sorted(bucket)
                result[route] = RouteStats(
                    p50=_nearest_rank(values, 50.0),
                    p95=_nearest_rank(values, 95.0),
                    count=len(values),
                )
            return result

    def stats(self, route: str) -> RouteStats | None:
        """The current window-capped `{p50, p95, count}` for exactly ONE `route` — the same
        per-key math `snapshot()` runs, without sorting every OTHER key's bucket under the same
        lock acquisition (fix round 1, finding I-1: `observe_and_maybe_log_chat_latency`'s hot
        path no longer pays for unrelated routes' bucket sizes). `None` if `route` has never been
        observed.
        """
        with self._lock:
            bucket = self._observations.get(route)
            if not bucket:
                return None
            values = sorted(bucket)
            return RouteStats(
                p50=_nearest_rank(values, 50.0),
                p95=_nearest_rank(values, 95.0),
                count=len(values),
            )

    def lifetime_count(self, route: str) -> int:
        """The total number of `observe(route, ...)` calls ever made (fix round 1, finding C-1) —
        never capped by `window`, unlike `stats()`/`snapshot()`'s own `count` field. `0` if `route`
        has never been observed.
        """
        with self._lock:
            return self._lifetime_counts.get(route, 0)


def observe_and_maybe_log_chat_latency(tracker: LatencyTracker, seconds: float) -> None:
    """Record one `/public/chat` first-token latency sample, then — every
    `_CHAT_LATENCY_LOG_EVERY` (100) LIFETIME samples — log the greppable
    `chat_latency p50=<ms> p95=<ms> count=<n>` line phase-7 task-03 greps for the PRD §9.1 metric.

    Fix round 1, finding C-1: the cadence gate and the log line's `count=<n>` both read
    `tracker.lifetime_count(PUBLIC_CHAT_KEY)` — a counter that is never capped by the tracker's
    rolling window — instead of `stats()`/`snapshot()`'s own window-capped `count` (which, once a
    route's samples exceed `window`, is permanently pinned at `window` and can never again be a
    multiple-of-100 gate past the first `window` requests). `p50`/`p95` still come from the
    current window (`tracker.stats`, a single-key read — finding I-1) since the rolling-window
    percentiles themselves are the right statistic; only the cadence/count source was wrong.

    `app.routes.public_routes.public_chat` wires this function as its
    `app.routes.sse.sse_response` `on_first_event` callback, via a closure capturing the elapsed
    seconds and the shared tracker — this function itself takes no `Request`/`Response`, so it
    stays independently unit-testable, the same as `LatencyTracker` above.

    Args:
        tracker: the shared `LatencyTracker` (`app.state.latency_tracker`).
        seconds: the measured first-token latency, in seconds.
    """
    tracker.observe(PUBLIC_CHAT_KEY, seconds)
    logger.info("route=public_chat first_token_ms=%d", round(seconds * 1000))
    lifetime_count = tracker.lifetime_count(PUBLIC_CHAT_KEY)
    if lifetime_count % _CHAT_LATENCY_LOG_EVERY == 0:
        stats = tracker.stats(PUBLIC_CHAT_KEY)
        if stats is not None:  # always true here: `observe()` above just wrote this key.
            logger.info(
                "chat_latency p50=%d p95=%d count=%d",
                round(stats["p50"] * 1000),
                round(stats["p95"] * 1000),
                lifetime_count,
            )


def _route_name(scope: Scope) -> str:
    """The matched route's name, or `_UNMATCHED_ROUTE_KEY` when nothing matched (a 404 —
    `Router.app` never sets `scope["route"]` in that case; FastAPI's own `APIRoute.matches` is
    what sets it on a match, `:832` of `fastapi.routing` — or a path inside a `Mount`, whose
    `scope["route"]` is never an `APIRoute` either).

    Fix round 1, finding I-1: this used to fall back to the raw request path, so every distinct
    unmatched path (e.g. an unauthenticated scanner walking 404s) created its own permanent
    `LatencyTracker` key — unbounded memory growth with no eviction, since the tracker only evicts
    SAMPLES within a key, never keys themselves. Every unmatched request now buckets into the same
    single constant key instead.
    """
    route = scope.get("route")
    if isinstance(route, APIRoute):
        return route.name
    return _UNMATCHED_ROUTE_KEY


class LatencyMiddleware:
    """Raw ASGI middleware timing every HTTP request end to end and logging one
    `route=... status=... duration_ms=...` line per request (module docstring): a general,
    route-agnostic companion to the `/public/chat`-specific first-token metric above.

    Not `starlette.middleware.base.BaseHTTPMiddleware` (module docstring: it buffers a streaming
    response through an internal `anyio` memory stream, which would defeat `/public/chat`'s SSE
    byte-for-byte pass-through). Installed via `app.add_middleware(LatencyMiddleware, tracker=...)`
    in `app.factory.create_app`.
    """

    def __init__(
        self, app: ASGIApp, tracker: LatencyTracker, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Args:
        app: the wrapped ASGI application (Starlette's own middleware-stack convention).
        tracker: the shared `LatencyTracker` every request's general duration is recorded into.
        clock: CONVENTIONS.md §10's injectable-clock seam — defaults to the same `time.monotonic`
            `LatencyTracker.__init__` itself defaults to. Independent of `tracker`'s own `clock`
            (never read by `LatencyTracker.observe`, module docstring) — this one IS called, to
            measure this middleware's own request duration.
        """
        self._app = app
        self._tracker = tracker
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass non-HTTP scopes (`websocket`, `lifespan`) straight through, untimed. For an HTTP
        request: time the FULL call — through to the last byte of the response body, including a
        streamed SSE body's whole lifetime — record it under a `_REQUEST_KEY_PREFIX`-prefixed
        per-route key, and log the one general per-request line.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        start = self._clock()
        status_box: list[int] = []

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_box.append(message["status"])
            await send(message)

        await self._app(scope, receive, send_wrapper)

        duration_seconds = self._clock() - start
        route_name = _route_name(scope)
        status = status_box[0] if status_box else 0
        self._tracker.observe(f"{_REQUEST_KEY_PREFIX}{route_name}", duration_seconds)
        logger.info(
            "route=%s status=%s duration_ms=%d",
            route_name,
            status,
            round(duration_seconds * 1000),
        )
