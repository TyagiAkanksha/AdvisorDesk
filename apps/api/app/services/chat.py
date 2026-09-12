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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.models import ChatMessage, ChatSession
from app.services.errors import NotFoundError


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
    @property
    def similarity(self) -> float: ...


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
    session: Session,
    chat_session_id: uuid.UUID,
    text: str,
    retrieval: RetrievalResultLike,
    *,
    latency_ms: int | None = None,
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

    Phase-9 DESIGN §A: each chunk-level citation entry also carries the retriever's own
    `similarity`, rounded to 4 dp — so every stored answer doubles as a retrieval trace. Readers
    must use `.get("similarity")` (pre-0009 rows have none). `latency_ms` is keyword-only and
    defaults to `None` so every existing call site keeps working unchanged.

    Args:
        session: the caller's `Session`.
        chat_session_id: the owning `ChatSession.id`.
        text: the assistant's full answer text (already accumulated from the token stream).
        retrieval: the `RetrievalResult` (or any structurally-compatible `RetrievalResultLike`)
            this answer was grounded in.
        latency_ms: the route's own whole-answer `time.monotonic()` measurement, or `None` when
            the caller has none to report.

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
            "similarity": round(chunk.similarity, 4),
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
        latency_ms=latency_ms,
    )
    session.add(message)
    session.flush()
    return message


def set_message_feedback(session: Session, message_id: uuid.UUID, value: int) -> ChatMessage:
    """Record 👍/👎 on one assistant turn (phase-9 DESIGN §A).

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first; flush only).
        message_id: the `ChatMessage.id` the `done` SSE event handed the client.
        value: `-1` or `1` — already validated on the wire by `ChatFeedbackRequest`.

    Returns:
        The updated `ChatMessage` row.

    Raises:
        NotFoundError: no such row, or the row is not an assistant turn — a user message has no
            answer to rate, and the two cases are deliberately indistinguishable to the caller
            (same §9 envelope), since the client never legitimately holds a user-row id.
    """
    message = session.get(ChatMessage, message_id)
    if message is None or message.role != "assistant":
        raise NotFoundError(f"No assistant message {message_id}.")
    message.feedback = value
    session.flush()
    return message


@dataclass(frozen=True)
class GapRow:
    """One §6 content gap: a user question whose next reply found no matching content."""

    question: str
    asked_at: datetime
    session_id: uuid.UUID


def content_gaps(session: Session, *, days: int = 30, limit: int = 20) -> list[GapRow]:
    """`report_content_gaps`'s query (PRD §6, normative): user messages whose following
    assistant message (same session, next by `created_at`) has `retrieval_found = False`.

    Pairing: for each `role="user"` row, its partner is the `role="assistant"` row in the
    SAME `session_id` with the smallest `created_at` strictly greater than the user row's own
    — found here via a correlated `MIN(created_at)` scalar subquery, then joined back on that
    exact value, rather than a `LIMIT 1`-per-row approach (SQLAlchemy has no clean per-row
    "top 1 correlated" without a `LATERAL` join, and the `MIN(...)` + equality-join shape is
    the ordinary, portable way to express "next row by column" in SQL). A user row with no
    following assistant row at all correlates to `MIN(...) = NULL`, which the join's equality
    condition can never satisfy — SQL's three-valued `NULL = NULL -> NULL` (never `TRUE`)
    excludes it from the join for free, which is exactly the "no following assistant message
    -> not a gap" rule (task-01 brief Step 1).

    The join's `retrieval_found.is_(False)` (not `.isnot(True)`, which NULL would also satisfy)
    is what keeps a lone user message — one with no assistant row anywhere, hence no partner
    row's `retrieval_found` to inspect at all — out of the result, and separately guards
    against ever treating NULL as "uncovered" if this predicate is ever reused elsewhere.

    The `days` window applies to the user message's own `created_at` (the question's
    `asked_at`, not the paired reply's) — the brief's "last `days` days" reads on when the
    question was ASKED.

    Args:
        session: the caller's `Session`.
        days: only gaps asked within the last `days` days (from now) are returned.
        limit: caps the number of gaps returned, newest-first.

    Returns:
        `GapRow`s ordered newest-`asked_at`-first, at most `limit` of them.
    """
    user_msg = aliased(ChatMessage)
    reply_msg = aliased(ChatMessage)

    next_reply_created_at = (
        select(func.min(reply_msg.created_at))
        .where(
            reply_msg.session_id == user_msg.session_id,
            reply_msg.role == "assistant",
            reply_msg.created_at > user_msg.created_at,
        )
        .correlate(user_msg)
        .scalar_subquery()
    )

    cutoff = datetime.now(UTC) - timedelta(days=days)

    stmt = (
        select(user_msg.content, user_msg.created_at, user_msg.session_id)
        .join(
            reply_msg,
            and_(
                reply_msg.session_id == user_msg.session_id,
                reply_msg.role == "assistant",
                reply_msg.created_at == next_reply_created_at,
            ),
        )
        .where(
            user_msg.role == "user",
            user_msg.created_at >= cutoff,
            reply_msg.retrieval_found.is_(False),
        )
        .order_by(user_msg.created_at.desc())
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    return [
        GapRow(question=row.content, asked_at=row.created_at, session_id=row.session_id)
        for row in rows
    ]
