"""Failing (RED) tests for the §9 rate-limiting caps: `RateLimiter` (unit) and `POST
/public/chat` wiring (endpoint).

Task brief: docs/plans/phase-4-rag-assistant/task-03-rate-limiting.md (freshly amended: the
injectable clock returns POSIX EPOCH SECONDS, default `time.time`; day buckets are
`floor(clock() / 86400)` — the UTC-midnight reset; the per-minute cap is a SLIDING one-minute
window). Spec: advisordesk-prd.md §9 "Rate limiting" (three caps + PRD defaults:
`RATE_LIMIT_PER_MIN=10` per IP, `RATE_LIMIT_PER_DAY=50` per session, `SESSION_CREATE_PER_DAY=20`
per IP — the cap that stops resetting the per-session cap by minting fresh sessions), §5.3
(session creation is "subject to the per-IP creation cap"). CONVENTIONS.md §4 (429s carry the
§9 envelope); §10 (injectable clock, TestClient over the real HTTP surface, no cross-test-file
imports).

`app.routes.ratelimit` does not exist yet (imported below for `RateLimiter`): every test here is
expected to fail at collection (`ModuleNotFoundError`) until the implementer (a separate agent)
creates `app/routes/ratelimit.py` and wires it — `create_app`'s (not-yet-existing) `rate_limiter=`
parameter and `app.state.rate_limiter` — into `app/routes/public_routes.py` ahead of
`get_or_create_session` and the SSE response. That failure IS the RED evidence this file exists
to produce.

I001 note (established precedent — `test_retrieval.py`/`test_public_chat.py`, both pinned):
`from app.routes.ratelimit import RateLimiter` sits in the THIRD-PARTY import block below, not
the first-party `app.*` block — ruff's isort resolves first-party membership by checking the
module actually exists on disk, and `app/routes/ratelimit.py` doesn't exist yet. Once the
implementer creates it, `uv run ruff check` will demand the same reorder this repo has already
done twice (`a964787`, `10e1390`) — expected, not a defect in this file today.

Fakes (`FakeEmbedder`, `FakeChatLLM`, `FakeClock`) are defined locally per CONVENTIONS.md §10 /
the test-author brief: no cross-test-file imports. `FakeEmbedder`/`FakeChatLLM` are trimmed
copies of `tests/test_public_chat.py`'s own (same shape, same rationale — a fixed-vector
`Embedder` double and a scripted, recording `ChatLLM` double); the endpoint tests below never seed
`Content`/`Chunk` rows (retrieval always finds nothing, so every admitted request takes the
refusal path) since what these tests assert is *whether the request reaches retrieval/synthesis
at all*, not what the answer contains.

Client IP: this repo's pinned `starlette` (1.3.1, see `uv.lock`) TestClient constructor accepts a
`client: tuple[str, int]` argument that becomes `request.client.host`/`.port` in the ASGI scope
(verified empirically against the project's own `uv run` venv — the anaconda system Python's much
older starlette does NOT have this parameter, which is why this file's endpoint tests are only
meaningful under `uv run`). This is the pinned mechanism for exercising per-IP distinctions here —
deliberately NOT an `X-Forwarded-For` parsing scheme (a deploy concern PRD §9 doesn't ask for);
the implementation must key on `request.client.host` directly.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

import pytest
from app.routes.ratelimit import RateLimiter
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.services.errors import RateLimitedError

# One day, in seconds — `floor(clock() / 86400)` is the day-bucket key the brief pins (UTC
# midnight reset). A day-46 fixed anchor keeps every timestamp comfortably positive and far from
# both the Unix epoch and any test's own day-boundary arithmetic unless a test deliberately
# crosses one.
_DAY_SECONDS = 86400
_MID_DAY_ANCHOR = 46 * _DAY_SECONDS + 43_200  # noon, day 46


@dataclass
class FakeClock:
    """A settable epoch-seconds clock double for `RateLimiter`'s injectable `clock` seam.

    Callable (matches `Callable[[], float]`) so it can be passed directly as `RateLimiter`'s
    `clock=` argument; `advance`/`set` let a test move time forward without any real `sleep`
    (CONVENTIONS.md §10: "clock into the rate limiter" is one of the explicitly named injectable
    seams; "no sleeps in tests" per the brief's Acceptance section).
    """

    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def set(self, value: float) -> None:
        self.now = value


# ---------------------------------------------------------------------------
# 1. Unit tests: `RateLimiter` against a fake epoch clock — no HTTP, no DB.
# ---------------------------------------------------------------------------


def test_check_message_per_min_admits_ten_then_raises_on_eleventh() -> None:
    """PRD §9 default `RATE_LIMIT_PER_MIN=10`: 10 messages in a minute from one IP pass; the
    11th raises `RateLimitedError`.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(), clock=clock)

    for _ in range(10):
        limiter.check_message("1.2.3.4", "session-a")

    with pytest.raises(RateLimitedError):
        limiter.check_message("1.2.3.4", "session-a")


def test_check_message_per_min_sliding_window_admits_again_after_61_seconds() -> None:
    """Sliding one-minute window: 10 messages at t=0 exhaust the cap; advancing the fake clock
    61s (past the whole 60s window) admits an 11th.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(), clock=clock)

    for _ in range(10):
        limiter.check_message("1.2.3.4", "session-a")

    clock.advance(61.0)

    limiter.check_message("1.2.3.4", "session-a")  # must not raise


def test_check_message_per_min_sliding_window_still_blocks_after_only_30_seconds() -> None:
    """Sliding-window pin (brief's explicit counter-case): the same 10-message burst at t=0,
    followed by only 30s of elapsed time — all 10 are still "in the last 30s" relative to the
    11th attempt — must still raise, unlike the 61s case above.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(), clock=clock)

    for _ in range(10):
        limiter.check_message("1.2.3.4", "session-a")

    clock.advance(30.0)

    with pytest.raises(RateLimitedError):
        limiter.check_message("1.2.3.4", "session-a")


def test_check_message_per_day_session_cap_admits_fifty_then_raises_regardless_of_pacing() -> None:
    """PRD §9 default `RATE_LIMIT_PER_DAY=50`: 50 messages in one session pass, the 51st raises
    — "regardless of pacing": each call is spaced 100s apart (never bursty, so a sliding-window
    per-minute-style implementation would never trip) yet the day cap still trips on the 51st,
    proving it isn't confused with the per-minute mechanism. `rate_limit_per_min` is set
    generously high so the per-minute cap can never be the thing that raises here.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(rate_limit_per_min=10_000), clock=clock)

    for _ in range(50):
        limiter.check_message("9.9.9.9", "session-day-cap")
        clock.advance(100.0)

    with pytest.raises(RateLimitedError):
        limiter.check_message("9.9.9.9", "session-day-cap")


def test_check_message_per_day_session_cap_resets_at_utc_midnight_bucket_boundary() -> None:
    """Day buckets are `floor(clock() / 86400)` (the brief's amended, controller-ruled
    semantics — UTC midnight, since the clock is POSIX epoch seconds): a custom
    `rate_limit_per_day=3` cap, exhausted just before a day boundary, still raises on the 4th
    attempt AT the same instant (same bucket) — but admits again once the fake clock crosses
    into the next `floor(t / 86400)` bucket, even though only a few real seconds passed.
    """
    clock = FakeClock(now=_DAY_SECONDS - 5.0)  # 5s before the day-0/day-1 boundary
    limiter = RateLimiter(Settings(rate_limit_per_min=10_000, rate_limit_per_day=3), clock=clock)

    for _ in range(3):
        limiter.check_message("5.5.5.5", "session-midnight")

    with pytest.raises(RateLimitedError):
        limiter.check_message("5.5.5.5", "session-midnight")

    clock.advance(10.0)  # now DAY_SECONDS + 5 -> floor(.../86400) == 1, a new bucket

    limiter.check_message("5.5.5.5", "session-midnight")  # must not raise: fresh day bucket


def test_check_session_create_cap_admits_twenty_then_raises_other_ip_unaffected() -> None:
    """PRD §9 default `SESSION_CREATE_PER_DAY=20`: 20 session creations from one IP pass (each
    followed by `note_session_created`, the two-step check-then-record API), the 21st
    `check_session_create` raises — but a DIFFERENT IP's `check_session_create` is unaffected
    (the cap is per-IP, not global).
    """
    clock = FakeClock(now=_MID_DAY_ANCHOR)
    limiter = RateLimiter(Settings(), clock=clock)

    for _ in range(20):
        limiter.check_session_create("6.6.6.6")  # must not raise
        limiter.note_session_created("6.6.6.6")

    with pytest.raises(RateLimitedError):
        limiter.check_session_create("6.6.6.6")

    limiter.check_session_create("7.7.7.7")  # different IP, must not raise


def test_check_message_per_min_cap_reads_from_settings_custom_cap_trips_at_three() -> None:
    """PRD §9 "env-tunable": `Settings(rate_limit_per_min=2)` trips on the 3rd message, not the
    PRD default's 11th — the cap value is read from `Settings`, not hardcoded.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(rate_limit_per_min=2), clock=clock)

    limiter.check_message("8.8.8.8", "session-custom-cap")
    limiter.check_message("8.8.8.8", "session-custom-cap")

    with pytest.raises(RateLimitedError):
        limiter.check_message("8.8.8.8", "session-custom-cap")


def test_check_message_per_min_cap_is_per_ip_second_ip_unaffected() -> None:
    """The per-minute cap is keyed by IP: exhausting it for one IP leaves a second IP's own
    budget completely untouched.
    """
    clock = FakeClock(now=0.0)
    limiter = RateLimiter(Settings(rate_limit_per_min=2), clock=clock)

    limiter.check_message("10.0.0.1", "session-ip-a")
    limiter.check_message("10.0.0.1", "session-ip-a")
    with pytest.raises(RateLimitedError):
        limiter.check_message("10.0.0.1", "session-ip-a")

    # A different IP's own 2-message budget is untouched by IP A's breach above.
    limiter.check_message("10.0.0.2", "session-ip-b")
    limiter.check_message("10.0.0.2", "session-ip-b")


# ---------------------------------------------------------------------------
# 2. Endpoint tests: `POST /public/chat` wired to a real `RateLimiter` (TestClient + DB).
# ---------------------------------------------------------------------------


@dataclass
class FakeEmbedder:
    """Deterministic `Embedder` fake — always returns `vector` regardless of input text.

    Trimmed copy of `tests/test_public_chat.py::FakeEmbedder`'s shape (CONVENTIONS.md §10: no
    cross-test-file imports). No `Chunk` rows are ever seeded in this file's DB fixtures, so the
    exact vector value never matters — only whether `embed_texts` was called at all, and how many
    times, which `calls` records.
    """

    vector: list[float]
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [self.vector for _ in texts]


@dataclass
class FakeChatLLM:
    """Scripted, recording `ChatLLM` fake — trimmed copy of
    `tests/test_public_chat.py::FakeChatLLM`'s shape. No chunks are ever seeded in this file, so
    every admitted request takes the refusal branch (`sources` is always empty) — `calls`
    records how many times (and with what arguments) the route actually reached synthesis.
    """

    refusal_tokens: list[str] = field(
        default_factory=lambda: ["No published guidance covers this."]
    )
    calls: list[tuple[str, str, tuple[object, ...]]] = field(default_factory=list)

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        self.calls.append((system, question, tuple(sources)))
        yield from self.refusal_tokens


@dataclass(frozen=True)
class SseEvent:
    """One parsed `event: <name>` / `data: <json>` block — trimmed copy of
    `tests/test_public_chat.py::SseEvent`'s shape/parsing logic.
    """

    name: str
    data: dict[str, object]


def _parse_sse_events(body: str) -> list[SseEvent]:
    """Parse an SSE body into an ordered list of `SseEvent`s — trimmed copy of
    `tests/test_public_chat.py::_parse_sse_events`'s logic (no cross-file import).
    """
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
    """POST `/api/v1/public/chat` via the streaming interface; return (status, content_type,
    body) — trimmed copy of `tests/test_public_chat.py::_post_chat`.
    """
    with client.stream("POST", "/api/v1/public/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


def _build_app(
    tmp_engine: Engine, *, settings: Settings, chat_llm: FakeChatLLM, embedder: FakeEmbedder
) -> FastAPI:
    """Build the FastAPI app with a real `RateLimiter` wired through `create_app`'s (not yet
    existing) `rate_limiter=` parameter (task brief Interfaces block: "Instance on
    `app.state.rate_limiter`" — mirrors `chat_llm=`/`embedder=`'s established per-seam factory
    parameter shape, test-author judgment call per the brief's own "factory param `rate_limiter
    =None` likely" note).

    The real (default) `time.time` clock is used here, not a fake — these endpoint tests only
    ever assert small, fast cap counts (single-digit request counts within one test), never
    sliding-window timing, so real wall-clock time introduces no flakiness risk worth the extra
    seam.
    """
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=settings,
        chat_llm=chat_llm,
        embedder=embedder,
        rate_limiter=RateLimiter(settings),
    )


def test_endpoint_under_cap_requests_stream_normally(tmp_engine: Engine) -> None:
    """Acceptance: "under-cap requests still stream" — a single request, nowhere near any of the
    three (generously-sized) caps, gets a normal 200 SSE response.
    """
    settings = Settings(rate_limit_per_min=5, rate_limit_per_day=50, session_create_per_day=20)
    chat_llm = FakeChatLLM()
    embedder = FakeEmbedder(vector=[0.0] * 8)
    client = TestClient(
        _build_app(tmp_engine, settings=settings, chat_llm=chat_llm, embedder=embedder)
    )

    status, content_type, body = _post_chat_stream(client, {"message": "Under the cap."})

    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type
    names = [event.name for event in _parse_sse_events(body)]
    assert "error" not in names, names
    assert names.count("done") == 1, names
    assert len(chat_llm.calls) == 1
    assert len(embedder.calls) == 1


def test_endpoint_per_min_breach_returns_429_envelope_with_zero_new_llm_embedder_calls(
    tmp_engine: Engine,
) -> None:
    """Task brief Step 5: a per-minute breach returns HTTP 429 with the §9
    `{"error":{"code":"rate_limited", ...}}` envelope as plain `application/json` (never an SSE
    stream), and the rejected request itself causes ZERO additional embedder/chat-LLM calls —
    proving the rejection happens before retrieval AND before the stream opens. A second,
    DIFFERENT IP (via this repo's pinned starlette `TestClient(..., client=(host, port))`
    mechanism) is completely unaffected by the first IP's breach, exercising the per-IP keying
    end to end through the real HTTP wiring, not just the unit-level `RateLimiter` object.
    """
    settings = Settings(rate_limit_per_min=2, rate_limit_per_day=50, session_create_per_day=20)
    chat_llm = FakeChatLLM()
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = _build_app(tmp_engine, settings=settings, chat_llm=chat_llm, embedder=embedder)
    client_a = TestClient(app, client=("203.0.113.1", 50000))

    for _ in range(2):
        status, content_type, body = _post_chat_stream(client_a, {"message": "Under the cap."})
        assert status == 200, body
        assert content_type.startswith("text/event-stream"), content_type

    calls_before = (len(chat_llm.calls), len(embedder.calls))

    response = client_a.post("/api/v1/public/chat", json={"message": "One too many."})

    assert response.status_code == 429, response.text
    assert response.headers["content-type"].startswith("application/json"), response.headers
    envelope = response.json()
    assert envelope["error"]["code"] == "rate_limited"
    assert isinstance(envelope["error"]["message"], str) and envelope["error"]["message"]
    assert (len(chat_llm.calls), len(embedder.calls)) == calls_before

    # A different IP, same app/limiter instance, is unaffected by IP A's breach.
    client_b = TestClient(app, client=("203.0.113.2", 50000))
    status, content_type, body = _post_chat_stream(client_b, {"message": "Different IP."})
    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type


def test_endpoint_session_create_cap_minting_past_cap_returns_429(tmp_engine: Engine) -> None:
    """PRD §9 anti-reset pin (task brief Step 5): `SESSION_CREATE_PER_DAY` caps how many NEW
    sessions one IP may mint per day. Every request below omits `session_id`, so each one mints a
    fresh session; with a tight `session_create_per_day=2`, the 3rd minting attempt gets a 429
    `rate_limited` envelope instead of silently minting a 3rd session (which would let a client
    reset an exhausted per-session §9 cap indefinitely by never resending a `session_id`) — and,
    same as the per-minute breach above, causes zero additional LLM/embedder calls.
    """
    settings = Settings(rate_limit_per_min=100, rate_limit_per_day=1000, session_create_per_day=2)
    chat_llm = FakeChatLLM()
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = _build_app(tmp_engine, settings=settings, chat_llm=chat_llm, embedder=embedder)
    client = TestClient(app, client=("198.51.100.1", 50000))

    for _ in range(2):
        status, content_type, body = _post_chat_stream(client, {"message": "Mint a session."})
        assert status == 200, body
        assert content_type.startswith("text/event-stream"), content_type

    calls_before = (len(chat_llm.calls), len(embedder.calls))

    response = client.post("/api/v1/public/chat", json={"message": "One session too many."})

    assert response.status_code == 429, response.text
    assert response.headers["content-type"].startswith("application/json"), response.headers
    envelope = response.json()
    assert envelope["error"]["code"] == "rate_limited"
    assert isinstance(envelope["error"]["message"], str) and envelope["error"]["message"]
    assert (len(chat_llm.calls), len(embedder.calls)) == calls_before


def test_endpoint_per_day_session_cap_enforced_across_requests_same_session_id(
    tmp_engine: Engine,
) -> None:
    """PRD §9 `RATE_LIMIT_PER_DAY` (per session): with a tight `rate_limit_per_day=2`, two
    requests carrying the SAME (real, now-known) `session_id` are both admitted, a 3rd 429s with
    the §9 envelope — and a brand-new session (a request that omits `session_id` entirely,
    minting a fresh one) is unaffected, proving the cap is scoped per session, not global.

    The very first request of a brand-new session necessarily carries no `session_id` at all —
    the wiring-order pin (limits are checked BEFORE `get_or_create_session` ever mints one) means
    there is no id yet to key a per-session cap on for that one request, so it is not itself
    counted against `rate_limit_per_day`; this test only asserts the cap once the client starts
    resending a real `session_id`, which is the scenario the cap exists to bound.
    """
    settings = Settings(rate_limit_per_min=100, rate_limit_per_day=2, session_create_per_day=20)
    chat_llm = FakeChatLLM()
    embedder = FakeEmbedder(vector=[0.0] * 8)
    app = _build_app(tmp_engine, settings=settings, chat_llm=chat_llm, embedder=embedder)
    client = TestClient(app, client=("198.51.100.2", 50000))

    status, _content_type, mint_body = _post_chat_stream(client, {"message": "Mint a session."})
    assert status == 200, mint_body
    session_id = uuid.UUID(
        str(next(e for e in _parse_sse_events(mint_body) if e.name == "done").data["session_id"])
    )

    for _ in range(2):
        status, content_type, body = _post_chat_stream(
            client, {"session_id": str(session_id), "message": "Within the day cap."}
        )
        assert status == 200, body
        assert content_type.startswith("text/event-stream"), content_type

    calls_before = (len(chat_llm.calls), len(embedder.calls))

    response = client.post(
        "/api/v1/public/chat",
        json={"session_id": str(session_id), "message": "One message too many today."},
    )

    assert response.status_code == 429, response.text
    assert response.headers["content-type"].startswith("application/json"), response.headers
    envelope = response.json()
    assert envelope["error"]["code"] == "rate_limited"
    assert (len(chat_llm.calls), len(embedder.calls)) == calls_before

    # A brand-new session (no session_id sent) is unaffected by the exhausted one above.
    status, content_type, fresh_body = _post_chat_stream(
        client, {"message": "A fresh session's first message."}
    )
    assert status == 200, fresh_body
    assert content_type.startswith("text/event-stream"), content_type
