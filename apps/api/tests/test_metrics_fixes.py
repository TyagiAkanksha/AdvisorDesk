"""Regression tests for phase-6 task-01 review round 1's fix round 1: findings C-1, C-2, I-1, I-2.

Review: `.superpowers/sdd/reports/p6-t01-review.md`. `tests/test_metrics.py` (pinned, untouched by
this fix round) already covers `LatencyTracker`'s core percentile/eviction contract and the
wiring's happy paths — this file exists only to pin the four defects that review found and this
fix round closed, one test group per finding:

- **C-1** (cadence saturation): `chat_latency`'s cadence and its `count=<n>` field are now driven
  by `LatencyTracker.lifetime_count`, a per-key counter that is never capped by the rolling
  window — `snapshot()`/`stats()`'s own window-capped `count` field (pinned by `test_metrics.py`)
  is unchanged and untouched by this fix.
- **C-2** (logs discarded in production): `app.main._configure_logging()` now configures the root
  logger to INFO with a stream handler, guarded (via `logging.basicConfig`'s own built-in
  behavior) to never clobber an already-configured root.
- **I-1** (unbounded keys + full-snapshot-per-request under lock): unmatched requests now bucket
  into the single constant key `"unmatched"`, never the raw path; `observe_and_maybe_log_chat_
  latency` now reads `LatencyTracker.stats`/`lifetime_count` (targeted, single-key) instead of
  `snapshot()` (full, every-key).
- **I-2** (error events pollute first-token): `app.routes.sse.sse_response`'s `on_first_event`
  hook now receives the first SSE block itself; `public_routes.public_chat`'s `_on_first_event`
  closure only records a sample when that block is a genuine `token` event.

Fakes (`FakeEmbedder`, `FailingEmbedder`, `FakeChatLLM`) and the `_post_chat`/`_parse_sse_events`
helpers are trimmed, locally-defined copies of `tests/test_metrics.py`'s and
`tests/test_public_chat_guards.py`'s own shapes (CONVENTIONS.md §10: no cross-test-file imports).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.db import make_session_factory
from app.factory import create_app
from app.routes.metrics import LatencyTracker, observe_and_maybe_log_chat_latency
from app.services.errors import EmbeddingFailedError

# ---------------------------------------------------------------------------
# Fakes (CONVENTIONS.md §10: defined locally, no cross-test-file imports).
# ---------------------------------------------------------------------------


@dataclass
class FakeEmbedder:
    """Deterministic `Embedder` fake — trimmed copy of `tests/test_metrics.py::FakeEmbedder`."""

    vector: list[float]

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        return [self.vector for _ in texts]


class FailingEmbedder:
    """An `Embedder` fake whose `embed_texts` always raises `EmbeddingFailedError` BEFORE any
    token is streamed — trimmed copy of `tests/test_public_chat_guards.py::FailingEmbedder`. This
    is what makes `_generate_chat_stream` yield exactly one `error` event as its FIRST (and only)
    SSE block, the exact scenario finding I-2 pins.
    """

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        raise EmbeddingFailedError("simulated embedding provider failure (FailingEmbedder fake)")


@dataclass
class FakeChatLLM:
    """Scripted `ChatLLM` fake — trimmed copy of `tests/test_metrics.py::FakeChatLLM`. Always
    yields `tokens` regardless of `sources`, since these tests assert timing/metrics, never
    answer content.
    """

    tokens: list[str]

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        yield from self.tokens


def _post_chat(client: TestClient, body: dict[str, object]) -> tuple[int, str, str]:
    """POST `/api/v1/public/chat` via the streaming interface; return (status, content_type, body)
    — trimmed copy of `tests/test_metrics.py::_post_chat`.
    """
    with client.stream("POST", "/api/v1/public/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


def _event_names(body: str) -> list[str]:
    """The ordered `event: <name>` values in an SSE body — just enough parsing for these tests
    (no `data:` payload decoding needed, unlike `tests/test_public_chat_guards.py`'s fuller
    `_parse_sse_events`).
    """
    blocks = [block for block in body.split("\n\n") if block.strip()]
    names = []
    for block in blocks:
        for line in block.split("\n"):
            if line.startswith("event:"):
                names.append(line[len("event:") :].strip())
                break
    return names


# ---------------------------------------------------------------------------
# C-1: cadence must be driven by a LIFETIME counter, not the window-capped count.
# ---------------------------------------------------------------------------


def test_800_chat_observations_produce_exactly_8_cadence_lines_with_lifetime_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """800 calls to `observe_and_maybe_log_chat_latency` (the real cadence-checking seam, driven
    directly — fast, no 800 HTTP requests) against a DEFAULT tracker (`window=500`, so the window
    saturates at request 500) must log the greppable `chat_latency` line exactly 8 times, at
    counts 100, 200, ..., 800 — proving the cadence survives past the window boundary instead of
    firing on every request once `count` (the window-capped field) pins at 500 (the pre-fix bug,
    review finding C-1).
    """
    tracker = LatencyTracker()

    with caplog.at_level(logging.INFO, logger="app.routes.metrics"):
        for _ in range(800):
            observe_and_maybe_log_chat_latency(tracker, 0.1)

    pattern = re.compile(r"chat_latency p50=\d+ p95=\d+ count=(\d+)")
    fired_counts = [
        int(match.group(1))
        for record in caplog.records
        for match in (pattern.search(record.getMessage()),)
        if match is not None
    ]

    assert fired_counts == [100, 200, 300, 400, 500, 600, 700, 800], fired_counts
    # The window-capped `count` field (pinned by tests/test_metrics.py) stays exactly what it
    # always was — capped at `window` (500) — completely unaffected by this fix.
    assert tracker.snapshot()["public_chat"]["count"] == 500


# ---------------------------------------------------------------------------
# C-2: app.main must configure root logging to INFO, guarded against clobbering.
# ---------------------------------------------------------------------------


def test_configure_logging_enables_info_for_metrics_logger_when_root_unconfigured() -> None:
    """With the root logger reset to its un-configured default (no handlers, level WARNING —
    Python's own library default, and what a bare `uvicorn app.main:app` boot sees per the
    review's C-2 probe), `app.main._configure_logging()` raises `app.routes.metrics`'s effective
    level to INFO and gives the root logger a handler to actually emit through.
    """
    import app.main as main_module

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        root.handlers = []
        root.setLevel(logging.WARNING)

        main_module._configure_logging()

        assert logging.getLogger("app.routes.metrics").isEnabledFor(logging.INFO)
        assert root.handlers, "root logger must have at least one handler after configuring"
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)


def test_configure_logging_leaves_a_preconfigured_root_untouched() -> None:
    """A root logger that already has a handler (a test harness, or a future task-02 dictConfig)
    must be left completely alone — `_configure_logging()`'s guard (`logging.basicConfig`'s own
    built-in no-op-when-already-configured behavior) must never clobber it.
    """
    import app.main as main_module

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    sentinel_handler = logging.NullHandler()
    try:
        root.handlers = [sentinel_handler]
        root.setLevel(logging.ERROR)

        main_module._configure_logging()

        assert root.handlers == [sentinel_handler]
        assert root.level == logging.ERROR
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)


# ---------------------------------------------------------------------------
# I-1: unmatched requests bucket into one constant key, never the raw path.
# ---------------------------------------------------------------------------


def test_two_unmatched_paths_bucket_into_one_unmatched_key_not_raw_paths() -> None:
    """Two GETs to two DIFFERENT unknown paths must land in the SAME single `request:unmatched`
    tracker key, with `count == 2` — never a distinct key per raw path (the pre-fix behavior:
    unbounded key growth for any unauthenticated scanner walking 404s, review finding I-1).

    DB-less on purpose (`create_app()` with no `session_factory`) since neither path this test
    hits ever reaches a route that touches the database.
    """
    app = create_app()
    client = TestClient(app)

    response_one = client.get("/api/v1/does-not-exist-one")
    response_two = client.get("/api/v1/does-not-exist-two")

    assert response_one.status_code == 404
    assert response_two.status_code == 404
    snapshot = app.state.latency_tracker.snapshot()
    raw_path_keys = [key for key in snapshot if "does-not-exist" in key]
    assert raw_path_keys == [], snapshot
    assert "request:unmatched" in snapshot, snapshot
    assert snapshot["request:unmatched"]["count"] == 2, snapshot


# ---------------------------------------------------------------------------
# I-2: only a genuine first `token` event records a "public_chat" sample.
# ---------------------------------------------------------------------------


def test_error_first_stream_records_no_public_chat_sample(tmp_engine: Engine) -> None:
    """A `/public/chat` exchange whose FIRST (and only) SSE block is an `error` event — the
    embedding provider failing before any token is streamed, `FailingEmbedder` above — must
    record NOTHING under the reserved `"public_chat"` first-token key. Pre-fix, the generic
    `on_first_event()` hook fired on ANY first item, polluting the metric with error-path timings
    (review finding I-2).
    """
    chat_llm = FakeChatLLM(tokens=["Should ", "never ", "stream."])
    embedder = FailingEmbedder()
    app = create_app(
        session_factory=make_session_factory(tmp_engine), chat_llm=chat_llm, embedder=embedder
    )
    client = TestClient(app)

    status, _content_type, body = _post_chat(
        client, {"message": "A question that fails before any token is streamed."}
    )

    assert status == 200, body
    assert _event_names(body) == ["error"], body
    snapshot = app.state.latency_tracker.snapshot()
    assert "public_chat" not in snapshot, snapshot


def test_token_first_stream_records_public_chat_sample(tmp_engine: Engine) -> None:
    """A normal `/public/chat` exchange whose first SSE block is a genuine `token` event DOES
    record a `"public_chat"` first-token sample — the contrasting happy path for the I-2 fix
    above, so the fix is a filter, not a blanket removal of the metric.
    """
    chat_llm = FakeChatLLM(tokens=["An ", "answer."])
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = create_app(
        session_factory=make_session_factory(tmp_engine), chat_llm=chat_llm, embedder=embedder
    )
    client = TestClient(app)

    status, _content_type, body = _post_chat(client, {"message": "A normal question."})

    assert status == 200, body
    assert _event_names(body)[0] == "token", body
    snapshot = app.state.latency_tracker.snapshot()
    assert "public_chat" in snapshot, snapshot
    assert snapshot["public_chat"]["count"] == 1, snapshot
