"""Failing (RED) tests for the phase-6 task-01 latency-metrics middleware: `LatencyTracker`
(unit) and the `/public/chat` + `/healthz` wiring (endpoint) it backs.

Task brief: docs/plans/phase-6-deployment/task-01-metrics-middleware.md. Spec: advisordesk-prd.md
§9 "Streaming latency" ("a simple middleware logs p50/p95") and §9.1 ("p50/p95 first-token
latency on `/public/chat`"). CONVENTIONS.md §10 (injectable clock, TestClient over the real HTTP
surface, no cross-test-file imports, no sleeps in tests).

`app.routes.metrics` does not exist yet (imported below for `LatencyTracker`): every test in this
file is expected to fail at collection (`ModuleNotFoundError`) until the implementer (a separate
agent) creates `app/routes/metrics.py` and wires the ASGI middleware into `app/factory.py` (plus
the `on_first_event` hook into `app/routes/sse.py`) — that failure IS the RED evidence this file
exists to produce. Even past collection, every wiring test would still fail: `app.state` carries
no `latency_tracker` attribute at all yet.

I001 note (established precedent — `tests/test_ratelimit.py`'s own module docstring, when that
file was originally authored against a not-yet-existing `app/routes/ratelimit.py`):
`from app.routes.metrics import LatencyTracker` sits in the THIRD-PARTY import block below, not
the first-party `app.*` block — ruff's isort resolves first-party membership by checking the
module actually exists on disk, and `app/routes/metrics.py` doesn't exist yet. Once the
implementer creates it, `uv run ruff check` will demand the same reorder (move the import down
into the `app.*` block) — expected, not a defect in this file today.

Fakes (`FakeClock`, `FakeEmbedder`, `FakeChatLLM`) are defined locally per CONVENTIONS.md §10 /
the test-author brief: no cross-test-file imports. `FakeEmbedder`/`FakeChatLLM` are trimmed
copies of `tests/test_public_chat.py`'s own shapes (same pattern `tests/test_ratelimit.py` already
follows for the identical reason); the wiring tests below never seed `Content`/`Chunk` rows, so
every admitted chat request takes the refusal path over an empty index — what these tests assert
is *how long the exchange took and whether it was recorded*, never what the answer contains.
`FakeEmbedder(vector=[0.0] * 8)` mirrors `tests/test_ratelimit.py`'s own precedent of an
intentionally-wrong-dimension (non-1024) vector: with zero `Chunk` rows in the throwaway schema,
pgvector's `<=>` never actually evaluates against any stored row, so the query vector's dimension
is never checked.

Judgment calls (test-author, flagged for controller/implementer review — none of them are
specified verbatim by the brief's Interfaces block):

1. **Units returned by `LatencyTracker.snapshot()`.** `observe(route: str, seconds: float)`'s
   parameter is explicitly named `seconds`; nothing in the Interfaces block says `snapshot()`
   converts to milliseconds internally. This file assumes `LatencyTracker` is unit-agnostic —
   `snapshot()`'s `p50`/`p95` are plain floats in the SAME unit fed to `observe()` (seconds,
   unconverted) — and that the `<ms>` formatting named in the brief's greppable log-line spec
   (`chat_latency p50=<ms> p95=<ms> count=<n>`) is a MIDDLEWARE/log-formatting concern (multiply
   by 1000 when building that one log line), not part of the tracker's own data contract. This
   keeps `LatencyTracker` a small, generic, reusable percentile tracker. If the implementer
   instead designs `snapshot()` to already return milliseconds, exactly two assertions below
   (`test_snapshot_nearest_rank_p50_p95_over_100_known_observations`,
   `test_rolling_window_evicts_oldest_observations_keeps_only_the_last_window`) need their
   literal expected numbers divided by 1000 — a small, mechanical, isolated fix that does not
   touch the eviction logic, the empty-snapshot test, the route-independence test, or any wiring
   test (none of which pin an exact seconds-vs-ms value).
2. **The first-token metric's snapshot key.** Assumed to be the literal string `"public_chat"` —
   mirroring the route's own `operation_id`/endpoint-function name (`app/routes/public_routes.py`)
   — per the dispatch brief's own wording ("a chat request records a `public_chat` first-token
   sample > 0"). `test_chat_request_records_public_chat_first_token_sample_above_zero` asserts
   `count >= 1` rather than `== 1` specifically so it stays valid whether or not a general
   per-request duration sample for `/public/chat` ALSO happens to be recorded under this same key.
3. **The general per-request-timing key** (exercised by the `GET /healthz` test) is deliberately
   NOT pinned to an exact string — the Interfaces block does not say whether the ASGI middleware
   keys routes by raw path, FastAPI `operation_id`, or Starlette route name.
   `test_healthz_records_request_timing_sample_but_no_first_token_sample` instead asserts on an
   aggregate observation-count delta (before vs. after one request), which is correct under any
   of those naming schemes.
4. **The every-100-requests log cadence.** Driven directly through
   `LatencyTracker.observe("public_chat", ...)`, called 99 times — the only documented public
   seam for recording a sample — followed by exactly ONE real `TestClient` chat request, per this
   dispatch's own explicit authorization ("the every-100-requests log cadence may be pinned at
   whatever seam keeps the test FAST and deterministic ... e.g., driving the tracker/middleware
   seam directly rather than 100 real TestClient chat requests"). The greppable log LINE ITSELF is
   still asserted only via `caplog`, emitted by the real code triggered by that one real request
   (`test_hundredth_chat_request_logs_greppable_chat_latency_line`). This assumes the cadence
   check is a function of the `"public_chat"` key's own accumulated `count` reaching a multiple of
   100, not a separate, tracker-independent request counter — if the implementer's mechanism
   differs, this test's 99-observation setup needs revisiting with the controller.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

import pytest
from app.routes.metrics import LatencyTracker
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.db import make_session_factory
from app.factory import create_app

# ---------------------------------------------------------------------------
# Fakes: `Callable[[], float]` clock, `Embedder`, and `ChatLLM` seams (defined
# locally, per CONVENTIONS.md §10 / the test-author brief).
# ---------------------------------------------------------------------------


@dataclass
class FakeClock:
    """A settable, callable clock double — `Callable[[], float]`, matching `LatencyTracker`'s
    injectable `clock` seam (CONVENTIONS.md §10: "clock into the rate limiter" is one of the
    explicitly named injectable seams in this codebase; `LatencyTracker`'s own Interfaces-block
    signature names an identical seam). Passed explicitly into every tracker unit test below so
    none of them depends on real wall-clock time for any reason, even though `observe()` takes an
    already-measured `seconds` duration directly and so may never call this at all.
    """

    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass
class FakeEmbedder:
    """Deterministic `Embedder` fake — trimmed copy of `tests/test_public_chat.py::FakeEmbedder`'s
    shape (CONVENTIONS.md §10: no cross-test-file imports). No `Chunk` rows are ever seeded in
    this file's DB fixtures (module docstring: every chat request here takes the refusal path
    over an empty index, `tests/test_ratelimit.py`'s own precedent), so the vector's
    dimension/value never matters for retrieval correctness — only that `embed_texts` returns
    something well-formed.
    """

    vector: list[float]

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        return [self.vector for _ in texts]


@dataclass
class FakeChatLLM:
    """Scripted `ChatLLM` fake — trimmed copy of `tests/test_public_chat.py::FakeChatLLM`'s shape.
    Always yields `tokens`, regardless of `sources` — the refusal-vs-grounded distinction is
    irrelevant here, since every test in this file asserts timing/metrics, never answer content.
    """

    tokens: list[str]

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        yield from self.tokens


def _post_chat(client: TestClient, body: dict[str, object]) -> tuple[int, str, str]:
    """POST `/api/v1/public/chat` via the streaming interface; return (status, content_type, body).

    Trimmed copy of `tests/test_public_chat.py::_post_chat`'s shape (CONVENTIONS.md §10: no
    cross-test-file imports) — `client.stream(...)` + `iter_text()` reads the full response body
    before returning, so the streaming code path (where the metrics middleware's `on_first_event`
    hook and its post-response request timing both fire) actually completes.
    """
    with client.stream("POST", "/api/v1/public/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


# ---------------------------------------------------------------------------
# 1. `LatencyTracker` unit tests (fake clock, no HTTP; brief Step-1).
# ---------------------------------------------------------------------------


def test_snapshot_nearest_rank_p50_p95_over_100_known_observations() -> None:
    """100 known observations (10ms, 20ms, ..., 1000ms, fed to `observe()` as seconds) -> exact
    nearest-rank p50/p95, hand-computed: rank = ceil(percentile/100 * n), 1-indexed into the
    values sorted ascending (here, already ascending by construction, no ties).

    n=100: p50 rank = ceil(0.50 * 100) = 50 -> the 50th-smallest value = 500ms = 0.5s.
           p95 rank = ceil(0.95 * 100) = 95 -> the 95th-smallest value = 950ms = 0.95s.

    See the module docstring's judgment call #1 for the seconds-vs-milliseconds assumption these
    two literals (`500 / 1000`, `950 / 1000`) encode.
    """
    tracker = LatencyTracker(clock=FakeClock())
    observations_seconds = [milliseconds / 1000 for milliseconds in range(10, 1001, 10)]
    assert len(observations_seconds) == 100  # sanity: 10, 20, ..., 1000ms, inclusive.
    for seconds in observations_seconds:
        tracker.observe("known_sequence_route", seconds)

    snapshot = tracker.snapshot()

    assert snapshot["known_sequence_route"]["count"] == 100
    assert snapshot["known_sequence_route"]["p50"] == 500 / 1000
    assert snapshot["known_sequence_route"]["p95"] == 950 / 1000


def test_rolling_window_evicts_oldest_observations_keeps_only_the_last_window() -> None:
    """A small `window=3` keeps only the 3 MOST RECENT observations — the oldest are evicted, one
    at a time, as new ones arrive (FIFO), not e.g. a random subset. Five observations
    (100ms..500ms, fed in ascending order) leave exactly [300, 400, 500]ms in the window:

    count = 3. p50 rank = ceil(0.50 * 3) = 2 -> the 2nd-smallest of the surviving three = 400ms.
             p95 rank = ceil(0.95 * 3) = 3 -> the 3rd-smallest of the surviving three = 500ms.
    """
    tracker = LatencyTracker(clock=FakeClock(), window=3)
    for milliseconds in (100, 200, 300, 400, 500):
        tracker.observe("eviction_route", milliseconds / 1000)

    snapshot = tracker.snapshot()

    assert snapshot["eviction_route"]["count"] == 3
    assert snapshot["eviction_route"]["p50"] == 400 / 1000
    assert snapshot["eviction_route"]["p95"] == 500 / 1000


def test_empty_tracker_snapshot_is_empty_dict() -> None:
    """A `LatencyTracker` that has never observed anything reports `snapshot() == {}` — no route
    keys at all, not empty per-route stat blocks. Constructed with zero arguments (both `clock`
    and `window` default per the Interfaces block) to also pin that the bare constructor works.
    """
    tracker = LatencyTracker()

    assert tracker.snapshot() == {}


def test_snapshot_keys_are_independent_per_route() -> None:
    """`snapshot()`'s shape is `dict[str, {p50, p95, count}]`, keyed by `route` (Interfaces
    block) — two distinct routes accumulate independently, never mixed into one shared bucket.
    """
    tracker = LatencyTracker(clock=FakeClock())
    tracker.observe("route_a", 0.010)
    tracker.observe("route_a", 0.020)
    tracker.observe("route_b", 0.100)

    snapshot = tracker.snapshot()

    assert snapshot["route_a"]["count"] == 2
    assert snapshot["route_b"]["count"] == 1
    # n=2, p50 rank = ceil(0.5 * 2) = 1 -> the 1st-smallest of route_a's two observations.
    assert snapshot["route_a"]["p50"] == 0.010
    # n=1: every percentile rank is 1 -> the sole observation.
    assert snapshot["route_b"]["p50"] == 0.100
    assert snapshot["route_b"]["p95"] == 0.100


# ---------------------------------------------------------------------------
# 2. Wiring tests: `TestClient` + fake LLM/embedder over the real HTTP surface
#    (brief Step-5).
# ---------------------------------------------------------------------------


def test_chat_request_records_public_chat_first_token_sample_above_zero(
    tmp_engine: Engine,
) -> None:
    """A `/public/chat` request records a positive first-token latency sample under the
    `"public_chat"` snapshot key (module docstring, judgment call #2) — asserted via a real
    `TestClient` request, not by calling any middleware/tracker seam directly.
    """
    chat_llm = FakeChatLLM(tokens=["An ", "answer."])
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = create_app(
        session_factory=make_session_factory(tmp_engine), chat_llm=chat_llm, embedder=embedder
    )
    client = TestClient(app)
    assert app.state.latency_tracker.snapshot() == {}

    status, _content_type, body = _post_chat(client, {"message": "A question."})

    assert status == 200, body
    snapshot = app.state.latency_tracker.snapshot()
    assert "public_chat" in snapshot, snapshot
    assert snapshot["public_chat"]["count"] >= 1, snapshot
    assert snapshot["public_chat"]["p50"] > 0, snapshot
    assert snapshot["public_chat"]["p95"] > 0, snapshot


def test_healthz_records_request_timing_sample_but_no_first_token_sample() -> None:
    """A plain `GET /api/v1/healthz` records a general request-timing sample SOMEWHERE in the
    tracker (module docstring, judgment call #3: asserted via an aggregate count delta, not an
    exact key name) but never creates a `"public_chat"` first-token entry — that key is only ever
    written by the `on_first_event` hook on an actual `/public/chat` stream, which this request
    never touches.

    DB-less on purpose (`create_app()` with no `session_factory` — CONVENTIONS.md §5: `create_app`
    must succeed with no database) since `GET /healthz` itself never touches one; this test needs
    no `tmp_engine`/`db_session` fixture and so runs even when `TEST_DATABASE_URL` is unset.
    """
    app = create_app()
    client = TestClient(app)
    before = app.state.latency_tracker.snapshot()
    assert before == {}

    response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    after = app.state.latency_tracker.snapshot()
    before_total = sum(entry["count"] for entry in before.values())
    after_total = sum(entry["count"] for entry in after.values())
    assert after_total > before_total, after
    assert "public_chat" not in after, after


def test_hundredth_chat_request_logs_greppable_chat_latency_line(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Every 100 chat requests, the middleware logs a line matching
    `chat_latency p50=\\d+ p95=\\d+ count=\\d+` (the brief's own regex; phase-7 task-03 greps this
    exact format for the §9.1 metric).

    Cadence driven directly through `LatencyTracker.observe("public_chat", ...)` 99 times (module
    docstring, judgment call #4 — this dispatch's own sanctioned fast/deterministic seam), then
    exactly ONE real `TestClient` chat request pushes the count to 100 and must trigger the log
    line through the real middleware code path — the log line itself is asserted only via
    `caplog`, from that one real request, never fabricated directly.
    """
    chat_llm = FakeChatLLM(tokens=["An ", "answer."])
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = create_app(
        session_factory=make_session_factory(tmp_engine), chat_llm=chat_llm, embedder=embedder
    )
    tracker = app.state.latency_tracker
    for _ in range(99):
        tracker.observe("public_chat", 0.1)
    client = TestClient(app)

    with caplog.at_level(logging.INFO):
        status, _content_type, body = _post_chat(client, {"message": "Trigger the periodic log."})

    assert status == 200, body
    pattern = re.compile(r"chat_latency p50=\d+ p95=\d+ count=\d+")
    matches = [
        record.getMessage() for record in caplog.records if pattern.search(record.getMessage())
    ]
    assert matches, [record.getMessage() for record in caplog.records]
