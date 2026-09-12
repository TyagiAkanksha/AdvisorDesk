"""Public content + chat REST routes: the unauthenticated client-app surface (PRD §5.3).

CONVENTIONS.md §4: the `/public/content*` routes below contain no `try/except` —
`content_service.get_published_by_slug`'s `NotFoundError` flows to
`app.routes.errors::register_error_handlers`, which builds the PRD §9
envelope. Thin: call service -> DTO. None of the routes in this module
depend on `require_admin` (contrast every route in
`app.routes.content_routes`) — PRD §5.3: "client routes are public", no
session/cookie of any kind.

`tags_for_contents` is the only tag lookup the content routes perform
(task-03 brief Interfaces block, same rule `app.routes.content_routes`
follows) — the list route batches it into one call for the whole result
set (no N+1); the detail route calls it once for its single id.

Review round 1, finding M3: a slash-bearing or otherwise unroutable slug
(e.g. `.../content/a/b`) never reaches `public_content_get` at all — it
404s at the ROUTER, before any handler runs, with code `http_404` (via
`app.routes.errors::_http_exception_handler`), distinct from a routable-
but-unknown slug's `not_found` code from `get_published_by_slug`; both are
"this slug doesn't resolve to content" and task-04's error handling should
treat them the same way.

`public_chat` (phase-4 task-02, PRD §5.3, §7.5-§7.7) is the one exception to
"routes contain no try/except": `_generate_chat_stream` (its SSE body
generator) DOES catch, under CONVENTIONS.md §4's explicit outermost-SSE-
generator carve-out (review round 1, finding C-1) — a manually-built
`error` event is the only way to report a failure once the 200 has already
been sent, since `register_error_handlers` never runs again for this
request. Review round 1, finding I-1: the WHOLE exchange (session lookup,
user-message write, retrieval, synthesis, assistant-message write) lives
inside that one `try`, not just the LLM call — a pre-token failure (e.g. the
embedding provider call inside `retrieve()`) must also produce an `error`
event, not an unhandled `RuntimeError` from FastAPI ("response already
started") and a dead connection.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ChatSession, Content
from app.models.schemas.chat import ChatRequest
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.public import (
    ChatFeedbackRequest,
    PublicContentDetail,
    PublicContentSummary,
)
from app.rag.embeddings import Embedder
from app.rag.retrieval import retrieve
from app.rag.synthesis import SYSTEM_PROMPT, ChatLLM, dedupe_citations
from app.routes.deps import (
    get_chat_llm,
    get_embedder,
    get_latency_tracker,
    get_rate_limiter,
    get_session,
    get_settings,
)
from app.routes.metrics import LatencyTracker, observe_and_maybe_log_chat_latency
from app.routes.ratelimit import RateLimiter
from app.routes.sse import sse_event, sse_response
from app.services import content as content_service
from app.services.chat import (
    get_or_create_session,
    record_assistant_message,
    record_user_message,
    set_message_feedback,
)
from app.services.errors import AppError
from app.services.tags import tags_for_contents

logger = logging.getLogger(__name__)

# `POST /public/chat`'s one SSE error code — deliberately generic and fixed (CONVENTIONS.md §4 /
# `app.rag.embeddings.OpenAICompatibleEmbedder`'s own precedent): the raw exception detail behind
# an LLM failure is logged for operators, never placed in the client-facing envelope, regardless
# of whether it came from the real `OpenAICompatibleChatLLM` or (in tests) a fake.
_CHAT_STREAM_ERROR_CODE = "chat_synthesis_failed"
_CHAT_STREAM_ERROR_MESSAGE = "The assistant failed to generate a response. Please try again."

# Fix round 1, finding I-2: the exact prefix `app.routes.sse.sse_event("token", ...)` always
# produces — `public_chat`'s `_on_first_event` hook below uses this to recognize a genuine first
# `token` event (and only that) among the first SSE block `sse_response` hands it, which may
# instead be an `error` block on the failure path.
_FIRST_TOKEN_EVENT_PREFIX = "event: token\n"

# No 401 (unlike `app.routes.content_routes.router`): these routes are
# unauthenticated by design. 422 is over-declared on the whole router for
# simplicity, mirroring `content_routes.py`'s same trade-off, even though
# `public_content_list` takes no request fields that could ever 422.
router = APIRouter(responses={422: {"model": ErrorEnvelope}})

# Only the by-slug route can raise `NotFoundError` — merged onto that route
# alone via FastAPI's router-then-route `responses` merge.
_DETAIL_RESPONSES: dict[int | str, dict[str, object]] = {404: {"model": ErrorEnvelope}}

# Same shape as `_DETAIL_RESPONSES`, declared separately for `public_chat_feedback` (phase-9
# task-02) — its own `NotFoundError` case (an unknown or `role='user'` `message_id`).
_FEEDBACK_RESPONSES: dict[int | str, dict[str, object]] = {404: {"model": ErrorEnvelope}}


def _to_summary(content: Content, tags: list[str]) -> PublicContentSummary:
    """Build a `PublicContentSummary` from a published `Content` row plus its resolved tags."""
    return PublicContentSummary(
        title=content.title,
        slug=content.slug,
        tags=tags,
        # `Content.published_at` is `Mapped[datetime | None]` in general, but
        # every row this route ever sees has `status == 'published'`
        # (`content_service.list_published_content`'s own filter) — and
        # `publish_content` always sets `status` and `published_at`
        # together (`app/services/content.py`) — so it is never `None`
        # here. Mirrors `content_routes.py::_to_content_response`'s
        # `cast(ContentStatus, content.status)`: a DB-shape runtime
        # guarantee made static once, at the one place it matters.
        published_at=cast(datetime, content.published_at),
    )


@router.get(
    "/public/content",
    operation_id="public_content_list",
    response_model=list[PublicContentSummary],
)
def public_content_list(session: Session = Depends(get_session)) -> list[PublicContentSummary]:
    """PRD §5.3: published-and-non-deleted content, newest-published first, tags included.

    Bare list, no pagination envelope — test-author-resolved,
    controller-approved (mirrors `GET /tags`'s bare `list[TagWithCount]`
    shape; task-03 test-author report ambiguity #1).
    """
    items = content_service.list_published_content(session)
    tag_names_by_id = tags_for_contents(session, [item.id for item in items])
    return [_to_summary(item, tag_names_by_id[item.id]) for item in items]


@router.get(
    "/public/content/{slug}",
    operation_id="public_content_get",
    response_model=PublicContentDetail,
    responses=_DETAIL_RESPONSES,
)
def public_content_get(slug: str, session: Session = Depends(get_session)) -> PublicContentDetail:
    """PRD §5.3: by-slug detail for a published-and-non-deleted item (404 otherwise).

    A draft/archived item's slug, a soft-deleted (still `status='published'`)
    item's slug, and a slug that never existed all 404 the same way — see
    `content_service.get_published_by_slug`'s §9 pin.
    """
    content = content_service.get_published_by_slug(session, slug)
    tags = tags_for_contents(session, [content.id])[content.id]
    return PublicContentDetail(
        title=content.title,
        slug=content.slug,
        body_md=content.body_md,
        tags=tags,
        published_at=cast(datetime, content.published_at),
    )


def _generate_chat_stream(
    session: Session,
    chat_llm: ChatLLM,
    embedder: Embedder,
    settings: Settings,
    body: ChatRequest,
    *,
    started_at: float,
) -> Iterator[str]:
    """Yield the §5.3 SSE body for one `/public/chat` exchange (PRD §7.6-§7.7, §4).

    Success order: one or more `token` events, then exactly one `citations` event, then exactly
    one `done` event. On ANY failure anywhere in the exchange — a DB error creating the session,
    the embedding provider call inside `retrieve()`, or the chat-completion call itself, at
    request time or mid-stream — whatever `token` events already went out, then exactly one
    `error` event and nothing further (CONVENTIONS.md §4's outermost-SSE-generator carve-out:
    a manually-built §9 envelope, since a 200 has already been sent by the time any of this can
    fail and `register_error_handlers` can no longer run). Review round 1, finding I-1: the ENTIRE
    body below — not just the `chat_llm.stream_answer` loop — lives inside the one `try`, so a
    pre-token failure (the single most likely real-world case: the embedding provider rejecting a
    rotated/expired `NVIDIA_API_KEY`) also produces this `error` event instead of an unhandled
    `RuntimeError: Caught handled exception, but response already started.` and a dead connection.

    The user's message is persisted and COMMITTED right after it's written — not just flushed —
    before retrieval/synthesis ever runs. Two independent reasons: (1) PRD §9 error handling — the
    user's message must survive any failure that happens after this point, and (2) `created_at`'s
    server default is Postgres' TRANSACTION timestamp (`now()` == `transaction_timestamp()`,
    constant for the whole transaction — see `app.services.content.list_content`'s own
    `created_at`-tie comment for the same fact in a different context). Without committing here,
    the user row and the assistant row written after streaming completes would land in the SAME
    transaction and get the exact same `created_at`, leaving `tests/test_public_chat.py`'s plain
    `ORDER BY created_at` (the column carries no tiebreaker on its own, unlike `list_content`'s
    `.id.desc()` fallback) genuinely nondeterministic between the two rows. The assistant row is
    committed the same way, immediately after it's written (review round 1, finding M-6) — so a
    `done` event is never sent for a row that turned out not to survive a commit failure, and
    `record_assistant_message`'s own `flush()` is never redundantly repeated here. Neither commit
    violates CONVENTIONS.md §3 ("services never commit") — `app.services.chat`'s functions still
    only `flush()`; both commits live in the route layer, which already owns the transaction
    boundary for this request (`app.routes.deps.get_session` normally owns it alone, but a route
    is free to commit early when it has a documented reason to, same as it would be free to for
    any other request).

    WR-09 (phase-6 remediation, task-08): a THIRD commit, right after `retrieve()` returns and
    before the `chat_llm.stream_answer(...)` loop begins. `retrieve()`'s own read-only
    `session.execute(select(...))` runs on this same session AFTER the user-message commit above
    already closed that transaction — SQLAlchemy's autobegin silently opens a brand-new
    transaction for that SELECT, and nothing had ever closed it again until the assistant-message
    commit below, meaning it stayed open for the ENTIRE (potentially slow, network-bound) LLM
    stream. Committing here releases it immediately once retrieval is done, before the stream
    loop can hold it open. It is a plain commit with no pending writes (nothing is written between
    `retrieve()` returning and this line), so it changes no persisted data and does not disturb the
    user-row-before-assistant-row `created_at` ordering above: the assistant row's write and commit
    still happen only after the stream completes, in their own (fourth) transaction.

    On the error path, the `error` event is yielded BEFORE `session.rollback()` runs (review
    round 2, finding N-1 — reordered from round 1's rollback-then-yield): probe RR-P7 showed that
    if the rollback itself raises — reachable exactly when the DB is the thing that failed, i.e.
    one of the failure classes I-1 widened this `try` to cover — a rollback-first ordering lets
    that second exception escape the generator and reproduces I-1's original failure mode (a dead
    connection with no `error` event ever sent). The client's envelope must never depend on the
    health of a connection that just failed, so the rollback is now purely a best-effort cleanup
    AFTER the response body is already complete: it runs inside its own `try/except`, logs on
    failure, and never raises into the stream.

    `started_at` (phase-9 DESIGN §A) is `public_chat`'s own `_start = time.monotonic()`, threaded
    in keyword-only so this stays a required, explicit argument rather than a second silent clock
    read: `latency_ms = int((time.monotonic() - started_at) * 1000)` is computed immediately
    before `record_assistant_message`, giving whole-answer latency (deliberately not
    time-to-first-token, which `_on_first_event` already tracks separately) — populated on every
    successful exchange and left `NULL` on the error path, since no assistant row is ever written
    there.
    """
    chat_session_id: uuid.UUID | None = None
    tokens: list[str] = []
    try:
        chat_session = get_or_create_session(session, body.session_id)
        chat_session_id = chat_session.id
        record_user_message(session, chat_session.id, body.message)
        session.commit()

        retrieval = retrieve(
            session, embedder, body.message, threshold=settings.similarity_threshold
        )
        # WR-09: release the transaction `retrieve()`'s SELECT just (auto-)opened — see docstring
        # above — before entering the stream loop, instead of holding it open across the whole
        # (potentially slow) LLM stream.
        session.commit()

        for token in chat_llm.stream_answer(SYSTEM_PROMPT, body.message, retrieval.chunks):
            tokens.append(token)
            yield sse_event("token", {"text": token})

        answer_text = "".join(tokens)
        # Phase-9 DESIGN §A: whole-answer latency, deliberately not time-to-first-token (which
        # `_on_first_event` already tracks separately under the "public_chat" metric key).
        latency_ms = int((time.monotonic() - started_at) * 1000)
        assistant_message = record_assistant_message(
            session, chat_session.id, answer_text, retrieval, latency_ms=latency_ms
        )
        session.commit()

        # PRD §4 citation asymmetry, wire half: deduped to content level (§5.3) right here, right
        # before it goes over the wire — the DB row just written above kept the chunk-level shape
        # (`app.services.chat.record_assistant_message`'s own comment is the other half).
        citations = dedupe_citations(retrieval.chunks)
        yield sse_event("citations", {"citations": citations})
        yield sse_event(
            "done", {"session_id": str(chat_session.id), "message_id": str(assistant_message.id)}
        )
    except Exception as exc:
        # Broad by design (CONVENTIONS.md §4 carve-out): this must catch anything raised anywhere
        # in the exchange above — a DB error, `EmbeddingFailedError` from `retrieve()`, the real
        # `ChatCompletionFailedError`, or (in tests) a fake's own exception type. Review round 1,
        # finding M-7: when the exception is a typed `AppError` (real production failures always
        # are — `EmbeddingFailedError`/`ChatCompletionFailedError` both carry a `.code`), that code
        # reaches the wire instead of being silently discarded; anything else (e.g. a test
        # double's plain `RuntimeError`) falls back to the generic code below. The MESSAGE is
        # always the fixed, generic string, regardless — raw provider/DB detail is logged for
        # operators, never enveloped.
        logger.warning("chat stream failed for session %s: %s", chat_session_id, exc)
        code = exc.code if isinstance(exc, AppError) else _CHAT_STREAM_ERROR_CODE
        yield sse_event("error", {"error": {"code": code, "message": _CHAT_STREAM_ERROR_MESSAGE}})
        # Review round 2, finding N-1: rollback is best-effort cleanup that runs AFTER the error
        # event is already on the wire, in its own try/except — a rollback failure (only
        # reachable when the DB itself is what failed) must never escape into the stream and
        # revert to I-1's original symptom (a dead connection, no `error` event ever sent).
        try:
            session.rollback()
        except Exception as rollback_exc:
            logger.warning(
                "session.rollback() failed after chat stream failure for session %s: %s",
                chat_session_id,
                rollback_exc,
            )
        return


@router.post(
    "/public/chat",
    operation_id="public_chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "SSE stream (PRD §5.3): `token` (repeated), `citations`, `done` on success, or "
                "`error` on failure."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        429: {"model": ErrorEnvelope},
    },
)
def public_chat(
    request: Request,
    body: ChatRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    chat_llm: ChatLLM = Depends(get_chat_llm),
    embedder: Embedder = Depends(get_embedder),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    latency_tracker: LatencyTracker = Depends(get_latency_tracker),
) -> StreamingResponse:
    """PRD §5.3: retrieval -> grounded synthesis -> typed SSE stream -> persistence.

    Rate limiting (task-03, PRD §9) is checked right here, first, before `chat_llm`/`embedder` are
    ever touched and before `_generate_chat_stream` builds any part of the SSE body — the task
    brief's wiring-order pin. A breach raises `RateLimitedError` (no `try/except` here, per
    CONVENTIONS.md §4: it propagates straight to `register_error_handlers`'s 429 mapping), so a
    rejected request never reaches retrieval or the LLM, and the client sees a plain
    `application/json` 429 envelope — never a started SSE stream.

    `429: {"model": ErrorEnvelope}` is declared honestly in this route's own `responses=` above
    (task-03 brief) rather than left undeclared, since a rate-limit rejection is now a real,
    expected outcome of calling this endpoint, not an edge case worth hiding from the OpenAPI
    export both frontend codegens read.

    Review round 1, finding C-1: PRD §5.3 says a `session_id` that is absent **or unknown** both
    mint a session "subject to the per-IP creation cap" — gating the create cap purely on
    `body.session_id is None` (round 0) let a client bypass `SESSION_CREATE_PER_DAY` (and, since
    `check_message`'s per-day cap was keyed on the client-supplied string, `RATE_LIMIT_PER_DAY`
    too) by sending any syntactically-valid-but-never-issued UUID. `session.get(ChatSession, ...)`
    below is a single indexed **read-only** primary-key lookup — it mints nothing and starts no
    stream, so it does not violate the wiring-order pin (whose purpose is "nothing minted, no
    stream started before the checks pass" — the pin's own wording, task brief lines 45-46); it
    only tells this route what `get_or_create_session` (called later, inside the generator) is
    about to do. `will_mint` is then the single source of truth PRD §5.3 actually specifies:
    "absent or unknown", not "absent".

    The §9 caps: `RATE_LIMIT_PER_MIN` (sliding one-minute window, per IP, always checked) and
    `RATE_LIMIT_PER_DAY` (per session, checked only once a real, KNOWN session exists) both live
    behind `rate_limiter.check_message` — keyed on `existing_session.id` (the resolved row), never
    on the raw, unverified `body.session_id`, so an unknown id can no longer smuggle itself into a
    per-day bucket nobody will ever charge again either. `SESSION_CREATE_PER_DAY` (per IP) is a
    separate gate, `rate_limiter.reserve_session_create` (review round 1, finding I-1: an atomic
    check-and-record in one lock acquisition — the two-step `check_session_create`/
    `note_session_created` pair the brief's Interfaces block names is still `RateLimiter`'s public
    surface for the pinned unit tests, but calling it as two separate steps here left a
    check-then-act race a concurrency probe measured concretely: 32 concurrent minters against a
    cap of 5 all admitted. `reserve_session_create` closes that window), called only when
    `will_mint` is true — and, deliberately, called AFTER `check_message`, not before (review
    round 1, finding M-4's own counter-example: mutating the route to record a create BEFORE
    `check_message` lets a per-minute-rejected request still burn a create slot for a request that
    was never going to be admitted at all; ordering `reserve_session_create` last means a
    create-cap charge only ever happens for a request `check_message` has already accepted). The
    one accepted asymmetry from that ordering: if the create cap turns out to be the thing that
    rejects, the per-minute (and, for a resumed-but-unknown-turned-known-nonexistent case, per-day)
    slot `check_message` already recorded for this same request is not refunded — the same
    "admission burns budget, not eventual success" trade-off `check_message`'s own admit-then-fail
    path already accepts (`app.routes.ratelimit`'s module docstring; probe P-K in the review
    report measured the analogous case for a mid-stream failure after admission).

    See `_generate_chat_stream` for the full event-order/persistence contract once a request is
    admitted; it repeats the identical `get_or_create_session(session, body.session_id)` PK lookup
    this route just did — accepted duplication (one cheap, indexed read) rather than threading the
    already-resolved `ChatSession` through the generator's signature for what is otherwise a
    single extra `SELECT`.

    Review round 1, finding M-2: without `response_class=StreamingResponse` +
    the explicit `200` `responses=` content override above, FastAPI's OpenAPI export defaults to
    an empty-schema `application/json` entry for this status (its generic default-`response_class`
    behavior, since this route sets no `response_model`) — wrong for an endpoint that only ever
    returns `text/event-stream`. `response_class=StreamingResponse` alone suppresses that default
    (`StreamingResponse.media_type` is `None` at the class level, so FastAPI's auto-schema branch
    never fires); the `responses=` override then supplies the real media type both frontend
    codegens read.
    """
    # Phase-6 task-01 (PRD §9.1) first-token latency. NOT documented in this function's own
    # docstring (deliberately — that docstring's TEXT is FastAPI's own OpenAPI `description` for
    # this route, and the §5 surface is frozen; a comment here changes no wire-visible baseline).
    # `_start` is captured before either rate-limit check, so a rejected request (which never
    # reaches `sse_response`/`_on_first_event` at all) never skews the metric — the reference
    # point is meant to reflect what a client actually experiences waiting for its first byte of
    # answer, not just the retrieval/synthesis portion. `_on_first_event` (passed to
    # `sse_response` below) fires once, right before `_generate_chat_stream`'s first SSE block is
    # yielded (`app.routes.sse`'s own docstring), and is passed that first block's raw formatted
    # text. Fix round 1, finding I-2: only a genuine `token` event records anything — a stream
    # whose first (and, on the failure path, only) block is an `error` event no longer lands a
    # sample in the reserved "public_chat" first-TOKEN bucket, which PRD §9.1 defines as
    # time-to-first-token specifically, not time-to-first-SSE-block-of-any-kind. A refusal (no
    # matching content) is unaffected: `_generate_chat_stream` still streams real `token` events
    # for a refusal, so it still belongs in the metric. When it does fire, it records the elapsed
    # time under `app.state.latency_tracker`'s reserved `"public_chat"` key, logging the greppable
    # `chat_latency ...` line every 100 samples (`app.routes.metrics.
    # observe_and_maybe_log_chat_latency`, §9.1's phase-7-consumed metric).
    _start = time.monotonic()

    def _on_first_event(first_item: str) -> None:
        if not first_item.startswith(_FIRST_TOKEN_EVENT_PREFIX):
            return
        observe_and_maybe_log_chat_latency(latency_tracker, time.monotonic() - _start)

    client_ip = request.client.host if request.client is not None else "unknown"

    existing_session = (
        session.get(ChatSession, body.session_id) if body.session_id is not None else None
    )
    will_mint = existing_session is None

    rate_limiter.check_message(
        client_ip, str(existing_session.id) if existing_session is not None else None
    )

    if will_mint:
        rate_limiter.reserve_session_create(client_ip)

    return sse_response(
        _generate_chat_stream(session, chat_llm, embedder, settings, body, started_at=_start),
        on_first_event=_on_first_event,
    )


@router.post(
    "/public/chat/{message_id}/feedback",
    operation_id="public_chat_feedback",
    status_code=204,
    responses=_FEEDBACK_RESPONSES,
)
def public_chat_feedback(
    message_id: uuid.UUID,
    body: ChatFeedbackRequest,
    session: Session = Depends(get_session),
) -> Response:
    """PRD §5.3 surface, phase-9 DESIGN §A: record 👍/👎 on one assistant answer.

    Unauthenticated like every other route in this module; the `message_id` from the `done` SSE
    event is the only capability required. Not rate-limited — see the ruling below.

    Ruling — rate limiting (decide-and-justify, per the task brief): NOT rate-limited.
    `rate_limiter.check_message` is the wrong instrument: it charges the per-minute *chat* bucket
    (`RATE_LIMIT_PER_MIN=10`) and a per-day *session* bucket, so ten thumb clicks would deny the
    user's own next question — a self-inflicted denial of service on the demo's most-clicked
    control. The endpoint is also cheap and un-enumerable: one indexed PK lookup plus a
    one-column UPDATE, addressed by a server-minted UUIDv4 the caller must already possess,
    writing a value constrained to ±1 by both Pydantic and the DB CHECK, and creating no rows.
    The blast radius of abuse is "someone flips their own answer's rating repeatedly", which the
    last-write-wins semantics already absorb. If replay traffic (task 18) or prod logs ever show
    abuse, the follow-up is a *separate* cheap per-IP counter on `RateLimiter`, never sharing the
    chat buckets — recorded as a controller-visible decision, not deferred silently.
    """
    set_message_feedback(session, message_id, body.value)
    return Response(status_code=204)
