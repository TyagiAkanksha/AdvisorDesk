"""Fixer-owned tests for `POST /public/chat` (phase-4 task-02 review rounds 1 and 2: findings
M-1, M-5, R-1, N-2).

Four gaps `tests/test_public_chat.py` (pinned) leaves open, all confirmed load-bearing by the
reviewer's mutation battery / probes rather than merely theoretical:

- **M-1** (round 1): the pinned suite's only refusal test uses a genuinely EMPTY index
  (test-author judgment call 4), so PRD §7.4's actual trigger — "nothing cleared the threshold"
  with a NON-empty index (a real chunk that scored below `SIMILARITY_THRESHOLD`) — is never
  exercised. Two mutants survived the pinned suite because of this:
  `M2_found_from_top_similarity` (`retrieval_found = top_similarity is not None`, which happens
  to also read `False` when the index is empty since `top_similarity is None` then, but reads
  `True` — wrongly — the moment a below-threshold chunk exists) and `M3_no_threshold` (the
  threshold filter dropped entirely, so a below-threshold chunk reaches the LLM as a "source").
  `test_below_threshold_nonempty_refuses_and_records_real_top_similarity` below kills both: it
  pins `top_similarity` to the chunk's REAL cosine value (not `None`) alongside `retrieval_found
  is False` and zero sources reaching the LLM, so a mutant that infers "found" from "similarity
  is not None" and a mutant that skips the threshold filter both diverge from it.
- **M-5** (round 1): `ChatRequest.message` had no length/whitespace guard, so `{"message": ""}`
  and `{"message": "   "}` both 200'd, burning an LLM call, persisting a blank "question", and
  poisoning phase-7's `report_content_gaps`. `app/models/schemas/chat.py`'s `min_length=1` +
  `_message_not_whitespace_only` validator (mirroring `ContentCreate.title`'s established
  two-guard pattern) close this; the two tests below pin the 422 + §9 envelope for both cases.
- **R-1** (round 2, ruled required — RR-3 of the review): round 1's I-1 fix (the whole exchange,
  not just the LLM call, lives inside `_generate_chat_stream`'s one `try`) had zero regression
  coverage — the reviewer's `M10_pre_fix_structure` mutant (reverting the fix in memory) left all
  20 previously-committed tests green, because `test_llm_failure_mid_stream_...` only ever enters
  the `try` AFTER the region I-1 restructured. `test_pre_stream_retrieval_failure_...` below is
  the reviewer's own ~25-line spec: a `FailingEmbedder` that raises before any token, asserting
  exactly one `error` event (also pinning M-7's `exc.code` passthrough) and a persisted user row.
- **N-2** (round 2): "citations ordered by first use, not sorted" was only weakly pinned — the
  pinned test's fixture slugs (`asymmetry-content-a`/`-b`) happen to sort alphabetically in the
  same order as first use, so `M9_dedupe_sorted_by_slug` (dedupe then sort by slug) survives the
  whole suite deterministically. `test_first_use_order_survives_when_alphabetical_order_disagrees`
  below picks slugs where alphabetical order is the OPPOSITE of first-use order.

Fakes/helpers are redefined locally (CONVENTIONS.md §10 / the original test-author's own
precedent: no cross-test-file imports) — `FakeEmbedder`, `_vector_at_cosine`, `_add_content`/
`_add_chunk`, the SSE parsing helpers, and `_build_client`/`_post_chat` are near-verbatim copies
of `tests/test_public_chat.py`'s own (itself derived from `tests/test_retrieval.py`'s), trimmed to
only what these findings need.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL` is
set, and are skipped by fixture name otherwise (`tests/conftest.py::pytest_collection_modifyitems`).
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
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db import make_session_factory
from app.factory import create_app
from app.models import ChatMessage, Chunk, Content
from app.services.errors import EmbeddingFailedError

# `nvidia/nv-embedqa-e5-v5` (PRD §7.2 v1.5) — matches `Chunk.embedding`'s `Vector(1024)` column
# and `Settings.embedding_dimensions`'s default, same as `test_public_chat.py`/`test_retrieval.py`.
_DIMS = 1024


def _vector_at_cosine(cos_theta: float, *, dims: int = _DIMS) -> list[float]:
    """A unit vector whose cosine similarity to `QUERY_VECTOR` is exactly `cos_theta`.

    Identical construction to `test_public_chat.py`/`test_retrieval.py`'s own (re-derived locally
    per the no-cross-test-file-imports rule).
    """
    sin_theta = math.sqrt(1.0 - cos_theta * cos_theta)
    return [cos_theta, sin_theta] + [0.0] * (dims - 2)


QUERY_VECTOR = _vector_at_cosine(1.0)  # == [1.0, 0.0, ..., 0.0]


@dataclass
class FakeEmbedder:
    """Deterministic `Embedder` fake — always returns `vector` regardless of input text.

    Verbatim shape of `tests/test_public_chat.py::FakeEmbedder`.
    """

    vector: list[float]
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [self.vector for _ in texts]


class FailingEmbedder:
    """An `Embedder` fake whose `embed_texts` always raises `EmbeddingFailedError` — simulates
    the embedding provider rejecting the query-embedding call (e.g. a rotated/expired
    `NVIDIA_API_KEY`) BEFORE any token is streamed and before the chat LLM is ever reached.

    Review round 1 finding I-1 / round 2 finding R-1: this is the regression-pin fake for "a
    pre-token failure anywhere in the exchange must still produce the SSE `error` event" —
    `app.rag.retrieval.retrieve()` calls `embed_texts` as its very first step, so this fires
    before `_generate_chat_stream` ever reaches `chat_llm.stream_answer`.
    """

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        raise EmbeddingFailedError("The embedding provider call failed.")


@dataclass(frozen=True)
class RecordedChatCall:
    """One recorded `FakeChatLLM.stream_answer` call — what the app actually passed it."""

    system: str
    question: str
    sources: tuple[object, ...]


@dataclass
class FakeChatLLM:
    """Scripted, recording `ChatLLM` fake — verbatim shape of `test_public_chat.py::FakeChatLLM`,
    trimmed (no `fail_after`: neither test below needs a mid-stream failure).
    """

    answer_tokens: list[str]
    refusal_tokens: list[str] = field(
        default_factory=lambda: ["No published guidance covers this."]
    )
    calls: list[RecordedChatCall] = field(default_factory=list)

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        self.calls.append(
            RecordedChatCall(system=system, question=question, sources=tuple(sources))
        )
        script = self.answer_tokens if sources else self.refusal_tokens
        yield from script


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
) -> None:
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


def _content_level_citation(content: Content) -> dict[str, str]:
    """The deduped, content-level wire shape (PRD §5.3/§4) — verbatim shape of
    `test_public_chat.py::_content_level_citation`.
    """
    return {"content_id": str(content.id), "title": content.title, "slug": content.slug}


@dataclass(frozen=True)
class SseEvent:
    """One parsed `event: <name>` / `data: <json>` block — verbatim shape of
    `test_public_chat.py::SseEvent`.
    """

    name: str
    data: dict[str, object]


def _parse_sse_events(body: str) -> list[SseEvent]:
    """Parse an SSE body into an ordered list of `SseEvent`s — verbatim logic of
    `test_public_chat.py::_parse_sse_events`.
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


def _post_chat(client: TestClient, body: dict[str, object]) -> tuple[int, str, str]:
    """POST `/api/v1/public/chat` via the streaming interface; return (status, content_type, body).

    Verbatim shape of `test_public_chat.py::_post_chat`.
    """
    with client.stream("POST", "/api/v1/public/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


def _build_client(
    tmp_engine: Engine, *, chat_llm: FakeChatLLM, embedder: FakeEmbedder
) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with the chat LLM + embedder seams faked
    — verbatim shape of `test_public_chat.py::_build_client`.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        chat_llm=chat_llm,
        embedder=embedder,
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# M-1: §7.4 below-threshold-but-NONEMPTY refusal — kills mutants M2/M3.
# ---------------------------------------------------------------------------


def test_below_threshold_nonempty_refuses_and_records_real_top_similarity(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §7.4: a chunk that exists but scores BELOW `SIMILARITY_THRESHOLD` (default 0.35, an
    empty index is a different case entirely — `test_public_chat.py`'s test 7 already covers
    that) must still refuse (zero sources reach the LLM, `citations: []`), while
    `retrieval_found` is `False` and `top_similarity` is the chunk's REAL cosine value — NOT
    `None` (task-01's `RetrievalResult.top_similarity` is `None` only when the index itself
    returns nothing, never merely because nothing cleared the threshold).

    Kills reviewer mutant `M2_found_from_top_similarity` (`retrieval_found = top_similarity is
    not None`, which is wrong here since `top_similarity` is a real `0.2`, not `None`, yet the
    correct `retrieval_found` is still `False`) and `M3_no_threshold` (the threshold filter
    dropped entirely — a below-threshold chunk would reach the LLM as a source and produce a
    non-empty `citations` event, contradicting the assertions below).
    """
    content = _add_content(db_session, slug="below-threshold-content")
    # 0.2 < the default SIMILARITY_THRESHOLD (0.35, app/config.py) — a real, non-empty candidate
    # that the threshold filter must still drop.
    _add_chunk(db_session, content.id, chunk_index=0, text="a barely-related chunk", cos_theta=0.2)
    db_session.commit()

    refusal_tokens = ["No ", "published ", "guidance ", "covers ", "this."]
    chat_llm = FakeChatLLM(
        answer_tokens=["Should ", "never ", "stream."], refusal_tokens=refusal_tokens
    )
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    status, _content_type, body = _post_chat(client, {"message": "A below-threshold question."})

    assert status == 200, body
    events = _parse_sse_events(body)
    names = [event.name for event in events]
    assert "error" not in names, names
    assert "".join(str(event.data["text"]) for event in events if event.name == "token") == "".join(
        refusal_tokens
    )

    citations_event = next(e for e in events if e.name == "citations")
    assert citations_event.data == {"citations": []}

    done_event = next(e for e in events if e.name == "done")
    message_id = uuid.UUID(str(done_event.data["message_id"]))

    assert len(chat_llm.calls) == 1
    assert chat_llm.calls[0].sources == ()  # the refusal pin: zero sources reached the LLM

    with make_session_factory(tmp_engine)() as fresh:
        assistant_row = fresh.get(ChatMessage, message_id)
        assert assistant_row is not None
        assert assistant_row.retrieval_found is False
        # The load-bearing assertion this test exists for: a REAL value, not None.
        assert assistant_row.top_similarity == pytest.approx(0.2, abs=1e-3)
        assert not assistant_row.citations


# ---------------------------------------------------------------------------
# M-5: empty/whitespace-only `message` -> 422 + §9 envelope.
# ---------------------------------------------------------------------------


def test_empty_message_is_rejected_with_422_envelope(tmp_engine: Engine) -> None:
    """`{"message": ""}` must 422 with the §9 envelope, not reach the route at all (no LLM call,
    no session/message rows) — `ChatRequest.message`'s `Field(min_length=1)`.
    """
    chat_llm = FakeChatLLM(answer_tokens=["unused"])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    response = client.post("/api/v1/public/chat", json={"message": ""})

    assert response.status_code == 422, response.text
    envelope = response.json()
    assert envelope["error"]["code"] == "validation_error"
    assert isinstance(envelope["error"]["message"], str) and envelope["error"]["message"]
    assert len(chat_llm.calls) == 0


def test_whitespace_only_message_is_rejected_with_422_envelope(tmp_engine: Engine) -> None:
    """`{"message": "   "}` must 422 the same way a byte-empty message does — `min_length=1`
    alone counts characters, not content, so `ChatRequest._message_not_whitespace_only` (mirrors
    `ContentCreate.title`'s established two-guard pattern) is the guard actually exercised here.
    """
    chat_llm = FakeChatLLM(answer_tokens=["unused"])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    response = client.post("/api/v1/public/chat", json={"message": "   "})

    assert response.status_code == 422, response.text
    envelope = response.json()
    assert envelope["error"]["code"] == "validation_error"
    assert isinstance(envelope["error"]["message"], str) and envelope["error"]["message"]
    assert len(chat_llm.calls) == 0


# ---------------------------------------------------------------------------
# R-1 (round 2, RR-3 — required): I-1 regression pin — a pre-token failure still
# produces exactly one `error` event, and the user's message survives it.
# ---------------------------------------------------------------------------


def test_pre_stream_retrieval_failure_emits_error_event_and_persists_user_message(
    tmp_engine: Engine, db_session: Session
) -> None:
    """Review round 1 finding I-1 / round 2 finding R-1 (regression pin, reviewer-specified): a
    failure INSIDE `retrieve()` — before any token is streamed, before the chat LLM is ever
    called — must still produce exactly one SSE `error` event (not an unhandled `RuntimeError`
    and a dead connection), and the user's message must survive it, durably, from a fresh
    session.

    Also pins M-7: the wire `code` is `EmbeddingFailedError`'s OWN code (`embedding_failed`), not
    the generic `chat_synthesis_failed` fallback `test_llm_failure_mid_stream_...`
    (`test_public_chat.py`, pinned) exercises for a plain `RuntimeError`.

    This is the reviewer's own regression proof (RR-3): reverting `_generate_chat_stream` back to
    the pre-fix shape (`retrieve()`/session writes OUTSIDE the `try`, only the LLM loop inside)
    leaves `test_public_chat.py`'s 9 tests green — this test is the one that catches that revert.
    See the fix report for the git-stash proof.
    """
    chat_llm = FakeChatLLM(answer_tokens=["Should ", "never ", "stream."])
    embedder = FailingEmbedder()
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)
    question = "A question that fails before any token is streamed."

    status, content_type, body = _post_chat(client, {"message": question})

    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type
    events = _parse_sse_events(body)
    names = [event.name for event in events]
    assert names == ["error"], names
    assert len(chat_llm.calls) == 0  # the chat LLM must never be reached

    error_payload = events[0].data["error"]
    assert isinstance(error_payload, dict)
    assert error_payload["code"] == "embedding_failed"
    assert isinstance(error_payload["message"], str) and error_payload["message"]

    with make_session_factory(tmp_engine)() as fresh:
        rows = list(fresh.execute(select(ChatMessage)).scalars())

    assert len(rows) == 1, rows
    assert rows[0].role == "user"
    assert rows[0].content == question


# ---------------------------------------------------------------------------
# N-2 (round 2): first-use citation order must survive when alphabetical
# (slug) order disagrees with it.
# ---------------------------------------------------------------------------


def test_first_use_order_survives_when_alphabetical_order_disagrees(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §5.3/§4: `dedupe_citations` must order by FIRST USE, not by any other key. The pinned
    `test_public_chat.py`'s asymmetry test uses slugs (`asymmetry-content-a`/`-b`) that happen to
    sort alphabetically in first-use order too, so a dedupe-then-sort-by-slug implementation
    passes it by coincidence (review round 2, finding N-2). Here the FIRST-used content's slug
    (`zebra-first-use`) sorts LAST alphabetically, and the SECOND-used content's slug
    (`alpha-second-use`) sorts FIRST — only a genuine first-occurrence-order dedupe produces
    `[zebra, alpha]`; any sort-based dedupe (by slug, content_id, or title) produces `[alpha,
    zebra]` instead.
    """
    content_zebra = _add_content(db_session, slug="zebra-first-use")
    content_alpha = _add_content(db_session, slug="alpha-second-use")
    # Similarity-descending retrieval order: zebra (.9) is retrieved first -> first use; alpha
    # (.7) second. Alphabetically, "alpha-second-use" < "zebra-first-use" — the opposite order.
    _add_chunk(db_session, content_zebra.id, chunk_index=0, text="zebra chunk", cos_theta=0.9)
    _add_chunk(db_session, content_alpha.id, chunk_index=0, text="alpha chunk", cos_theta=0.7)
    db_session.commit()

    chat_llm = FakeChatLLM(answer_tokens=["Grounded ", "answer."])
    embedder = FakeEmbedder(vector=QUERY_VECTOR)
    client = _build_client(tmp_engine, chat_llm=chat_llm, embedder=embedder)

    status, _content_type, body = _post_chat(client, {"message": "Tell me about zebra and alpha."})

    assert status == 200, body
    events = _parse_sse_events(body)
    names = [event.name for event in events]
    assert "error" not in names, names

    citations_event = next(e for e in events if e.name == "citations")
    # First-use order (zebra, then alpha) — NOT alphabetical (alpha, then zebra).
    assert citations_event.data == {
        "citations": [
            _content_level_citation(content_zebra),
            _content_level_citation(content_alpha),
        ]
    }
