"""The hand-rolled agent loop: system prompt, event/step types, `run_agent` (PRD §6, §11 row 7).

`app.routes.agent_routes` (`POST /agent/chat`) is the only production caller — it wraps every
`AgentEvent` this module yields into an SSE block via `app.routes.sse.sse_event` (PRD §5.4's five
wire shapes map 1:1 onto `Token`/`ToolCall`/`ToolResult`/`Done`/`Error` below). The real
`AgentLLM` (`OpenAICompatibleAgentLLM`, PRD v1.5) lives in the sibling module `app.agent.llm` —
kept out of this one so `loop.py` (the orchestration seam every test in `tests/test_agent_loop.py`
exercises directly, no HTTP, no provider) never has to import the `openai` SDK at all; see
`app.agent.llm`'s module docstring for the full split rationale.

Naming (controller-fixed pin, task-03 brief + test-author report): `LlmStep`'s completion member
is `LlmDone`; `AgentEvent`'s completion member is the plain `Done` — `Done` is the more
externally-visible type (constructed/matched by both test files and this module's own SSE-facing
route), `LlmDone` is purely internal to the model-querying inner loop.

Fix round 1 (Opus review of commit e58f007, findings C-1/C-4/I-1): see `run_agent` for the
specifics of each — `json.dumps`-ing a synthesized tool call's `arguments` onto the wire (C-1),
committing/rolling back around each individual `call_tool` invocation instead of relying on one
trailing commit at the route layer (C-4), and counting the §6 cap against every ATTEMPTED tool
call, not just successful ones (I-1).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.mcp.runtime import call_tool, list_tool_schemas
from app.services.errors import AppError
from app.services.lifecycle import ChunkPipeline

__all__ = [
    "SYSTEM_PROMPT",
    "AgentEvent",
    "AgentLLM",
    "Done",
    "Error",
    "LlmDone",
    "LlmStep",
    "TextDelta",
    "Token",
    "ToolCall",
    "ToolCallStep",
    "ToolResult",
    "run_agent",
]

# PRD §6 "Agent loop" verbatim intent (wording adjustable, mirrors `app.rag.synthesis.
# SYSTEM_PROMPT`'s own "wording adjustable" precedent):
#   1. The assistant is a CMS operations agent for an authenticated admin, offered the MCP tool
#      schemas, operating on real content.
#   2. When asked to draft an article, write the body in this same turn and pass it to
#      `create_draft` — every agent-created draft is ALWAYS status `draft`, NEVER published
#      unless the user's message explicitly instructs publishing (probe-derived pin (a)).
#   3. Answer capability/general questions directly in text, with no tool call — only call a
#      tool to actually operate on CMS content (probe-derived pin (b), 2026-08-01: the pinned
#      model over-calls tools under `tool_choice="auto"` without this steering line).
#   4. Checkpoint fix (finding L-2): tag names are stored lowercase-hyphenated (PRD §4.1) — tell
#      the model to convert a conversational tag name into that form itself, both when tagging
#      content and when filtering by tag, rather than relying solely on the tool layer's own
#      normalization (`app.mcp.tools_read`) to paper over a mismatched filter.
SYSTEM_PROMPT = (
    "You are AdvisorDesk's CMS operations agent, working on behalf of an authenticated admin. "
    "You are given tools to search, create, edit, tag, publish, archive, delete, and count CMS "
    "content, plus a tool to report content gaps. Use a tool only when the user is asking you to "
    "actually operate on CMS content. For capability or general questions — 'what can you do', "
    "'how does this work', and similar — answer directly in text without calling any tool. "
    "When asked to draft an article, write the full article body yourself in this same turn and "
    "pass it to create_draft. Every draft you create is ALWAYS status 'draft' — never publish it "
    "unless the user's message explicitly instructs you to publish. Do not call the publish tool "
    "unless publishing was explicitly requested. Tag names are stored lowercase-hyphenated (e.g. "
    "'tax-planning') — convert a conversational tag name into that form when tagging content or "
    "filtering by tag."
)

# PRD §6 verbatim: "Cap: 8 tool calls per request."
_MAX_TOOL_CALLS = 8


# ---------------------------------------------------------------------------
# `LlmStep`: what `AgentLLM.next_step` returns, one step at a time.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextDelta:
    """The model produced a text fragment (not a tool call)."""

    text: str


@dataclass(frozen=True)
class ToolCallStep:
    """The model wants to call tool `name` with `arguments` (not yet validated/executed)."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LlmDone:
    """The model has no more text or tool calls to produce this turn — the exchange is over."""


LlmStep = TextDelta | ToolCallStep | LlmDone


class AgentLLM(Protocol):
    """The model-querying seam `run_agent` depends on.

    Structurally implemented by `app.agent.llm.OpenAICompatibleAgentLLM` (the real provider) and
    by each test file's own scripted `FakeAgentLLM` — a `Protocol`, not an ABC, so a test fake
    needs no inheritance relationship to satisfy it (mirrors `app.rag.synthesis.ChatLLM`'s shape).
    """

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        """Return the model's next step given the conversation so far.

        Args:
            messages: the full conversation so far, oldest first — a system message, then
                alternating user/assistant/tool turns `run_agent` has built up.
            tool_schemas: every registered tool's `{"name", "description", "inputSchema"}`
                (`app.mcp.runtime.list_tool_schemas()`'s own shape, passed through unchanged —
                an implementation adapts this into its own provider's wire format, e.g. OpenAI's
                `tools=[{"type":"function","function":{...}}]`).

        Returns:
            Exactly one `LlmStep` — a text fragment, one tool call to attempt, or "done".
        """
        ...


# ---------------------------------------------------------------------------
# `AgentEvent`: what `run_agent` yields — the PRD §5.4 wire shapes, one per SSE event.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    """A text fragment to stream to the client (§5.4 `event: token`)."""

    text: str


@dataclass(frozen=True)
class ToolCall:
    """A tool call was attempted (§5.4 `event: tool_call`) — fired on EVERY attempt, whether or
    not it ultimately succeeds, so the client sees what the agent tried."""

    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """A tool call SUCCEEDED (§5.4 `event: tool_result`) — only a successful attempt emits this."""

    tool: str
    result_summary: str


@dataclass(frozen=True)
class Done:
    """The exchange finished normally (§5.4 `event: done`).

    `tool_calls` is one `{"tool", "arguments", "result_summary"}` dict per successfully
    completed call, in execution order — the exact wire shape, so the SSE route serializes it
    with no further transformation.
    """

    tool_calls: list[dict[str, Any]]


@dataclass(frozen=True)
class Error:
    """The exchange failed gracefully (§5.4 `event: error`) — a second consecutive tool failure.

    `code` propagates the underlying `AppError.code` verbatim (mirrors `app.routes.public_routes`'
    own "typed AppError code reaches the wire" precedent) — `ToolInputError`'s message is
    deliberately safe to show (its own docstring), and the same judgment extends to its code.
    """

    code: str
    message: str


AgentEvent = Token | ToolCall | ToolResult | Done | Error


def _cap_report(completed: list[dict[str, Any]]) -> str:
    """Build the §6 cap-of-8 honest partial-completion report: what ran, and to re-run for more.

    The loop only knows what it itself completed this request — not the model's full original
    plan — so "which remain" is reported as "there may be more; re-run" rather than an itemized
    remainder list the loop has no way to know (judgment call, disclosed in the task-03 report).
    """
    tool_names = ", ".join(entry["tool"] for entry in completed)
    return (
        f"Reached the {_MAX_TOOL_CALLS}-tool-call limit for this request. Completed "
        f"{len(completed)} operation(s): {tool_names}. There may be more work left to do for "
        "this request — please re-run it to continue with the rest."
    )


def run_agent(
    messages: list[dict[str, Any]],
    *,
    llm: AgentLLM,
    session: Session,
    actor_id: uuid.UUID,
    pipeline: ChunkPipeline,
) -> Iterator[AgentEvent]:
    """Drive one stateless agent exchange (PRD §5.4, §6): query the model, execute tool calls.

    Builds its own working conversation — `SYSTEM_PROMPT` followed by `messages` verbatim (never
    mutating the caller's own list) — and repeatedly asks `llm.next_step` for the next step,
    reacting to it, until the model reports `LlmDone`, the §6 cap of 8 successful tool calls is
    reached, or a second CONSECUTIVE tool failure ends the exchange with a graceful `Error`.

    Every tool call runs through `app.mcp.runtime.call_tool` with `pipeline` threaded straight
    through (t02 amendment) — publishing/archiving/deleting/editing-a-published-item via the
    agent runs the SAME chunk-rebuild path the REST routes do, never silently a no-op.

    Args:
        messages: the client-resent conversation history, oldest first, last element the new
            user turn (PRD §5.4) — copied, never mutated.
        llm: the model-querying seam (`AgentLLM.next_step`).
        session: the caller's `Session` — every tool call runs through it, but each call now
            owns its own commit/rollback boundary (fix round 1, finding C-4), not one shared
            transaction for the whole exchange.
        actor_id: the authenticated admin driving this exchange (stamped on any write tool).
        pipeline: the `ChunkPipeline` every tool call threads through (required, keyword-only,
            no default — t02 amendment: a caller must supply a real pipeline or agent-driven
            publish/edit/archive/delete would silently skip embedding work).

    Yields:
        `AgentEvent`s in execution order: `Token`s for text, a `ToolCall` for every attempt (a
        `ToolResult` follows only if it succeeded), then exactly one final `Done` or `Error`.

    Transaction boundary (fix round 1, finding C-4): `session.commit()` runs immediately after
    each SUCCESSFUL `call_tool`, and `session.rollback()` immediately after each FAILED one —
    mirroring `app.mcp.server._execute_tool_call`'s per-call semantics, in-band with whether the
    call actually raised, never left for a single trailing commit at the route layer. Before
    this fix, one commit at the end of the whole exchange could commit a tool's partial write
    (e.g. `publish` flushing `status='published'` before `rebuild_chunks` raised
    `EmbeddingFailedError`) as if it had fully succeeded, while `done`/`error` honestly reported
    it hadn't — or roll back an EARLIER call's already-reported success just because a LATER
    call in the same exchange failed. Each tool call now keeps its own §4 transaction semantics
    regardless of which surface (REST, MCP, or this loop) drove it.
    """
    conversation: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *(dict(message) for message in messages),
    ]
    tool_schemas = list_tool_schemas()
    completed: list[dict[str, Any]] = []
    consecutive_failures = 0
    call_index = 0

    # Fix round 1, finding C-4: establish a clean transaction baseline before this exchange's
    # own per-call commit/rollback boundary begins. `session.rollback()` (below, on a failed
    # call) reverts the WHOLE current transaction, not just this attempt's own writes — without
    # this, a caller that had already flushed (but not committed) unrelated work onto the same
    # `session` before calling `run_agent` would lose it the moment this exchange's FIRST tool
    # call happened to fail, even though that failure did no writes of its own. In production
    # `get_session` hands `run_agent` a brand-new session with nothing pending, so this commits
    # an empty transaction (a no-op); it only matters for a caller (e.g. a test fixture) that
    # flushes setup data onto the same session first.
    session.commit()

    while True:
        step = llm.next_step(conversation, tool_schemas)

        if isinstance(step, TextDelta):
            conversation.append({"role": "assistant", "content": step.text})
            yield Token(step.text)
            continue

        if isinstance(step, LlmDone):
            yield Done(completed)
            return

        # step: ToolCallStep — record the attempt as an assistant tool-call turn before it runs,
        # so a subsequent `next_step` call (self-correction retry, or the very next step) sees a
        # self-consistent conversation regardless of what actually happened.
        call_index += 1
        tool_call_id = f"call_{call_index}"
        conversation.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": step.name,
                            # Fix round 1, finding C-1: the OpenAI wire protocol (and the real
                            # NVIDIA endpoint, live-verified 400) requires `arguments` to be a
                            # JSON-encoded STRING, not the raw dict `ToolCallStep.arguments`
                            # carries — every follow-up provider query failed until this was
                            # fixed. `app.agent.llm.OpenAICompatibleAgentLLM` mirrors this with
                            # its own `json.loads` when re-hydrating a queued parallel tool call.
                            "arguments": json.dumps(step.arguments),
                        },
                    }
                ],
            }
        )
        yield ToolCall(step.name, step.arguments)

        try:
            result = call_tool(
                step.name, step.arguments, session=session, actor_id=actor_id, pipeline=pipeline
            )
        except AppError as exc:
            # Fix round 1, finding C-4: roll back THIS call's (possibly partial) write
            # immediately — in-band with the failure, mirroring
            # `app.mcp.server._execute_tool_call`. Safe even when nothing was actually written
            # (e.g. a pure Pydantic validation `ToolInputError` before any handler ran) — an
            # empty rollback is a no-op.
            session.rollback()
            # PRD §6: "On a tool error, surface the error to the model once for self-correction,
            # then fail gracefully with an explanation." The error text is fed back VERBATIM
            # (probe-derived pin (2): the model self-corrects only when the field name and shape
            # are visible, not a paraphrase) — `str(exc)` is `ToolInputError`/`ToolNotFoundError`'s
            # own message, already safe to show (their docstrings).
            if consecutive_failures:
                yield Error(code=exc.code, message=str(exc))
                return
            consecutive_failures += 1
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": (
                        f"Tool call to '{step.name}' failed: {exc} "
                        "Correct the arguments and try again."
                    ),
                }
            )
            if call_index >= _MAX_TOOL_CALLS:
                # Fix round 1, finding I-1: the cap bounds ATTEMPTS (`call_index`), not
                # successes (`len(completed)`) — an alternating fail/succeed script previously
                # ran 16 tool executions (16 provider queries) against an "8 tool calls per
                # request" cap. This stops at exactly 8 attempts, full stop, regardless of how
                # many of them succeeded.
                report = _cap_report(completed)
                conversation.append({"role": "assistant", "content": report})
                yield Token(report)
                yield Done(completed)
                return
            continue

        # Fix round 1, finding C-4: commit THIS call's write immediately — never left pending
        # for a later iteration or a trailing route-level commit to (mis)handle. A LATER failure
        # in the same exchange can now never roll back an already-reported success.
        session.commit()
        consecutive_failures = 0
        summary = str(result)
        conversation.append({"role": "tool", "tool_call_id": tool_call_id, "content": summary})
        completed.append(
            {"tool": step.name, "arguments": step.arguments, "result_summary": summary}
        )
        yield ToolResult(step.name, summary)

        if call_index >= _MAX_TOOL_CALLS:
            # §6 cap pin (finding I-1: counts attempts via `call_index`, not successes) — stop
            # WITHOUT asking the model for another step — synthesize the honest
            # partial-completion report ourselves.
            report = _cap_report(completed)
            conversation.append({"role": "assistant", "content": report})
            yield Token(report)
            yield Done(completed)
            return
