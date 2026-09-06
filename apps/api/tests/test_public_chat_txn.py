"""New (RED) test for WR-09: `/public/chat` must release the retrieval transaction before the
LLM streaming loop begins, not hold it open across the whole stream.

Task brief: docs/plans/phase-6-remediation/task-08-held-txn-agent-tests-metrics.md, WR-09.

Current bug (`app/routes/public_routes.py::_generate_chat_stream`): the user-message write IS
already committed early (right after `record_user_message`, before `retrieve()` — module
docstring's own "committed right after it's written" claim), but `retrieve()`'s own read-only
`session.execute(select(...))` (`app.rag.retrieval.retrieve`) runs AFTER that commit, on the SAME
session — SQLAlchemy's autobegin starts a NEW transaction for it, and nothing closes that
transaction again until `record_assistant_message`'s write is committed AFTER the entire
`chat_llm.stream_answer(...)` loop has finished. That second transaction — opened by the
retrieval SELECT — is the one actually "held open ... through the entire token-streaming loop to
the post-stream commit" the WR-09 brief describes; it stays open for as long as the (potentially
slow, network-bound) LLM stream runs.

This test pins the fix's actual observable property WITHOUT touching either pinned public-chat
test file (`tests/test_public_chat.py`, `tests/test_public_chat_guards.py`): between the moment
`retrieve()` returns and the moment the LLM's `stream_answer` generator is first driven, a
`Session.commit()` (or equivalent transaction-releasing call) must have happened — i.e. no
Postgres transaction is left open while the (slow) stream loop runs. It never asserts anything
about a SPECIFIC number of commits or a specific commit/write ordering beyond that one gap, so it
stays valid across any reasonable implementation of the fix (e.g. one extra `session.commit()`
right after `retrieve()`, or reordering retrieval before the user-message write+commit).

Instrumentation: `Session.commit` (the SQLAlchemy class, patched globally for the duration of the
test only, via `monkeypatch`) and `app.routes.public_routes.retrieve` (the exact call site
`_generate_chat_stream` uses) are both wrapped to append a marker into one shared, ordered list;
the fake `ChatLLM.stream_answer` appends its own marker the instant it starts producing tokens.
No pinned file is imported, read from, or modified — a minimal local `_FakeEmbedder` is defined
here per the established no-cross-test-file-imports convention.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL` is
set, skipped by fixture name otherwise (`tests/conftest.py::pytest_collection_modifyitems`) — the
one test below requests `tmp_engine`, so the whole module skips cleanly without a DB.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import make_session_factory
from app.factory import create_app
from app.routes import public_routes

# `nvidia/nv-embedqa-e5-v5` (PRD §7.2 v1.5) dimensionality — matches `Settings.
# embedding_dimensions`'s default; the exact vector VALUE is irrelevant here (no `Chunk` rows are
# ever seeded, so pgvector's `<=>` never actually evaluates against a stored row — same
# intentionally-no-content precedent `tests/test_metrics.py::FakeEmbedder` follows).
_DIMS = 1024


@dataclass
class _FakeEmbedder:
    """Minimal `Embedder` fake — always returns a fixed, well-formed vector."""

    vector: list[float]

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        return [self.vector for _ in texts]


@dataclass
class _MarkingChatLLM:
    """A `ChatLLM` fake whose `stream_answer` appends `"stream_enter"` to the shared `events`
    list the INSTANT it starts producing tokens (i.e. the instant the route's `for token in
    chat_llm.stream_answer(...)` loop first calls `next()` on it) — the checkpoint this test
    measures "is any transaction still open?" against.
    """

    events: list[str]
    tokens: list[str] = field(default_factory=lambda: ["An ", "answer."])

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        self.events.append("stream_enter")
        yield from self.tokens


def test_retrieval_txn_released_before_llm_stream_loop_begins(
    tmp_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WR-09: the transaction `retrieve()`'s SELECT opens must be released (committed) before
    `chat_llm.stream_answer(...)` starts producing tokens — never held open across the whole
    stream. RED on today's code: `retrieve()` runs, then the stream loop starts immediately with
    no intervening `session.commit()`, so the transaction opened for retrieval is still open for
    the entire (potentially slow) LLM stream, only closing at the POST-stream commit after
    `record_assistant_message`. GREEN once the implementer releases that transaction before the
    stream loop begins (e.g. one extra `session.commit()` right after `retrieve()` returns).
    """
    events: list[str] = []

    # Spy on every `Session.commit()` call, system-wide, for the duration of this test only
    # (`monkeypatch` reverts automatically on teardown) — the one place any transaction, on any
    # session, actually gets released.
    original_commit = Session.commit

    def _spy_commit(self: Session, *args: object, **kwargs: object) -> None:
        events.append("commit")
        original_commit(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Session, "commit", _spy_commit)

    # Spy on the EXACT call site `_generate_chat_stream` uses (`app.routes.public_routes.
    # retrieve`, imported by name into that module) — marks the moment the retrieval SELECT has
    # actually completed, without needing to inspect `app.rag.retrieval.retrieve`'s internals.
    original_retrieve = public_routes.retrieve

    def _spy_retrieve(*args: object, **kwargs: object) -> object:
        result = original_retrieve(*args, **kwargs)  # type: ignore[arg-type]
        events.append("retrieval_done")
        return result

    monkeypatch.setattr(public_routes, "retrieve", _spy_retrieve)

    chat_llm = _MarkingChatLLM(events=events)
    embedder = _FakeEmbedder(vector=[0.1] * _DIMS)
    app = create_app(
        session_factory=make_session_factory(tmp_engine), chat_llm=chat_llm, embedder=embedder
    )
    client = TestClient(app)

    with client.stream("POST", "/api/v1/public/chat", json={"message": "A question."}) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200, body  # sanity: the exchange actually ran end to end
    assert "retrieval_done" in events, events
    assert "stream_enter" in events, events

    retrieval_at = events.index("retrieval_done")
    stream_at = events.index("stream_enter")
    assert retrieval_at < stream_at, events  # sanity: retrieval really precedes the stream loop

    between = events[retrieval_at + 1 : stream_at]
    assert "commit" in between, (
        "expected the transaction opened by retrieve()'s SELECT to be committed/released "
        f"before chat_llm.stream_answer(...) starts producing tokens; events={events}"
    )
