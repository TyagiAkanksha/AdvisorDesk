"""`POST /agent/chat`: the stateless admin agent endpoint (PRD §5.4, §6, §12).

Reuses `app.routes.sse.sse_event`/`sse_response` verbatim (task-03 brief: "one SSE
implementation serves both chat endpoints") — the wire framing is identical to
`app.routes.public_routes.public_chat`'s, only the five event names/payloads differ (§5.4).

Mirrors `public_chat`'s own outermost-SSE-generator carve-out (CONVENTIONS.md §4): once the 200
has been sent, the only way to report a failure is a manually-built `error` event, since
`register_error_handlers` can no longer run for this request. `run_agent` (`app.agent.loop`)
already turns a graceful tool failure into an `Error` event internally (§6: "fail gracefully with
an explanation") — the `try/except` here exists for what `run_agent` does NOT swallow: a bug, or
a real provider failure from `app.agent.llm.OpenAICompatibleAgentLLM` (`AgentLLMFailedError`),
raised from inside `llm.next_step` while `run_agent`'s generator is being driven.

Statelessness (§5.4/§12): no `app.services.chat`/`ChatSession`/`ChatMessage` code is imported or
called anywhere in this module — there is nothing here that COULD write a chat row. Every
`session.commit()`/`session.rollback()` that runs for a request through this route lives inside
`run_agent` itself (fix round 1, finding C-4 — one commit/rollback per tool call, never a single
trailing commit here), and persists only whatever CMS content the agent's own tool calls produced
(`Content`/`Tag` rows), never a chat message.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.loop import AgentEvent, AgentLLM, Done, Token, ToolCall, ToolResult, run_agent
from app.auth.deps import AdminPrincipal, require_admin
from app.models.schemas.agent import AgentChatRequest
from app.models.schemas.common import ErrorEnvelope
from app.routes.deps import get_agent_llm, get_chunk_pipeline, get_session
from app.routes.sse import sse_event, sse_response
from app.services.errors import AppError
from app.services.lifecycle import ChunkPipeline

logger = logging.getLogger(__name__)

# `/agent/chat`'s one SSE error code for anything `run_agent` itself doesn't already turn into a
# graceful `Error` event (a bug, or a real provider failure) — mirrors `app.routes.public_routes`'
# `_CHAT_STREAM_ERROR_CODE`/`_CHAT_STREAM_ERROR_MESSAGE` fallback shape exactly.
_AGENT_STREAM_ERROR_CODE = "agent_stream_failed"
_AGENT_STREAM_ERROR_MESSAGE = "The agent failed to complete this request. Please try again."

router = APIRouter(responses={401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})


def _to_sse_event(event: AgentEvent) -> str:
    """Render one `AgentEvent` as its §5.4 SSE wire block — the loop's types map 1:1 onto it."""
    if isinstance(event, Token):
        return sse_event("token", {"text": event.text})
    if isinstance(event, ToolCall):
        return sse_event("tool_call", {"tool": event.tool, "arguments": event.arguments})
    if isinstance(event, ToolResult):
        return sse_event(
            "tool_result", {"tool": event.tool, "result_summary": event.result_summary}
        )
    if isinstance(event, Done):
        return sse_event("done", {"tool_calls": event.tool_calls})
    return sse_event("error", {"error": {"code": event.code, "message": event.message}})


def _generate_agent_stream(
    session: Session,
    llm: AgentLLM,
    pipeline: ChunkPipeline,
    actor_id: uuid.UUID,
    messages: list[dict[str, Any]],
) -> Iterator[str]:
    """Yield the §5.4 SSE body for one `/agent/chat` exchange.

    Fix round 1, finding C-4: the single TRAILING `session.commit()` this generator used to run
    after `run_agent` was fully exhausted is REMOVED — it was the actual bug. `run_agent` itself
    now commits after every SUCCESSFUL `call_tool` and rolls back after every FAILED one
    (mirroring `app.mcp.server._execute_tool_call`'s per-call transaction semantics), so a
    publish whose `rebuild_chunks` raised `EmbeddingFailedError` mid-exchange rolls back on the
    spot instead of riding this generator's own trailing commit to a
    published-with-zero-chunks row the SSE stream had just reported as NOT completed. Nothing is
    lost by removing it: every write in this whole request path originates from a `call_tool`
    call inside `run_agent`, and each one now owns its own commit/rollback boundary the instant
    it succeeds or fails — there is never anything left pending by the time `run_agent`'s
    generator is exhausted, whether it ended in `Done` or a graceful `Error`.

    On an exception escaping `run_agent` itself (a bug, or `AgentLLMFailedError` from the real
    provider seam), the `error` event is still yielded BEFORE `session.rollback()` runs — same
    ordering `public_chat._generate_chat_stream` uses and for the same reason: a rollback
    failure must never cost the client its `error` event. This `rollback()` is now purely
    defensive (every tool call already resolved its own transaction boundary by the time any
    exception could reach here) — kept as a safety net for a bug elsewhere, or any state left
    dirty on a path that isn't `run_agent`'s own tool-call loop.
    """
    try:
        for event in run_agent(
            messages, llm=llm, session=session, actor_id=actor_id, pipeline=pipeline
        ):
            yield _to_sse_event(event)
    except Exception as exc:
        logger.warning("agent chat stream failed for actor %s: %s", actor_id, exc)
        code = exc.code if isinstance(exc, AppError) else _AGENT_STREAM_ERROR_CODE
        yield sse_event("error", {"error": {"code": code, "message": _AGENT_STREAM_ERROR_MESSAGE}})
        try:
            session.rollback()
        except Exception as rollback_exc:
            logger.warning(
                "session.rollback() failed after agent stream failure for actor %s: %s",
                actor_id,
                rollback_exc,
            )
        return


@router.post(
    "/agent/chat",
    operation_id="agent_chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "SSE stream (PRD §5.4): `token`/`tool_call`/`tool_result` interleaved in "
                "execution order, then `done` on success or `error` on failure."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
    },
)
def agent_chat(
    body: AgentChatRequest,
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
    llm: AgentLLM = Depends(get_agent_llm),
    pipeline: ChunkPipeline = Depends(get_chunk_pipeline),
) -> StreamingResponse:
    """PRD §5.4: stateless agent exchange — resent history in, typed SSE tool-loop events out.

    `pipeline` is `app.state.chunk_pipeline` (t02 amendment, `get_chunk_pipeline`) — threaded
    straight into `run_agent`, so an agent-driven publish/archive/delete/edit-of-published runs
    the SAME chunk-rebuild path the REST `/content/{id}/...` routes do, never silently a no-op.
    """
    messages = [message.model_dump() for message in body.messages]
    return sse_response(_generate_agent_stream(session, llm, pipeline, principal.user_id, messages))
