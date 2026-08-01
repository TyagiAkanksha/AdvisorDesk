"""Failing (RED) tests for `POST /public/chat`: synthesis, SSE streaming, persistence, refusal.

Task brief: docs/plans/phase-4-rag-assistant/task-02-chat-synthesis-sse.md, Step 1.
Spec: advisordesk-prd.md §5.3 (request/response + the four SSE event shapes, session rules incl.
unknown-id -> new session), §7.5 (system-prompt intent), §7.6-§7.7 (stream order, persistence),
§7.4 (outcome recording), §4 "Citation granularity" (the chunk-level-stored vs content-level-wire
asymmetry). CONVENTIONS.md §4 (SSE errors use the same §9 envelope).

`app.rag.synthesis` does not exist yet (imported below for `SYSTEM_PROMPT`): every test here is
expected to fail at collection (`ModuleNotFoundError`) until the implementer (a separate agent)
creates `app/rag/synthesis.py`, `app/routes/sse.py`, `app/services/chat.py`,
`app/models/schemas/chat.py`, and wires the route + factory param — that failure IS the RED
evidence this file exists to produce. Even past collection, every test would still fail: the
route does not exist (404) and `create_app` does not accept `chat_llm=`/`embedder=` yet.

Fakes are defined locally (`FakeEmbedder`, `FakeChatLLM`) per CONVENTIONS.md §10 / the test-author
brief: no cross-test-file imports. `FakeEmbedder` mirrors `test_retrieval.py::RecordingFakeEmbedder`
(a fixed, caller-chosen vector regardless of input text, so cosine similarities against hand-built
`Chunk.embedding` rows are known in advance) rather than `test_lifecycle.py::FakeEmbedder`'s
hash-seeded shape, because these tests need to control retrieval outcomes exactly. Content/chunk
rows are seeded via direct ORM field setup (`test_retrieval.py`'s style), not the real publish
pipeline, for the same reason: an exact, known embedding per chunk.

Judgment call (test-author, flagged for controller review — see `_build_client`'s docstring): the
brief's Interfaces block names only `chat_llm=None`/`app.state.chat_llm` as `create_app`'s new
phase-4 parameter, but the route also needs a request-time `Embedder` for
`app.rag.retrieval.retrieve()` (task-01, already real), and nothing already on `app.state` can
supply one testably. Every test below pins a second new parameter, `embedder=None` /
`app.state.embedder`, mirroring `chat_llm`'s own shape.

SSE parsing: `_parse_sse_events` is deliberately strict about the wire grammar (one `event:` line
and one `data:` line per blank-line-delimited block) — task-05's chat UI parses the same shapes,
so a lenient parser here would hide a malformed producer. Every request goes through
`TestClient.stream(...)` (not a plain `.post()`) per the brief, so the streaming code path is
actually exercised rather than a buffered response.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL` is
set, and are skipped by fixture name otherwise (`tests/conftest.py::pytest_collection_modifyitems`)
— every test here requests `tmp_engine`/`db_session`, so the whole module skips cleanly without a
DB.
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import pytest
from app.rag.synthesis import SYSTEM_PROMPT
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db import make_session_factory
from app.factory import create_app
from app.models import ChatMessage, ChatSession, Chunk, Content
from app.rag.retrieval import RetrievedChunk

# `nvidia/nv-embedqa-e5-v5` (PRD §7.2 v1.5) — matches `Chunk.embedding`'s `Vector(1024)` column
# and `Settings.embedding_dimensions`'s default, same as `test_retrieval.py`.
_DIMS = 1024


def _vector_at_cosine(cos_theta: float, *, dims: int = _DIMS) -> list[float]:
    """A unit vector whose cosine similarity to `QUERY_VECTOR` is exactly `cos_theta`.

    Identical construction to `test_retrieval.py::_vector_at_cosine` (re-derived locally per the
    no-cross-test-file-imports rule): `[cos_theta, sin_theta, 0.0, ..., 0.0]` is unit-norm, so its
    dot product with `QUERY_VECTOR = [1.0, 0.0, ..., 0.0]` — and therefore its cosine similarity —
    is exactly `cos_theta`.
    """
    sin_theta = math.sqrt(1.0 - cos_theta * cos_theta)
    return [cos_theta, sin_theta] + [0.0] * (dims - 2)


QUERY_VECTOR = _vector_at_cosine(1.0)  # == [1.0, 0.0, ..., 0.0]


# ---------------------------------------------------------------------------
# Fakes: `Embedder` and `ChatLLM` seams (defined locally, per the brief).
# ---------------------------------------------------------------------------


@dataclass
class FakeEmbedder:
    """Deterministic `Embedder` fake — always returns `vector` regardless of input text.

    Structurally matches `app.rag.embeddings.Embedder`: `retrieve()` (task-01, real) embeds the
    chat message through this seam with `input_type="query"`; returning a fixed, caller-chosen
    vector lets these tests pin exact cosine similarities against hand-built `Chunk.embedding`
    rows, exactly like `test_retrieval.py::RecordingFakeEmbedder`.
    """

    vector: list[float]
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [self.vector for _ in texts]


@dataclass(frozen=True)
class RecordedChatCall:
    """One recorded `FakeChatLLM.stream_answer` call — what the app actually passed it."""

    system: str
    question: str
    sources: tuple[RetrievedChunk, ...]


@dataclass
class FakeChatLLM:
    """Scripted, recording `ChatLLM` fake (brief Interfaces block: `ChatLLM` Protocol).

    Yields `answer_tokens` when called with at least one source, or `refusal_tokens` when called
    with zero sources — simulating a real model following `SYSTEM_PROMPT`'s refusal instruction
    (PRD §7.5) without any real provider call. `fail_after` (if set) raises `RuntimeError` after
    yielding that many tokens — the mid-stream-failure pin. Every call's `(system, question,
    sources)` is recorded on `calls`, in order.
    """

    answer_tokens: list[str]
    refusal_tokens: list[str] = field(
        default_factory=lambda: ["No published guidance covers this."]
    )
    fail_after: int | None = None
    calls: list[RecordedChatCall] = field(default_factory=list)

    def stream_answer(
        self, system: str, question: str, sources: Sequence[RetrievedChunk]
    ) -> Iterator[str]:
        self.calls.append(
            RecordedChatCall(system=system, question=question, sources=tuple(sources))
        )
        script = self.answer_tokens if sources else self.refusal_tokens
        for index, token in enumerate(script):
            if self.fail_after is not None and index == self.fail_after:
                raise RuntimeError("simulated LLM failure mid-stream (FakeChatLLM test fake)")
            yield token


# ---------------------------------------------------------------------------
# DB seeding helpers (direct ORM field setup — `test_retrieval.py`'s style).
# ---------------------------------------------------------------------------


def _add_content(session: Session, *, slug: str) -> Content:
    """Insert and flush a published, non-deleted `Content` row via direct field setup."""
    content = Content(
        title=f"Title for {slug}",
        slug=slug,
        body_md="body text, irrelevant to retrieval — chunks carry the retrievable text",
        status="published",
        is_deleted=False,
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    return content


def _add_chunk(
    session: Session, content_id: uuid.UUID, *, chunk_index: int, text: str, cos_theta: float
) -> Chunk:
    """Insert and flush a `Chunk` row whose embedding has cosine similarity `cos_theta` to
    `QUERY_VECTOR`.
    """
    chunk = Chunk(
        content_id=content_id,
        chunk_index=chunk_index,
        text=text,
        embedding=_vector_at_cosine(cos_theta),
    )
    session.add(chunk)
    session.flush()
    return chunk


def _content_level_citation(content: Content) -> dict[str, str]:
    """The deduped, content-level wire shape PRD §5.3/§4 pins for the `citations` SSE event."""
    return {"content_id": str(content.id), "title": content.title, "slug": content.slug}


def _chunk_level_citation(content: Content, chunk: Chunk) -> dict[str, str]:
    """The chunk-level DB shape PRD §4 pins for the persisted assistant row's `citations` column."""
    return {
        "content_id": str(content.id),
        "title": content.title,
        "slug": content.slug,
        "chunk_id": str(chunk.id),
    }


# ---------------------------------------------------------------------------
# SSE parsing + HTTP helpers.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SseEvent:
    """One parsed `event: <name>` / `data: <json>` block."""

    name: str
    data: dict[str, object]


def _parse_sse_events(body: str) -> list[SseEvent]:
    """Parse an SSE body into an ordered list of `SseEvent`s.

    Strict about the wire grammar: splits on blank-line-delimited blocks, and within each block
    requires EXACTLY one `event:` line and EXACTLY one `data:` line — a malformed block (missing
    or duplicated field) is a hard assertion failure here, not silently ignored, since task-05's
    chat UI parses this same shape.
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


def _assert_ok_event_shape(events: list[SseEvent]) -> None:
    """Assert the exact §5.3 success order: one or more `token`, then one `citations`, then one
    `done` — no `error` event anywhere.
    """
    names = [event.name for event in events]
    assert names, "expected at least one SSE event"
    assert "error" not in names, f"unexpected error event: {names}"
    assert names.count("citations") == 1, names
    assert names.count("done") == 1, names
    citations_at = names.index("citations")
    done_at = names.index("done")
    assert citations_at >= 1, f"expected at least one token event before citations: {names}"
    assert names[:citations_at] == ["token"] * citations_at, names
    assert done_at == citations_at + 1, names
    assert done_at == len(names) - 1, names


def _accumulated_token_text(events: list[SseEvent]) -> str:
    """Concatenate every `token` event's `text` field, in order."""
    return "".join(str(event.data["text"]) for event in events if event.name == "token")


def _post_chat(client: TestClient, body: dict[str, object]) -> tuple[int, str, str]:
    """POST `/api/v1/public/chat` via the streaming interface; return (status, content_type, body).

    Uses `client.stream(...)` rather than a plain `.post()` (task brief: "so tokens are observed
    as a stream, not a buffered body") — reads the full body via `iter_text()` so callers get
    complete content for `_parse_sse_events`, while still exercising `StreamingResponse`'s actual
    streaming code path.
    """
    with client.stream("POST", "/api/v1/public/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


def _build_client(
    tmp_engine: Engine, *, chat_llm: FakeChatLLM, embedder: FakeEmbedder
) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with the chat LLM + embedder seams faked.

    Judgment call (test-author, flagged for controller review — module docstring): the brief's
    Interfaces block names only `chat_llm=None`/`app.state.chat_llm` as `create_app`'s new
    phase-4 parameter, but `app.rag.retrieval.retrieve()` (task-01, already real) also needs an
    `Embedder` at request time, and nothing else on `app.state` provides one testably —
    `chunk_pipeline` exposes no embedder accessor (its `NoopChunkPipeline` default has none at
    all), and CONVENTIONS.md §10 requires external seams to be injectable, never monkeypatched at
    a distance. The natural minimal extension, mirroring `chat_llm`'s own shape, is a second new
    parameter: `embedder=None` / `app.state.embedder`. If the controller intends different wiring,
    this is the one place (every call site below routes through it) that needs revisiting, not a
    change to any test's assertions.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        chat_llm=chat_llm,
        embedder=embedder,
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Happy path: event order + content-type (brief Step-1 bullet 1).
# ---------------------------------------------------------------------------


def test_happy_path_streams_tokens_then_citations_then_done(
    tmp_engine: Engine, db_session: Session
) -> None:
    """§5.3 happy path: `token`+ -> `citations` -> `done`, `text/event-stream`, accumulated text."""
    content = _add_content(db_session, slug="roth-ira-basics")
    _add_chunk(db_session, content.id, chunk_index=0, text="Roth IRA basics chunk", cos_theta=0.9)
    db_session.commit()

    answer_tokens = ["Roth ", "IRAs ", "allow ", "tax-free ", "growth."]
    chat_llm = FakeChatLLM(answer_tokens=answer_tokens)
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    status, content_type, body = _post_chat(client, {"message": "What is a Roth IRA?"})

    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type
    events = _parse_sse_events(body)
    _assert_ok_event_shape(events)
    assert _accumulated_token_text(events) == "".join(answer_tokens)

    citations_event = next(e for e in events if e.name == "citations")
    assert citations_event.data == {"citations": [_content_level_citation(content)]}

    done_event = next(e for e in events if e.name == "done")
    assert isinstance(done_event.data["session_id"], str) and done_event.data["session_id"]
    assert isinstance(done_event.data["message_id"], str) and done_event.data["message_id"]

    assert len(chat_llm.calls) == 1
    assert chat_llm.calls[0].system == SYSTEM_PROMPT
    assert chat_llm.calls[0].question == "What is a Roth IRA?"


# ---------------------------------------------------------------------------
# 2. Session rules (brief Step-1 bullet 1, second half; PRD §5.3).
# ---------------------------------------------------------------------------


def test_no_session_id_creates_new_session(tmp_engine: Engine, db_session: Session) -> None:
    """§5.3: an absent `session_id` makes the server create a session and return its new id."""
    content = _add_content(db_session, slug="new-session-content")
    _add_chunk(db_session, content.id, chunk_index=0, text="new session chunk", cos_theta=0.8)
    db_session.commit()

    chat_llm = FakeChatLLM(answer_tokens=["An ", "answer."])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    status, _content_type, body = _post_chat(client, {"message": "A question."})

    assert status == 200, body
    events = _parse_sse_events(body)
    _assert_ok_event_shape(events)
    done_event = next(e for e in events if e.name == "done")
    new_session_id = uuid.UUID(str(done_event.data["session_id"]))

    with make_session_factory(tmp_engine)() as fresh:
        assert fresh.get(ChatSession, new_session_id) is not None


def test_known_session_id_is_echoed(tmp_engine: Engine, db_session: Session) -> None:
    """§5.3: a known `session_id` sent by the client is echoed back unchanged in `done`."""
    content = _add_content(db_session, slug="known-session-content")
    _add_chunk(db_session, content.id, chunk_index=0, text="known session chunk", cos_theta=0.8)
    db_session.commit()

    chat_llm = FakeChatLLM(answer_tokens=["An ", "answer."])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    _status, _content_type, first_body = _post_chat(client, {"message": "First question."})
    first_events = _parse_sse_events(first_body)
    _assert_ok_event_shape(first_events)
    first_session_id = next(e for e in first_events if e.name == "done").data["session_id"]

    status, _content_type, second_body = _post_chat(
        client, {"session_id": first_session_id, "message": "Second question."}
    )

    assert status == 200, second_body
    second_events = _parse_sse_events(second_body)
    _assert_ok_event_shape(second_events)
    second_session_id = next(e for e in second_events if e.name == "done").data["session_id"]
    assert second_session_id == first_session_id


def test_unknown_session_id_creates_new_session_without_error(
    tmp_engine: Engine, db_session: Session
) -> None:
    """§5.3: an unrecognized `session_id` creates a fresh session — no error, unlike a bare 404."""
    content = _add_content(db_session, slug="unknown-session-content")
    _add_chunk(db_session, content.id, chunk_index=0, text="unknown session chunk", cos_theta=0.8)
    db_session.commit()

    chat_llm = FakeChatLLM(answer_tokens=["An ", "answer."])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)
    unknown_id = str(uuid.uuid4())

    status, _content_type, body = _post_chat(
        client, {"session_id": unknown_id, "message": "A question."}
    )

    assert status == 200, body
    events = _parse_sse_events(body)
    _assert_ok_event_shape(events)
    done_event = next(e for e in events if e.name == "done")
    returned_id = str(done_event.data["session_id"])
    assert returned_id != unknown_id

    with make_session_factory(tmp_engine)() as fresh:
        assert fresh.get(ChatSession, uuid.UUID(returned_id)) is not None
        assert fresh.get(ChatSession, uuid.UUID(unknown_id)) is None


# ---------------------------------------------------------------------------
# 3. §4 citation-granularity asymmetry pin (brief Step-1 bullet 2), from ONE exchange.
# ---------------------------------------------------------------------------


def test_citation_asymmetry_wire_deduped_content_level_row_chunk_level_from_one_exchange(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §4 "Citation granularity (deliberate asymmetry)": from ONE exchange, the wire
    `citations` event is deduped to content level and ordered by first use, while the persisted
    assistant row keeps chunk-level citations (one entry per retrieved chunk, `chunk_id`
    included) — even when two chunks share a content item.
    """
    content_a = _add_content(db_session, slug="asymmetry-content-a")
    content_b = _add_content(db_session, slug="asymmetry-content-b")
    # Similarity-descending retrieval order: a1 (.9) -> b1 (.7) -> a2 (.5) — content A's first use
    # precedes B's even though A also owns the LAST (lowest-similarity) chunk, so a naive
    # "dedupe by sorting" implementation (instead of first-occurrence order) would fail this too.
    chunk_a1 = _add_chunk(db_session, content_a.id, chunk_index=0, text="a chunk 1", cos_theta=0.9)
    chunk_b1 = _add_chunk(db_session, content_b.id, chunk_index=0, text="b chunk 1", cos_theta=0.7)
    chunk_a2 = _add_chunk(db_session, content_a.id, chunk_index=1, text="a chunk 2", cos_theta=0.5)
    db_session.commit()

    chat_llm = FakeChatLLM(answer_tokens=["Grounded ", "answer."])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    status, _content_type, body = _post_chat(client, {"message": "Tell me about A and B."})

    assert status == 200, body
    events = _parse_sse_events(body)
    _assert_ok_event_shape(events)

    # Content level, deduped, ordered by first use: A before B (2 entries, not 3).
    citations_event = next(e for e in events if e.name == "citations")
    assert citations_event.data == {
        "citations": [_content_level_citation(content_a), _content_level_citation(content_b)]
    }

    done_event = next(e for e in events if e.name == "done")
    message_id = uuid.UUID(str(done_event.data["message_id"]))

    # Chunk level, one row per retrieved chunk (3 entries), `chunk_id` included.
    with make_session_factory(tmp_engine)() as fresh:
        assistant_row = fresh.get(ChatMessage, message_id)
        assert assistant_row is not None
        assert assistant_row.citations == [
            _chunk_level_citation(content_a, chunk_a1),
            _chunk_level_citation(content_b, chunk_b1),
            _chunk_level_citation(content_a, chunk_a2),
        ]


# ---------------------------------------------------------------------------
# 4. Outcome recording: covered + uncovered/refusal (brief Step-1 bullet 3; PRD §7.4/§7.5).
# ---------------------------------------------------------------------------


def test_outcome_recording_covered_question_sets_retrieval_found_true_and_top_similarity(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §7.4: a covered question records `retrieval_found=True` and `top_similarity` ≈ the
    scripted best similarity on the persisted assistant row, and the LLM receives that chunk.
    """
    content = _add_content(db_session, slug="outcome-covered-content")
    _add_chunk(db_session, content.id, chunk_index=0, text="covered chunk", cos_theta=0.9)
    db_session.commit()

    chat_llm = FakeChatLLM(answer_tokens=["Covered ", "answer."])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    status, _content_type, body = _post_chat(client, {"message": "A covered question."})

    assert status == 200, body
    events = _parse_sse_events(body)
    _assert_ok_event_shape(events)
    done_event = next(e for e in events if e.name == "done")
    message_id = uuid.UUID(str(done_event.data["message_id"]))

    assert len(chat_llm.calls) == 1
    assert len(chat_llm.calls[0].sources) == 1

    with make_session_factory(tmp_engine)() as fresh:
        assistant_row = fresh.get(ChatMessage, message_id)
        assert assistant_row is not None
        assert assistant_row.retrieval_found is True
        assert assistant_row.top_similarity == pytest.approx(0.9, abs=1e-3)


def test_outcome_recording_uncovered_question_refuses_with_zero_sources_and_retrieval_found_false(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §7.4/§7.5 refusal pin: an uncovered question (empty index — no published chunks at
    all) never gives the LLM any sources, streams the refusal text, carries `citations: []` on
    the wire, and records `retrieval_found=False` (with `top_similarity=None`, matching task-01's
    empty-index semantics) on the persisted assistant row.
    """
    # Deliberately no content/chunks at all in this throwaway schema — the "empty" half of the
    # brief's "uncovered (all below threshold / empty)".
    refusal_tokens = ["No ", "published ", "guidance ", "covers ", "this."]
    chat_llm = FakeChatLLM(
        answer_tokens=["Should ", "never ", "stream."], refusal_tokens=refusal_tokens
    )
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    status, _content_type, body = _post_chat(client, {"message": "An uncovered question."})

    assert status == 200, body
    events = _parse_sse_events(body)
    _assert_ok_event_shape(events)
    assert _accumulated_token_text(events) == "".join(refusal_tokens)

    citations_event = next(e for e in events if e.name == "citations")
    assert citations_event.data == {"citations": []}

    done_event = next(e for e in events if e.name == "done")
    message_id = uuid.UUID(str(done_event.data["message_id"]))

    assert len(chat_llm.calls) == 1
    assert chat_llm.calls[0].sources == ()  # refusal pin: the LLM was NOT given sources
    assert chat_llm.calls[0].system == SYSTEM_PROMPT

    with make_session_factory(tmp_engine)() as fresh:
        assistant_row = fresh.get(ChatMessage, message_id)
        assert assistant_row is not None
        assert assistant_row.retrieval_found is False
        assert assistant_row.top_similarity is None
        assert not assistant_row.citations


# ---------------------------------------------------------------------------
# 5. Persistence order (brief Step-1 bullet 4; PRD §7.7).
# ---------------------------------------------------------------------------


def test_persistence_user_then_assistant_rows_in_order_with_correct_roles(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §7.7: one exchange persists a user row then an assistant row, in that order, with the
    correct `role`/`content`.
    """
    content = _add_content(db_session, slug="persistence-content")
    _add_chunk(db_session, content.id, chunk_index=0, text="persistence chunk", cos_theta=0.9)
    db_session.commit()

    answer_tokens = ["Persisted ", "answer."]
    chat_llm = FakeChatLLM(answer_tokens=answer_tokens)
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)
    question = "A persisted question."

    status, _content_type, body = _post_chat(client, {"message": question})

    assert status == 200, body
    events = _parse_sse_events(body)
    _assert_ok_event_shape(events)
    done_event = next(e for e in events if e.name == "done")
    session_id = uuid.UUID(str(done_event.data["session_id"]))

    with make_session_factory(tmp_engine)() as fresh:
        rows = list(
            fresh.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            ).scalars()
        )

    assert len(rows) == 2
    assert rows[0].role == "user"
    assert rows[0].content == question
    assert rows[1].role == "assistant"
    assert rows[1].content == "".join(answer_tokens)


# ---------------------------------------------------------------------------
# 6. LLM failure mid-stream (brief Step-1 bullet 5; CONVENTIONS.md §4 / PRD §9).
# ---------------------------------------------------------------------------


def test_llm_failure_mid_stream_emits_error_event_and_still_persists_user_message(
    tmp_engine: Engine, db_session: Session
) -> None:
    """An LLM failure partway through streaming yields an `error` event carrying the §9
    envelope, never a `citations`/`done` event — but the user's message is still durably
    persisted.
    """
    content = _add_content(db_session, slug="failure-content")
    _add_chunk(db_session, content.id, chunk_index=0, text="failure chunk", cos_theta=0.9)
    db_session.commit()

    chat_llm = FakeChatLLM(answer_tokens=["Partial ", "answer ", "text."], fail_after=1)
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)
    question = "A question that fails mid-stream."

    status, content_type, body = _post_chat(client, {"message": question})

    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type
    events = _parse_sse_events(body)
    names = [event.name for event in events]
    assert names.count("token") == 1, names
    assert "citations" not in names, names
    assert "done" not in names, names
    assert names.count("error") == 1, names
    assert names[-1] == "error", names
    assert _accumulated_token_text(events) == "Partial "

    error_event = next(e for e in events if e.name == "error")
    error_payload = error_event.data["error"]
    assert isinstance(error_payload, dict)
    assert isinstance(error_payload["code"], str) and error_payload["code"]
    assert isinstance(error_payload["message"], str) and error_payload["message"]

    with make_session_factory(tmp_engine)() as fresh:
        rows = list(fresh.execute(select(ChatMessage)).scalars())

    assert len(rows) == 1, rows
    assert rows[0].role == "user"
    assert rows[0].content == question
