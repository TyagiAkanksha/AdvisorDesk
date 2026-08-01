"""Chat persistence services: sessions, user/assistant messages (PRD §4, §5.3, §7.4, §7.7).

Plain, session-first functions (CONVENTIONS.md §3) — no retrieval, no LLM calls, no SSE framing:
those live in `app.rag`/`app.routes`, which `app.services` may never import (CONVENTIONS.md §2
layering: "app.services imports only app.models and app.config"). `record_assistant_message`
therefore accepts a structurally-typed `RetrievalResultLike`, not `app.rag.retrieval.
RetrievalResult` itself — importing `app.rag` from here is exactly what the layering contract
forbids; the real `RetrievalResult`/`RetrievedChunk` (task-01) already satisfy this shape with no
inheritance relationship, the same seam pattern `app.rag.embeddings.Embedder` uses in the other
direction.

Phase-7's `report_content_gaps` MCP tool reads `retrieval_found`/`top_similarity` back off the
rows this module writes — those column semantics (PRD §7.4) are pinned here, once.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession


class RetrievedChunkLike(Protocol):
    """The subset of `app.rag.retrieval.RetrievedChunk`'s shape this module needs.

    A structural (attribute-based) `Protocol`, satisfied by the real `RetrievedChunk` dataclass
    with no inheritance relationship and no import of `app.rag` from this module. Declared via
    read-only `@property` members (not plain `attr: Type` annotations, which mypy treats as
    settable) because `RetrievedChunk` is a frozen dataclass — a plain mutable-attribute Protocol
    would reject it as "expected settable variable, got read-only attribute".
    """

    @property
    def content_id(self) -> uuid.UUID: ...
    @property
    def chunk_id(self) -> uuid.UUID: ...
    @property
    def title(self) -> str: ...
    @property
    def slug(self) -> str: ...


class RetrievalResultLike(Protocol):
    """The subset of `app.rag.retrieval.RetrievalResult`'s shape this module needs.

    Same structural-typing rationale as `RetrievedChunkLike` above (read-only `@property`
    members, since `RetrievalResult` is also a frozen dataclass).
    """

    @property
    def chunks(self) -> Sequence[RetrievedChunkLike]: ...
    @property
    def top_similarity(self) -> float | None: ...


def get_or_create_session(session: Session, session_id: uuid.UUID | None) -> ChatSession:
    """Return the `ChatSession` for `session_id`, or create a new one (PRD §5.3).

    PRD §5.3: an absent OR unknown `session_id` both mean "start a new session" — this function
    makes no distinction between the two: a `None` id and an id with no matching row both fall
    through to creating a fresh session. Never raises for an unrecognized id (unlike a bare by-id
    404 elsewhere in this app, e.g. `app.services.content.get_published_by_slug`) — that is the
    point of this rule (§5.3: "no error, unlike a bare 404").

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first).
        session_id: the client-supplied session id, or `None` if the client never had one.

    Returns:
        The existing `ChatSession` row for `session_id`, or a newly created (and flushed) one.
    """
    if session_id is not None:
        existing = session.get(ChatSession, session_id)
        if existing is not None:
            return existing
    chat_session = ChatSession()
    session.add(chat_session)
    session.flush()
    return chat_session


def record_user_message(session: Session, chat_session_id: uuid.UUID, text: str) -> ChatMessage:
    """Persist one `role="user"` turn (PRD §7.7) — no citations/outcome columns: those are
    populated on assistant rows only (PRD §4).

    Args:
        session: the caller's `Session`.
        chat_session_id: the owning `ChatSession.id`.
        text: the user's message, verbatim.

    Returns:
        The newly created (and flushed) `ChatMessage` row.
    """
    message = ChatMessage(session_id=chat_session_id, role="user", content=text)
    session.add(message)
    session.flush()
    return message


def record_assistant_message(
    session: Session, chat_session_id: uuid.UUID, text: str, retrieval: RetrievalResultLike
) -> ChatMessage:
    """Persist one `role="assistant"` turn with its retrieval outcome (PRD §7.4, §7.7, §4).

    PRD §4 "Citation granularity (deliberate asymmetry)": this row stores chunk-level citations
    (one entry per retrieved chunk, `chunk_id` included) — because the groundedness harness
    (phase 7) must know exactly which chunks supported the answer. This is the DB half of the
    asymmetry; the wire `citations` SSE event dedupes the SAME chunks to content level instead
    (`app.rag.synthesis.dedupe_citations`, built by the route right before it goes over the wire).

    `retrieval_found` is `False` iff `retrieval.chunks` is empty (PRD §7.4: "false when no chunk
    cleared the threshold"); `top_similarity` is `retrieval.top_similarity` verbatim — `None`
    exactly when `app.rag.retrieval.retrieve()` says so (its own docstring's None-iff-empty-index
    semantics), never recomputed here.

    Args:
        session: the caller's `Session`.
        chat_session_id: the owning `ChatSession.id`.
        text: the assistant's full answer text (already accumulated from the token stream).
        retrieval: the `RetrievalResult` (or any structurally-compatible `RetrievalResultLike`)
            this answer was grounded in.

    Returns:
        The newly created (and flushed) `ChatMessage` row.
    """
    # PRD §4 asymmetry, DB half: chunk-level citations, `chunk_id` included — content level
    # (deduped) is a wire-only concern, built separately at the route (`dedupe_citations`).
    citations = [
        {
            "content_id": str(chunk.content_id),
            "title": chunk.title,
            "slug": chunk.slug,
            "chunk_id": str(chunk.chunk_id),
        }
        for chunk in retrieval.chunks
    ]
    message = ChatMessage(
        session_id=chat_session_id,
        role="assistant",
        content=text,
        citations=citations,
        retrieval_found=bool(retrieval.chunks),
        top_similarity=retrieval.top_similarity,
    )
    session.add(message)
    session.flush()
    return message
