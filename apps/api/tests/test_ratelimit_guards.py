"""Fix-round-1 regression pins for phase-4 task-03 rate limiting (review report
`.superpowers/sdd/reports/p4-t03-review.md`).

`tests/test_ratelimit.py` (pinned) covers the 12 tests the task-03 test-author authored against
the original brief; this NEW file (not pinned, this fix round's own) pins exactly the properties
a reviewer's mutation battery found untested there, plus the two behavior changes the review's
Critical/Important findings required:

- **C-1 regression** (`test_endpoint_unknown_session_id_after_create_cap_exhausted_is_rejected_
  not_bypassed`): PRD §5.3 — a `session_id` that is absent OR UNKNOWN both mint a session
  "subject to the per-IP creation cap" (§9). Round 0 gated the create cap on `session_id is None`
  only; a syntactically-valid, never-issued UUID bypassed it entirely (reviewer probe P-1: 8
  consecutive random UUIDs minted 8 fresh sessions after the cap was exhausted). Re-runs that
  exact scenario against the fixed route and asserts a 429, not a bypass.
- **I-1 regression** (`test_reserve_session_create_is_atomic_under_concurrent_callers`):
  `check_session_create` then `note_session_created` as two separate lock acquisitions let
  concurrent callers all pass the check before any of them recorded (reviewer probe P-E2: cap 5,
  32 concurrent callers -> 32 admitted). Pins `RateLimiter.reserve_session_create`'s atomicity
  directly with real threads + a `threading.Barrier` — deterministic (the assertion never depends
  on scheduling order, only on whether the critical section is truly one atomic unit), no sleeps.
- **M-1** (`test_check_message_per_min_sliding_window_kills_fixed_bucket_mutant`): mutant
  `M5_fixed_not_sliding_minute` (a fixed `floor(t/60)` bucket) passed every test in
  `test_ratelimit.py` untouched — none of them distinguish a true sliding window from a fixed
  one. Uses the review's own killing case (10 admissions at t=59, an 11th at t=61).
- **M-2** (`test_prune_stale_entries_evicts_old_day_buckets_and_idle_minute_windows`): mutant
  `M4_no_pruning` (a no-op `_prune_stale_entries`) also passed every existing test. White-box
  (this file may read `RateLimiter`'s private stores — CONVENTIONS.md §10's "simulate actual
  usage" rule governs behavioral tests; a property the module docstring itself advertises, that
  no other test observes at all, is exactly what a internals assertion is for here) — asserts the
  day-scoped dicts and the per-minute window dict actually shrink after a day-bucket advance,
  which also covers M-3's "shed empty per-IP deque keys" fix.
- **M-4** (`test_route_never_reserves_a_session_create_slot_when_check_message_rejects`,
  `test_route_calls_check_message_before_reserve_session_create_on_the_admitted_path`): mutant
  `M12_note_before_check_message` (recording a session create before `check_message` ran) also
  passed every existing test — none of them inspect the ROUTE's call order, only
  `RateLimiter`'s own (already-correct) internal atomicity. A `RecordingRateLimiter` duck-typed
  fake (test files are not mypy-checked, `pyproject.toml`'s `files = ["app"]`, same duck-typing
  precedent as `test_ratelimit.py`'s own `FakeEmbedder`/`FakeChatLLM`) injected through
  `create_app(rate_limiter=...)` pins the route's actual call sequence directly.

Fakes/helpers below (`FakeClock`, `FakeChatLLM`, `FakeEmbedder`, `SseEvent`/`_parse_sse_events`/
`_post_chat_stream`, `_build_app`) are trimmed copies of `tests/test_ratelimit.py`'s own
(CONVENTIONS.md §10: no cross-test-file imports) — same shapes, same rationale.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.routes.ratelimit import RateLimiter
from app.services.errors import RateLimitedError

_DAY_SECONDS = 86400.0
# noon, day 46 — same fixed anchor as test_ratelimit.py
_MID_DAY_ANCHOR = 46 * _DAY_SECONDS + 43_200


@dataclass
class FakeClock:
    """A settable epoch-seconds clock double — trimmed copy of `test_ratelimit.py::FakeClock`."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def set(self, value: float) -> None:
        self.now = value


# ---------------------------------------------------------------------------
# 1. Unit: the sliding-window property (M-1) and pruning (M-2/M-3).
# ---------------------------------------------------------------------------


def test_check_message_per_min_sliding_window_kills_fixed_bucket_mutant() -> None:
    """Review round 1, finding M-1: the review's own killing case for mutant
    `M5_fixed_not_sliding_minute`. 10 admissions all at t=59 (a fixed `floor(t/60)` bucket puts
    them in bucket 0); one more at t=61 falls in fixed-bucket 1 — a DIFFERENT bucket, so a
    fixed-window implementation would incorrectly ADMIT it, believing the window just reset. Only
    2 real seconds have elapsed, well inside a true 60s sliding window, so a correct
    implementation must still reject. `test_ratelimit.py`'s own 30s counter-case (test 3) does
    NOT distinguish the two: a fixed bucket also rejects at t+30 (still bucket 0) and admits at
    t+61 (bucket rolled over the same way a sliding window's would) — only a boundary case
    straddling a FIXED bucket edge while staying inside 60 real seconds tells them apart.
    """
    clock = FakeClock(now=59.0)
    limiter = RateLimiter(Settings(), clock=clock)

    for _ in range(10):
        limiter.check_message("172.16.0.1", "session-sliding")

    clock.set(61.0)

    with pytest.raises(RateLimitedError):
        limiter.check_message("172.16.0.1", "session-sliding")


def test_prune_stale_entries_evicts_old_day_buckets_and_idle_minute_windows() -> None:
    """Review round 1, finding M-2 (mutant `M4_no_pruning` passed every existing test) and M-3
    (an idle IP's per-minute `deque` used to be kept forever, never evicted — a reviewer probe
    measured ~776 MiB/1M distinct IPs under the old behavior). Seeds five distinct IPs/sessions
    plus one session-create on day bucket 0, crosses a day-bucket boundary (also well past the
    60s sliding window every day-0 entry needs to still be "current"), triggers one more call for
    a SIXTH, brand-new identity, and asserts every day-0-only entry is gone from all three
    internal stores — not merely "still correct", but actually bounded, which is the property
    none of `test_ratelimit.py`'s 12 tests observe (they only ever check raise/no-raise).
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(), clock=clock)

    for i in range(5):
        limiter.check_message(f"10.0.0.{i}", f"session-{i}")
    limiter.check_session_create("10.0.0.99")
    limiter.note_session_created("10.0.0.99")

    assert len(limiter._minute_windows) == 5
    assert len(limiter._session_day_counts) == 5
    assert len(limiter._session_create_counts) == 1

    # Cross into day-bucket 1: > 60s past every day-0 admission above, so every day-0 minute
    # window is also stale, not just the day-bucket dicts.
    clock.set(_DAY_SECONDS + 10.0)

    limiter.check_message("10.0.0.new", "session-new")

    assert list(limiter._minute_windows) == ["10.0.0.new"], limiter._minute_windows
    assert len(limiter._session_day_counts) == 1
    assert len(limiter._session_create_counts) == 0


# ---------------------------------------------------------------------------
# 2. Unit: `reserve_session_create` atomicity under concurrency (I-1 regression).
# ---------------------------------------------------------------------------


def test_reserve_session_create_is_atomic_under_concurrent_callers() -> None:
    """Review round 1, finding I-1: `check_session_create` then `note_session_created` as two
    separate lock acquisitions let concurrent callers all pass the check before any of them
    recorded (reviewer probe P-E2, the route's exact shape: cap 5, 32 concurrent minters with a
    2ms gap between the two calls -> 32 sessions minted, 27 over the cap). This reproduces that
    probe against `reserve_session_create` — a `threading.Barrier` releases every thread's single
    call as simultaneously as the platform allows, so a non-atomic implementation would
    over-admit here too. A fixed `FakeClock` value (never advanced, read concurrently) removes
    any dependency on wall-clock timing — the assertion is deterministic: exactly `cap` threads
    are admitted and exactly `thread_count - cap` are rejected, every run, regardless of
    scheduling order, because the only thing that determines the outcome is whether
    check-and-record happens as one atomic unit.
    """
    cap = 5
    thread_count = 32
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    limiter = RateLimiter(Settings(session_create_per_day=cap), clock=clock)
    barrier = threading.Barrier(thread_count)
    counts_lock = threading.Lock()
    admitted = 0
    rejected = 0

    def worker() -> None:
        nonlocal admitted, rejected
        barrier.wait()
        try:
            limiter.reserve_session_create("203.0.113.50")
        except RateLimitedError:
            with counts_lock:
                rejected += 1
        else:
            with counts_lock:
                admitted += 1

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert admitted == cap, (admitted, rejected)
    assert rejected == thread_count - cap, (admitted, rejected)
    day_bucket = limiter._day_bucket(_MID_DAY_ANCHOR)
    assert limiter._session_create_counts[("203.0.113.50", day_bucket)] == cap


# ---------------------------------------------------------------------------
# 3. Endpoint: route call-order pin (M-4) via a recording fake limiter.
# ---------------------------------------------------------------------------


@dataclass
class FakeEmbedder:
    """Deterministic `Embedder` fake — trimmed copy of `test_ratelimit.py::FakeEmbedder`."""

    vector: list[float]
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [self.vector for _ in texts]


@dataclass
class FakeChatLLM:
    """Scripted, recording `ChatLLM` fake — trimmed copy of `test_ratelimit.py::FakeChatLLM`."""

    refusal_tokens: list[str] = field(
        default_factory=lambda: ["No published guidance covers this."]
    )
    calls: list[tuple[str, str, tuple[object, ...]]] = field(default_factory=list)

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        self.calls.append((system, question, tuple(sources)))
        yield from self.refusal_tokens


@dataclass
class RecordingRateLimiter:
    """Duck-typed fake standing in for `app.routes.ratelimit.RateLimiter` at the route level.

    Records the ORDER `public_chat` calls its two methods in — `RateLimiter`'s own unit tests
    (`test_ratelimit.py`, this file's section 1/2 above) already pin each method's individual
    correctness in isolation; this fake instead pins what the ROUTE does with them, which mutant
    `M12_note_before_check_message` showed was completely unobserved (review round 1, M-4).
    `check_session_create`/`note_session_created` are included for duck-type completeness (the
    route does not call them today — it calls `reserve_session_create` instead — but keeping the
    fake's surface matching `RateLimiter`'s full public API means it stays a valid stand-in if
    that ever changes).
    """

    raise_on_check_message: bool = False
    calls: list[str] = field(default_factory=list)

    def check_message(self, ip: str, session_id: str | None) -> None:
        self.calls.append("check_message")
        if self.raise_on_check_message:
            raise RateLimitedError("per-minute cap exceeded (fake)")

    def reserve_session_create(self, ip: str) -> None:
        self.calls.append("reserve_session_create")

    def check_session_create(self, ip: str) -> None:
        self.calls.append("check_session_create")

    def note_session_created(self, ip: str) -> None:
        self.calls.append("note_session_created")


def _build_app_with_fake_limiter(
    tmp_engine: Engine, *, fake_limiter: RecordingRateLimiter
) -> FastAPI:
    """Build the app with `fake_limiter` wired through `create_app`'s `rate_limiter=` seam.

    `cast(RateLimiter, fake_limiter)` only satisfies mypy's opinion of `create_app`'s signature —
    tests are never mypy-checked (`pyproject.toml`'s `files = ["app"]`), so this is purely
    documentation of intent, not a real static guarantee; the duck-typed fake works at runtime
    because Python does not enforce parameter types.
    """
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        chat_llm=FakeChatLLM(),
        embedder=FakeEmbedder(vector=[0.0] * 8),
        rate_limiter=cast(RateLimiter, fake_limiter),
    )


def test_route_never_reserves_a_session_create_slot_when_check_message_rejects(
    tmp_engine: Engine,
) -> None:
    """Review round 1, finding M-4: the specific bug pattern mutant `M12_note_before_check_message`
    introduces (a per-minute rejection still burning a create slot) reproduced at the route level
    — a `check_message` breach must short-circuit before `reserve_session_create` ever runs.
    """
    fake_limiter = RecordingRateLimiter(raise_on_check_message=True)
    client = TestClient(_build_app_with_fake_limiter(tmp_engine, fake_limiter=fake_limiter))

    response = client.post("/api/v1/public/chat", json={"message": "Hello."})

    assert response.status_code == 429, response.text
    assert response.headers["content-type"].startswith("application/json"), response.headers
    assert response.json()["error"]["code"] == "rate_limited"
    assert fake_limiter.calls == ["check_message"], fake_limiter.calls


def test_route_calls_check_message_before_reserve_session_create_on_the_admitted_path(
    tmp_engine: Engine,
) -> None:
    """Review round 1, finding M-4, the companion admitted-path pin: when nothing rejects, the
    route still calls `check_message` before `reserve_session_create`, in that exact order —
    pinning the "right" order the round-0 implementation already had, that no test verified.
    """
    fake_limiter = RecordingRateLimiter(raise_on_check_message=False)
    client = TestClient(_build_app_with_fake_limiter(tmp_engine, fake_limiter=fake_limiter))

    with client.stream("POST", "/api/v1/public/chat", json={"message": "Hello."}) as response:
        "".join(response.iter_text())
        status = response.status_code

    assert status == 200, status
    assert fake_limiter.calls == ["check_message", "reserve_session_create"], fake_limiter.calls


# ---------------------------------------------------------------------------
# 4. Endpoint: C-1 regression — an unknown session_id no longer bypasses the create cap.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SseEvent:
    """One parsed `event:`/`data:` block — trimmed copy of `test_ratelimit.py::SseEvent`."""

    name: str
    data: dict[str, object]


def _parse_sse_events(body: str) -> list[SseEvent]:
    """Trimmed copy of `test_ratelimit.py::_parse_sse_events`."""
    events: list[SseEvent] = []
    blocks = [block for block in body.split("\n\n") if block.strip()]
    for block in blocks:
        lines = [line for line in block.split("\n") if line]
        event_lines = [line for line in lines if line.startswith("event:")]
        data_lines = [line for line in lines if line.startswith("data:")]
        assert len(event_lines) == 1, f"expected exactly one 'event:' line in block {block!r}"
        assert len(data_lines) == 1, f"expected exactly one 'data:' line in block {block!r}"
        name = event_lines[0][len("event:") :].strip()
        raw_data = data_lines[0][len("data:") :].strip()
        events.append(SseEvent(name=name, data=json.loads(raw_data)))
    return events


def _post_chat_stream(client: TestClient, body: dict[str, object]) -> tuple[int, str, str]:
    """Trimmed copy of `test_ratelimit.py::_post_chat_stream`."""
    with client.stream("POST", "/api/v1/public/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


def _build_app(
    tmp_engine: Engine, *, settings: Settings, chat_llm: FakeChatLLM, embedder: FakeEmbedder
) -> FastAPI:
    """Trimmed copy of `test_ratelimit.py::_build_app`, wiring a REAL `RateLimiter`."""
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=settings,
        chat_llm=chat_llm,
        embedder=embedder,
        rate_limiter=RateLimiter(settings),
    )


def test_endpoint_unknown_session_id_after_create_cap_exhausted_is_rejected_not_bypassed(
    tmp_engine: Engine,
) -> None:
    """Review round 1, finding C-1 — re-run of the reviewer's probe P-1. PRD §5.3: a `session_id`
    that is absent OR UNKNOWN both mint a session "subject to the per-IP creation cap" (§9).
    Round 0 gated the create cap on `session_id is None` only, so a client with
    `SESSION_CREATE_PER_DAY` exhausted could keep minting fresh sessions (and serving fresh LLM
    answers) indefinitely by sending a syntactically-valid, never-issued UUID instead of omitting
    `session_id` — the reviewer's probe P-1 measured 8 consecutive random UUIDs minting 8 fresh
    sessions and serving 8 LLM answers after the cap was already exhausted. This test reproduces
    that exact scenario end to end (exhaust the cap honestly, then send one random UUID) and
    asserts the fix: the random UUID now gets the identical 429 `rate_limited` envelope an honest
    mint attempt would, with zero additional LLM/embedder calls — the loophole is closed, not
    merely narrowed.
    """
    settings = Settings(rate_limit_per_min=100, rate_limit_per_day=1000, session_create_per_day=2)
    chat_llm = FakeChatLLM()
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = _build_app(tmp_engine, settings=settings, chat_llm=chat_llm, embedder=embedder)
    client = TestClient(app, client=("198.51.100.77", 50000))

    for _ in range(2):
        status, content_type, body = _post_chat_stream(client, {"message": "Mint a session."})
        assert status == 200, body
        assert content_type.startswith("text/event-stream"), content_type

    calls_before = (len(chat_llm.calls), len(embedder.calls))

    garbage_session_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/public/chat",
        json={"session_id": garbage_session_id, "message": "Sneak past the cap."},
    )

    assert response.status_code == 429, response.text
    assert response.headers["content-type"].startswith("application/json"), response.headers
    envelope = response.json()
    assert envelope["error"]["code"] == "rate_limited"
    assert isinstance(envelope["error"]["message"], str) and envelope["error"]["message"]
    assert (len(chat_llm.calls), len(embedder.calls)) == calls_before


def test_endpoint_known_session_id_still_bypasses_only_the_create_cap_not_the_day_cap(
    tmp_engine: Engine,
) -> None:
    """Companion sanity pin: the C-1 fix must not overcorrect. A real, previously-minted session
    id is still recognized as KNOWN (the read-only PK lookup finds it) and therefore still
    exempt from `SESSION_CREATE_PER_DAY` (resuming a real session is not "minting"), while still
    fully subject to `RATE_LIMIT_PER_DAY` — proving the fix distinguishes "known" from "unknown"
    correctly rather than, say, treating every non-`None` id as exempt from every cap.
    """
    settings = Settings(rate_limit_per_min=100, rate_limit_per_day=2, session_create_per_day=1)
    chat_llm = FakeChatLLM()
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = _build_app(tmp_engine, settings=settings, chat_llm=chat_llm, embedder=embedder)
    client = TestClient(app, client=("198.51.100.78", 50000))

    status, _content_type, mint_body = _post_chat_stream(client, {"message": "Mint a session."})
    assert status == 200, mint_body
    session_id = str(
        next(e for e in _parse_sse_events(mint_body) if e.name == "done").data["session_id"]
    )

    # session_create_per_day=1 is already exhausted by the mint above — resuming the SAME known
    # session must still work (it is not a create). The mint's own first message is exempt from
    # RATE_LIMIT_PER_DAY (session_id=None at check time, same pinned semantics test 12 in
    # test_ratelimit.py exercises), so the day cap (2) is fresh for these two resumes.
    for _ in range(2):
        status, content_type, body = _post_chat_stream(
            client, {"session_id": session_id, "message": "Resume the known session."}
        )
        assert status == 200, body
        assert content_type.startswith("text/event-stream"), content_type

    # The per-day/session cap (2) is now exhausted by the two resumes above — a 3rd, on the SAME
    # known session, must 429 on the day cap, not the (already-separately-exhausted) create cap.
    response = client.post(
        "/api/v1/public/chat", json={"session_id": session_id, "message": "One message too many."}
    )
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "rate_limited"
