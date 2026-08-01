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
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Content
from app.models.schemas.chat import ChatRequest
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.public import PublicContentDetail, PublicContentSummary
from app.rag.embeddings import Embedder
from app.rag.retrieval import retrieve
from app.rag.synthesis import SYSTEM_PROMPT, ChatLLM, dedupe_citations
from app.routes.deps import get_chat_llm, get_embedder, get_session, get_settings
from app.routes.sse import sse_event, sse_response
from app.services import content as content_service
from app.services.chat import get_or_create_session, record_assistant_message, record_user_message
from app.services.errors import AppError
from app.services.tags import tags_for_contents

logger = logging.getLogger(__name__)

# `POST /public/chat`'s one SSE error code — deliberately generic and fixed (CONVENTIONS.md §4 /
# `app.rag.embeddings.OpenAICompatibleEmbedder`'s own precedent): the raw exception detail behind
# an LLM failure is logged for operators, never placed in the client-facing envelope, regardless
# of whether it came from the real `OpenAICompatibleChatLLM` or (in tests) a fake.
_CHAT_STREAM_ERROR_CODE = "chat_synthesis_failed"
_CHAT_STREAM_ERROR_MESSAGE = "The assistant failed to generate a response. Please try again."

# No 401 (unlike `app.routes.content_routes.router`): these routes are
# unauthenticated by design. 422 is over-declared on the whole router for
# simplicity, mirroring `content_routes.py`'s same trade-off, even though
# `public_content_list` takes no request fields that could ever 422.
router = APIRouter(responses={422: {"model": ErrorEnvelope}})

# Only the by-slug route can raise `NotFoundError` — merged onto that route
# alone via FastAPI's router-then-route `responses` merge.
_DETAIL_RESPONSES: dict[int | str, dict[str, object]] = {404: {"model": ErrorEnvelope}}


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
    any other request). On the error path, `session.rollback()` clears any partial state left by
    the failure before this generator returns — otherwise `get_session`'s own end-of-request
    `commit()` (which still runs: the exception is caught here, never re-raised) could itself
    raise on an already-poisoned transaction.
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

        for token in chat_llm.stream_answer(SYSTEM_PROMPT, body.message, retrieval.chunks):
            tokens.append(token)
            yield sse_event("token", {"text": token})

        answer_text = "".join(tokens)
        assistant_message = record_assistant_message(
            session, chat_session.id, answer_text, retrieval
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
        session.rollback()
        code = exc.code if isinstance(exc, AppError) else _CHAT_STREAM_ERROR_CODE
        yield sse_event("error", {"error": {"code": code, "message": _CHAT_STREAM_ERROR_MESSAGE}})
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
    },
)
def public_chat(
    body: ChatRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    chat_llm: ChatLLM = Depends(get_chat_llm),
    embedder: Embedder = Depends(get_embedder),
) -> StreamingResponse:
    """PRD §5.3: retrieval -> grounded synthesis -> typed SSE stream -> persistence.

    Rate-limit rejection (task-03) happens before this route ever runs (task brief's
    implementation note) — this route assumes every request that reaches it is allowed to
    proceed. See `_generate_chat_stream` for the full event-order/persistence contract.

    Review round 1, finding M-2: without `response_class=StreamingResponse` +
    the explicit `200` `responses=` content override above, FastAPI's OpenAPI export defaults to
    an empty-schema `application/json` entry for this status (its generic default-`response_class`
    behavior, since this route sets no `response_model`) — wrong for an endpoint that only ever
    returns `text/event-stream`. `response_class=StreamingResponse` alone suppresses that default
    (`StreamingResponse.media_type` is `None` at the class level, so FastAPI's auto-schema branch
    never fires); the `responses=` override then supplies the real media type both frontend
    codegens read.
    """
    return sse_response(_generate_chat_stream(session, chat_llm, embedder, settings, body))
