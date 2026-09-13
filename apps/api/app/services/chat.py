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
rows this module writes — those column semantics (PRD §7.4) are pinned here, once. Phase-9 task 15
adds a second, broader reader of the same rows: `weak_queries` (DESIGN §D), which classifies every
paired turn instead of only the refusals `content_gaps` sees — both share one private pairing,
`_paired_turns`.
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
from app.services.eval_policy import LOW_CONFIDENCE_BAND, NEAR_MISS_BAND


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


@dataclass(frozen=True)
class _PairedTurn:
    """One user question joined to its next assistant reply, with that reply's outcome columns.

    Private: the ONE shape both `content_gaps` (PRD §6, frozen) and `weak_queries` (phase-9
    DESIGN §D) read the §6 pairing through. Adding a consumer must not re-derive the join.

    `answer` (controller ruling, 2026-09-12 — an authorized extension beyond the task file's
    Interfaces, which named only `retrieval_found`/`top_similarity`/`feedback`): the paired
    assistant reply's own `content`. Without it, `weak_queries`' declining-answer rule (see its
    own docstring) has no way to see a row where retrieval cleared the threshold but the
    answerer declined anyway — `retrieval_found` alone cannot distinguish that case from a
    confident answer. Internal to this module either way: `content_gaps`'s public `GapRow`
    never carries it, so this extension is invisible outside `app.services.chat`.
    """

    question: str
    asked_at: datetime
    session_id: uuid.UUID
    retrieval_found: bool | None
    top_similarity: float | None
    feedback: int | None
    answer: str


def _paired_turns(
    session: Session, *, days: int, limit: int, uncovered_only: bool
) -> list[_PairedTurn]:
    """The §6 user↔reply pairing, newest question first, at most `limit` rows.

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

    When `uncovered_only` is `True`, the join also requires `retrieval_found.is_(False)` (not
    `.isnot(True)`, which NULL would also satisfy) — what keeps a lone user message — one with
    no assistant row anywhere, hence no partner row's `retrieval_found` to inspect at all — out
    of the result, and separately guards against ever treating NULL as "uncovered". When
    `uncovered_only` is `False`, every paired turn in the window comes back whatever its
    outcome, for a caller (`weak_queries`) that classifies rows itself instead of pre-filtering
    them in SQL.

    The `days` window applies to the user message's own `created_at` (the question's
    `asked_at`, not the paired reply's) — the brief's "last `days` days" reads on when the
    question was ASKED.

    Args:
        session: the caller's `Session`.
        days: window on the USER row's `created_at` (the question's `asked_at`), per §6.
        limit: SQL `LIMIT` on ROWS (not groups) — applied in SQL, before any Python filtering,
            so a caller that filters afterwards must pass a limit that accounts for it.
        uncovered_only: `True` adds `reply.retrieval_found.is_(False)` to the join (the §6 gap
            definition); `False` returns every paired turn in the window whatever its outcome.

    Returns:
        `_PairedTurn`s ordered newest-`asked_at`-first, at most `limit` of them.
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
        select(
            user_msg.content.label("question"),
            user_msg.created_at.label("asked_at"),
            user_msg.session_id.label("session_id"),
            reply_msg.retrieval_found.label("retrieval_found"),
            reply_msg.top_similarity.label("top_similarity"),
            reply_msg.feedback.label("feedback"),
            reply_msg.content.label("answer"),
        )
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
        )
        .order_by(user_msg.created_at.desc())
        .limit(limit)
    )
    if uncovered_only:
        stmt = stmt.where(reply_msg.retrieval_found.is_(False))

    rows = session.execute(stmt).all()
    return [
        _PairedTurn(
            question=row.question,
            asked_at=row.asked_at,
            session_id=row.session_id,
            retrieval_found=row.retrieval_found,
            top_similarity=row.top_similarity,
            feedback=row.feedback,
            answer=row.answer,
        )
        for row in rows
    ]


def content_gaps(session: Session, *, days: int = 30, limit: int = 20) -> list[GapRow]:
    """`report_content_gaps`'s query (PRD §6, normative) — unchanged behaviour, one line thick.

    A wrapper over `_paired_turns(..., uncovered_only=True)` since phase-9 task 15: the pairing it
    used to own inline is now shared with `weak_queries` (DESIGN §D). Signature, ordering, window
    and result rows are byte-identical to phase 7's — `tests/test_content_gaps.py`'s 12 tests and
    `mcp-tools.json` are the proof and must not move.
    """
    return [
        GapRow(question=turn.question, asked_at=turn.asked_at, session_id=turn.session_id)
        for turn in _paired_turns(session, days=days, limit=limit, uncovered_only=True)
    ]


# ---------------------------------------------------------------------------
# `weak_queries` (phase-9 task 15, DESIGN §D): a refusal is not the only way an answer can be
# weak — this is the second consumer of `_paired_turns`, above.
# ---------------------------------------------------------------------------

NEGATIVE_FEEDBACK = "negative_feedback"
REFUSED = "refused"
NEAR_MISS = "near_miss"
LOW_CONFIDENCE = "low_confidence"

#: Canonical order: the classification ladder itself (DESIGN §D, first match wins). Also the order
#: `WeakQueryGroup.kinds` lists the distinct kinds it saw, so two reports of the same group are
#: textually comparable.
WEAK_QUERY_KINDS: tuple[str, ...] = (NEGATIVE_FEEDBACK, REFUSED, NEAR_MISS, LOW_CONFIDENCE)

#: Hard ceiling on ROWS `weak_queries` pulls out of SQL before grouping. Grouping and
#: classification happen in Python (the `feedback`/band ladder is not expressible as one portable
#: GROUP BY over a correlated join), so `limit` cannot be pushed down: it caps GROUPS. This caps
#: the scan instead — orders of magnitude above this app's real 30-day volume (a single demo
#: session is tens of turns), and it keeps one pathological window from pulling the whole
#: `chat_messages` table into memory.
_WEAK_QUERY_SCAN_LIMIT = 2000

# Controller ruling (2026-09-12): the canonical refusal wording an answer emits when it declines
# (PRD §7.4 / `app.rag.synthesis.SYSTEM_PROMPT`'s own instruction to the model — "reply that no
# published guidance covers this"), as a casefolded SUBSTRING probe against the stored answer
# text. This is a documented REPORTING heuristic, not a judge call: it exists to let a report
# read history cheaply, with no LLM call of its own. `app.eval.groundedness`'s `_model_declined`
# (task 05c, backed by `MetricsJudge.is_refusal`) is the semantic, judge-based counterpart the
# eval harness uses instead — naming both here, in one place, is what keeps a future phrasing
# change in `app.rag.synthesis` from silently blinding this heuristic without either side ever
# raising an error.
_DECLINE_PHRASE = "no published guidance covers this"


def _is_declining_answer(answer: str) -> bool:
    """True when `answer` matches the canonical refusal phrasing (see `_DECLINE_PHRASE`'s own
    comment for why this is a reporting heuristic, not a judge call). Casefolded substring match,
    not exact-case."""
    return _DECLINE_PHRASE in answer.casefold()


@dataclass(frozen=True)
class WeakQueryExample:
    """One concrete turn behind a `WeakQueryGroup` — verbatim text, for the report/slide."""

    question: str
    kind: str
    top_similarity: float | None
    created_at: datetime


@dataclass(frozen=True)
class WeakQueryGroup:
    """One normalised question and every weak turn that asked it (DESIGN §D)."""

    normalized: str
    count: int
    kinds: list[str]  # distinct, in `WEAK_QUERY_KINDS` order
    worst_top_similarity: float | None  # min over non-None similarities; None iff all were None
    examples: list[WeakQueryExample]  # at most 3, newest `created_at` first


def _normalize_question(text: str) -> str:
    """DESIGN §D grouping rule: casefold, collapse internal whitespace, strip trailing
    `?`/`!`/`.` (and the spaces that stripping order leaves behind)."""
    return " ".join(text.split()).casefold().rstrip("?!. ")


def _classify_turn(turn: _PairedTurn, *, threshold: float) -> str | None:
    """Classify one paired turn per `weak_queries`' decision ladder, first match wins.

    One `if`/`return` per ladder rung, each commented with its row number from `weak_queries`'
    own docstring table — mirrors `app.eval.taxonomy.classify_failure`'s style.
    """
    # Row 1: a human thumbs-down outranks every inferred signal.
    if turn.feedback == -1:
        return NEGATIVE_FEEDBACK

    # Row 2 (controller ruling, 2026-09-12): retrieval CLEARED the threshold and the answerer
    # declined anyway — the case `retrieval_found` alone cannot see (task 05c's most interesting
    # weak query). Fires ONLY when `retrieval_found IS True` (not merely truthy): a NULL
    # `retrieval_found` must stay invisible to this rule exactly as it is to rows 3-5 below, and
    # a `retrieval_found is False` row is untouched by a declining answer here — "something was
    # close" (or wasn't) is information about RETRIEVAL, which rows 3-4 already classify on their
    # own; a decline adds nothing there.
    if turn.retrieval_found is True and _is_declining_answer(turn.answer):
        return NEAR_MISS

    # Row 3: nothing retrieved close enough to call it a near miss.
    if turn.retrieval_found is False and (
        turn.top_similarity is None or turn.top_similarity < threshold - NEAR_MISS_BAND
    ):
        return REFUSED

    # Row 4: nothing cleared the threshold, but something came close — the corpus almost had it.
    if turn.retrieval_found is False:
        return NEAR_MISS

    # Row 5: an answer was given, but only just above the threshold.
    if (
        turn.retrieval_found is True
        and turn.top_similarity is not None
        and turn.top_similarity < threshold + LOW_CONFIDENCE_BAND
    ):
        return LOW_CONFIDENCE

    return None


def weak_queries(
    session: Session, *, days: int = 30, limit: int = 20, threshold: float
) -> list[WeakQueryGroup]:
    """Client questions the system answered badly — not just the ones it refused (DESIGN §D).

    Every paired turn in the window is classified, FIRST MATCH WINS:

    | # | Kind | Condition |
    |---|---|---|
    | 1 | `negative_feedback` | `feedback == -1` |
    | 2 | `near_miss` | `retrieval_found is True` and the stored answer DECLINES |
    | 3 | `refused` | not found, and (`top_similarity is None` or `< threshold - NEAR_MISS_BAND`) |
    | 4 | `near_miss` | not found, and `top_similarity >= threshold - NEAR_MISS_BAND` |
    | 5 | `low_confidence` | found, and `top_similarity < threshold + LOW_CONFIDENCE_BAND` |

    Row 1 outranks every inferred signal — a human said so. Row 2 (controller ruling,
    2026-09-12) is the case `retrieval_found` alone cannot see: retrieval cleared the threshold
    and the answerer declined anyway (see `_is_declining_answer`). Narrower than it looks: this
    fires ONLY when `retrieval_found IS True` — a not-found row's classification (rows 3-4) is
    unaffected by a declining answer, because "something was close" is information about
    RETRIEVAL, and a decline adds nothing there.

    Anything else is not weak and is dropped. "found" means `retrieval_found is True` and "not
    found" means `retrieval_found is False` — a NULL `retrieval_found` (a pre-0009 row, whose
    outcome was never recorded) satisfies NEITHER, so such a row is weak only through rule 1. That
    mirrors `content_gaps`' deliberate `.is_(False)`-not-`.isnot(True)` choice: NULL is never read
    as "uncovered".

    Precedence, in one line: `negative_feedback` -> (`retrieval_found` and the answer declines ->
    `near_miss`) -> `refused` -> `near_miss` -> `low_confidence`.

    Turns are then grouped by normalised text (casefold, collapse whitespace, strip trailing
    `?`/`!`/`.`), ordered `count` desc, then `worst_top_similarity` asc (a group whose worst
    similarity is `None` sorts FIRST within its count — nothing was retrieved at all, which is as
    weak as it gets), then `normalized` asc as a deterministic final tiebreaker.

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first; reads only).
        days: window on when the question was ASKED (same rule as `content_gaps`).
        limit: maximum number of GROUPS returned (not rows — see `_WEAK_QUERY_SCAN_LIMIT`).
        threshold: the retrieval similarity threshold the answers were served under —
            `Settings.similarity_threshold`, passed in by the caller. Keyword-only with NO
            default: a band is meaningless against a guessed threshold, and `app.services` must
            not reach for `Settings` on its own (the MCP tool layer owns that wiring).

    Returns:
        `WeakQueryGroup`s, at most `limit` of them, in the order described above.
    """
    turns = _paired_turns(session, days=days, limit=_WEAK_QUERY_SCAN_LIMIT, uncovered_only=False)

    # Bucket by normalised question text. Insertion order into each bucket's list follows the
    # SQL's own newest-first order (see `_paired_turns`), so each bucket's entries are already
    # newest-first — `examples` below needs only a `[:3]` slice, never a re-sort.
    buckets: dict[str, list[tuple[_PairedTurn, str]]] = {}
    for turn in turns:
        kind = _classify_turn(turn, threshold=threshold)
        if kind is None:
            continue
        buckets.setdefault(_normalize_question(turn.question), []).append((turn, kind))

    groups = [_build_group(normalized, entries) for normalized, entries in buckets.items()]

    # Sorting key straight from the Interfaces notes: count desc, then worst-similarity asc with
    # `None` sorting first (nothing retrieved at all is at least as weak as any real number),
    # then normalized text asc as a final, fully deterministic tiebreaker.
    groups.sort(
        key=lambda group: (
            -group.count,
            group.worst_top_similarity if group.worst_top_similarity is not None else -1.0,
            group.normalized,
        )
    )
    return groups[:limit]


def _build_group(normalized: str, entries: list[tuple[_PairedTurn, str]]) -> WeakQueryGroup:
    """Fold one bucket of `(turn, kind)` entries (already newest-first, see `weak_queries`) into
    its `WeakQueryGroup`: distinct kinds in ladder order, the worst (minimum) similarity seen —
    `None` only when every turn in the bucket had `top_similarity is None` — and at most 3
    examples, newest first (a `[:3]` slice needs no re-sort; see `weak_queries`)."""
    similarities = [turn.top_similarity for turn, _ in entries if turn.top_similarity is not None]
    return WeakQueryGroup(
        normalized=normalized,
        count=len(entries),
        kinds=[kind for kind in WEAK_QUERY_KINDS if any(entry[1] == kind for entry in entries)],
        worst_top_similarity=min(similarities) if similarities else None,
        examples=[
            WeakQueryExample(
                question=turn.question,
                kind=kind,
                top_similarity=turn.top_similarity,
                created_at=turn.asked_at,
            )
            for turn, kind in entries[:3]
        ],
    )
