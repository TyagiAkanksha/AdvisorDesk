"""Failing (RED) tests for the hand-rolled agent loop (task-03 Step 1).

Task brief: docs/plans/phase-5-mcp-agent/task-03-agent-loop-endpoint.md, Step 1.
Spec: advisordesk-prd.md §6 "Agent loop" (cap-of-8 with honest partial-completion reporting;
error-once self-correction then graceful failure; the draft rule; system-prompt intent), §11
row 7 (hand-rolled tool loop — no LangChain/LlamaIndex).

`app.agent.loop` does not exist yet: every test below is expected to fail at collection
(`ModuleNotFoundError`) until the implementer (a separate agent) creates it — that failure IS
the RED evidence this file exists to produce.

Naming decision (controller-flagged `Done`/`Done` namespace collision, task brief amendment):
`LlmStep`'s completion member is exported as `LlmDone` here — `AgentEvent`'s completion member
keeps the plain name `Done`, since it is the more externally-visible type (constructed directly
by `tests/test_agent_endpoint.py`, and eventually by the SSE route). `TextDelta`/`ToolCallStep`
(the `LlmStep` union) and `Token`/`ToolCall`/`ToolResult`/`Error` (the `AgentEvent` union) are
the controller's fixed names, imported verbatim; `LlmStep`/`AgentEvent` are the two union type
aliases the controller pin also names.

Everything here calls `run_agent` directly against a real `db_session` and the real
`app.mcp.runtime.call_tool` seam (no HTTP) — mirrors `tests/test_mcp_write_tools.py`'s own
"go through the real tool seam, seed rows via `app.services.content` directly" style — with a
scripted `FakeAgentLLM` standing in for the real provider. `FakeAgentLLM` is INDEX-based, not
reactive to `messages`/`tool_schemas` content: `next_step` simply pops the next `LlmStep` off a
fixed, caller-supplied script and records every `(messages, tool_schemas)` call it received, in
order — the exact mechanism the error-feedback-verbatim and pipeline-threading pins below read
back.

Judgment calls (test-author, flagged for controller review — see individual test docstrings for
the full reasoning):
  1. On a tool-call attempt, the loop emits `ToolCall` whether or not the call succeeds — only a
     SUCCESSFUL call additionally emits `ToolResult` and is counted toward `Done.tool_calls`.
     Pinned by `test_tool_error_self_correction_...`/`test_two_consecutive_tool_failures_...`.
  2. `Done.tool_calls` / `Error.code` shapes: `Done.tool_calls` is `list[dict]`, one
     `{"tool","arguments","result_summary"}` per completed call — the exact §5.4 wire shape,
     so the SSE route can serialize it with no further transformation. `Error.code` propagates
     the underlying `AppError.code` verbatim (mirrors `app.routes.public_routes`'s own
     "typed AppError code reaches the wire" precedent, finding M-7).
  3. The cap (§6: "8 tool calls per request") counts only SUCCESSFUL calls in this file's own
     cap test (which never exercises a failure) — this file takes no position on whether a
     failed attempt also burns a cap slot; that corner case is left to the implementer/reviewer.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL`
is set, and are skipped by fixture name otherwise (`tests/conftest.py`) — every test here
requests `db_session`, so the whole module skips cleanly without a DB.
"""

from __future__ import annotations

import copy
import inspect
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from app.agent.loop import (
    SYSTEM_PROMPT,
    AgentEvent,
    Done,
    Error,
    LlmDone,
    LlmStep,
    TextDelta,
    Token,
    ToolCall,
    ToolCallStep,
    ToolResult,
    run_agent,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Content, User
from app.services import content as content_service
from app.services.lifecycle import NoopChunkPipeline

# ---------------------------------------------------------------------------
# Fakes: scripted `AgentLLM` + recording `ChunkPipeline` (defined locally, no
# cross-test-file imports, per repo convention — `RecordingChunkPipeline` is a
# field-for-field mirror of `tests/test_mcp_write_tools.py::RecordingChunkPipeline`).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedLlmCall:
    """One recorded `FakeAgentLLM.next_step` call.

    `messages` is a DEEP COPY taken at call time — so later in-place mutation of the loop's own
    `messages` list (e.g. appending the next tool result) can't retroactively corrupt what was
    actually sent for THIS call, which is exactly what the error-feedback-verbatim and
    history-verbatim pins need to assert against.
    """

    messages: list[dict[str, Any]]
    tool_schema_names: tuple[str, ...]


@dataclass
class FakeAgentLLM:
    """Scripted, recording `AgentLLM` fake — index-based, NOT reactive to `messages`/`tool_schemas`.

    `next_step` pops `steps[len(calls)]` on every call and records the call FIRST — so a test can
    inspect `calls[N].messages` to see exactly what the loop sent back after a tool result or a
    tool error (the error-once / history-verbatim pins), independent of what the fake itself
    returns. Raises `AssertionError` (never a silent `IndexError` or a hang) if the loop asks for
    more steps than scripted: a clear signal of either a too-short test script or an
    implementation bug (e.g. a broken cap/termination check that keeps querying the model).
    """

    steps: list[LlmStep]
    calls: list[RecordedLlmCall] = field(default_factory=list)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.calls.append(
            RecordedLlmCall(
                messages=copy.deepcopy(messages),
                tool_schema_names=tuple(schema["name"] for schema in tool_schemas),
            )
        )
        if len(self.calls) > len(self.steps):
            raise AssertionError(
                f"FakeAgentLLM script exhausted after {len(self.steps)} steps but the loop "
                f"asked for step #{len(self.calls)} — either the test's script is too short, "
                "or the implementation is querying the model more times than expected "
                "(e.g. a cap/termination bug)."
            )
        return self.steps[len(self.calls) - 1]


@dataclass
class RecordingChunkPipeline:
    """Recording `ChunkPipeline` fake — field-for-field mirror of
    `tests/test_mcp_write_tools.py::RecordingChunkPipeline` (kept local, no cross-file import,
    per that file's own precedent)."""

    rebuild_return: int = 0
    remove_return: int = 0
    rebuild_calls: list[uuid.UUID] = field(default_factory=list)
    remove_calls: list[uuid.UUID] = field(default_factory=list)

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        self.rebuild_calls.append(content.id)
        return self.rebuild_return

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        self.remove_calls.append(content_id)
        return self.remove_return


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — mirrors `tests/test_mcp_write_tools.py::actor_id` (kept
    local, per that file's own no-cross-test-file-dependency precedent)."""
    user = User(email="agent-admin@example.com", name="Agent Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


def _event_names(events: list[AgentEvent]) -> list[str]:
    """Render an event list as class names, e.g. `["Token", "ToolCall", ...]` — compact,
    readable assertions on event ORDER without repeating `isinstance` checks everywhere."""
    return [type(event).__name__ for event in events]


# ---------------------------------------------------------------------------
# 1. Interface pin: `pipeline` is a REQUIRED keyword-only parameter (t02 amendment).
# ---------------------------------------------------------------------------


def test_run_agent_pipeline_parameter_is_required_keyword_only() -> None:
    """t02 amendment (controller pin): `run_agent`'s `pipeline` has no default and cannot be
    passed positionally — every caller (this file, the `/agent/chat` route) MUST supply a real
    `ChunkPipeline`, or agent-driven publish/edit/archive/delete would silently skip embedding
    work."""
    parameters = inspect.signature(run_agent).parameters
    assert "pipeline" in parameters
    pipeline_param = parameters["pipeline"]
    assert pipeline_param.kind == inspect.Parameter.KEYWORD_ONLY
    assert pipeline_param.default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# 2. Two-tool happy path: execution order + full `Done` summary (brief Step-1 bullet 1).
# ---------------------------------------------------------------------------


def test_two_tool_script_emits_events_in_execution_order_with_full_done_summary(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §6/§5.4: a two-tool script streams `token`/`tool_call`/`tool_result` events in
    execution order, terminating with one `Done` whose `tool_calls` lists both completed calls,
    each `{tool, arguments, result_summary}`, in the order they ran."""
    llm = FakeAgentLLM(
        steps=[
            TextDelta("I'll create the draft now. "),
            ToolCallStep(
                "create_draft",
                {"title": "Roth IRA Basics", "body_md": "content", "tags": ["retirement"]},
            ),
            TextDelta("Now checking the total count. "),
            ToolCallStep("count_content", {}),
            TextDelta("All done."),
            LlmDone(),
        ]
    )
    messages = [
        {
            "role": "user",
            "content": "Draft an article on Roth IRAs, then tell me the total content count.",
        }
    ]

    events = list(
        run_agent(
            messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=NoopChunkPipeline()
        )
    )

    assert _event_names(events) == [
        "Token",
        "ToolCall",
        "ToolResult",
        "Token",
        "ToolCall",
        "ToolResult",
        "Token",
        "Done",
    ]

    assert isinstance(events[0], Token)
    assert events[0].text == "I'll create the draft now. "
    assert isinstance(events[1], ToolCall)
    assert events[1].tool == "create_draft"
    assert events[1].arguments == {
        "title": "Roth IRA Basics",
        "body_md": "content",
        "tags": ["retirement"],
    }
    assert isinstance(events[2], ToolResult)
    assert events[2].tool == "create_draft"
    assert "roth-ira-basics" in events[2].result_summary
    assert isinstance(events[3], Token)
    assert events[3].text == "Now checking the total count. "
    assert isinstance(events[4], ToolCall)
    assert events[4].tool == "count_content"
    assert events[4].arguments == {}
    assert isinstance(events[5], ToolResult)
    assert "1" in events[5].result_summary
    assert isinstance(events[6], Token)
    assert events[6].text == "All done."

    done = events[7]
    assert isinstance(done, Done)
    assert len(done.tool_calls) == 2
    assert done.tool_calls[0]["tool"] == "create_draft"
    assert done.tool_calls[0]["arguments"] == {
        "title": "Roth IRA Basics",
        "body_md": "content",
        "tags": ["retirement"],
    }
    assert "roth-ira-basics" in done.tool_calls[0]["result_summary"]
    assert done.tool_calls[1]["tool"] == "count_content"
    assert done.tool_calls[1]["arguments"] == {}
    assert "1" in done.tool_calls[1]["result_summary"]

    # Interface pin: the LLM is offered every registered tool's schema, by name.
    assert "create_draft" in llm.calls[0].tool_schema_names
    assert "count_content" in llm.calls[0].tool_schema_names

    content = db_session.execute(
        select(Content).where(Content.slug == "roth-ira-basics")
    ).scalar_one()
    assert content.status == "draft"


# ---------------------------------------------------------------------------
# 3. Cap-of-8 pin (brief Step-1 bullet 2; PRD §6 verbatim).
# ---------------------------------------------------------------------------


def test_cap_stops_after_eight_tool_calls_with_honest_partial_report(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §6 cap-of-8 pin (verbatim): a script demanding 9 tool calls executes exactly 8 — the
    loop stops itself WITHOUT ever asking the model for a 9th step — and the final text names
    the completed count and tells the user to re-run for the remainder."""
    steps: list[LlmStep] = [
        ToolCallStep("create_draft", {"title": f"Cap Test Article {i}"}) for i in range(1, 10)
    ]
    llm = FakeAgentLLM(steps=steps)
    messages = [
        {"role": "user", "content": "Create nine draft articles named Cap Test Article 1 to 9."}
    ]
    pipeline = RecordingChunkPipeline()

    events = list(
        run_agent(messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=pipeline)
    )

    assert len(llm.calls) == 8, "the loop must stop BEFORE asking for a 9th step"
    tool_call_events = [e for e in events if isinstance(e, ToolCall)]
    tool_result_events = [e for e in events if isinstance(e, ToolResult)]
    assert len(tool_call_events) == 8
    assert len(tool_result_events) == 8

    created = (
        db_session.execute(select(Content).where(Content.title.like("Cap Test Article%")))
        .scalars()
        .all()
    )
    assert len(created) == 8

    assert isinstance(events[-1], Done)
    assert len(events[-1].tool_calls) == 8

    final_text = "".join(e.text for e in events if isinstance(e, Token))
    assert "8" in final_text, final_text
    assert re.search(r"re-run|rerun|run again|try again", final_text, re.I), final_text


# ---------------------------------------------------------------------------
# 4. Error-once self-correction pin, part (a) (brief Step-1 bullet 3; PRD §6 verbatim).
# ---------------------------------------------------------------------------


def test_tool_error_self_correction_feeds_message_verbatim_then_succeeds(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §6 error-once pin: the FIRST tool failure is surfaced to the model for
    self-correction — the probe-derived pin: the NEXT `next_step` call's `messages` must carry
    the structured tool error VERBATIM, including the offending field name
    (`app.mcp.runtime._format_validation_error`'s `"field: message"` shape) — never a generic
    or paraphrased string. A corrected retry then succeeds.

    Judgment call (see module docstring #1): `ToolCall` fires for BOTH the failed attempt and
    the corrected retry (the attempt is shown even though it didn't succeed); only the
    successful retry additionally emits `ToolResult` and lands in `Done.tool_calls`.
    """
    llm = FakeAgentLLM(
        steps=[
            ToolCallStep("create_draft", {"title": "Roth IRA Basics", "tagz": ["tax-planning"]}),
            ToolCallStep("create_draft", {"title": "Roth IRA Basics", "tags": ["tax-planning"]}),
            LlmDone(),
        ]
    )
    messages = [{"role": "user", "content": "Draft an article on Roth IRAs tagged tax-planning."}]

    events = list(
        run_agent(
            messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=NoopChunkPipeline()
        )
    )

    assert len(llm.calls) == 3
    # The SECOND call's messages carry the first failure's error text verbatim, field name
    # included ("tagz", the offending field) — not a paraphrase.
    second_call_text = str(llm.calls[1].messages)
    assert "tagz" in second_call_text
    assert "Extra inputs are not permitted" in second_call_text

    tool_call_events = [e for e in events if isinstance(e, ToolCall)]
    tool_result_events = [e for e in events if isinstance(e, ToolResult)]
    assert len(tool_call_events) == 2, "the attempt is shown for both the failed and retry calls"
    assert len(tool_result_events) == 1, "only the successful retry produces a result"
    assert "Error" not in _event_names(events), "graceful self-correction, not a hard failure"

    assert isinstance(events[-1], Done)
    assert len(events[-1].tool_calls) == 1
    assert events[-1].tool_calls[0]["tool"] == "create_draft"

    content = db_session.execute(
        select(Content).where(Content.title == "Roth IRA Basics")
    ).scalar_one()
    assert content.status == "draft"


# ---------------------------------------------------------------------------
# 5. Error-once self-correction pin, part (b) (brief Step-1 bullet 3; PRD §6 verbatim).
# ---------------------------------------------------------------------------


def test_two_consecutive_tool_failures_yield_error_event_and_stop(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §6: a second consecutive tool failure fails gracefully — one `Error` event, loop
    stops immediately (never silent, no `Done` event, no third model query)."""
    llm = FakeAgentLLM(
        steps=[
            ToolCallStep("create_draft", {"title": ""}),
            ToolCallStep("create_draft", {"title": ""}),
        ]
    )
    messages = [{"role": "user", "content": "Draft an article with an empty title, twice."}]

    events = list(
        run_agent(
            messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=NoopChunkPipeline()
        )
    )

    assert len(llm.calls) == 2, "the loop must stop after the SECOND failure, never ask a third"
    assert _event_names(events)[-1] == "Error"
    assert "Done" not in _event_names(events)

    error_event = events[-1]
    assert isinstance(error_event, Error)
    # Judgment call (see module docstring #2): the underlying `AppError.code` reaches the wire
    # verbatim, mirroring `app.routes.public_routes`'s own precedent (finding M-7).
    assert error_event.code == "tool_input_error"
    assert isinstance(error_event.message, str) and error_event.message

    assert db_session.execute(select(Content)).first() is None, "no partial row survives"


# ---------------------------------------------------------------------------
# 6. Draft rule (brief Step-1 bullet 4; PRD §6 verbatim).
# ---------------------------------------------------------------------------


def test_draft_rule_agent_never_calls_publish_leaves_status_draft(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §6 draft rule: drafting an article never auto-publishes — no `publish` tool call is
    ever emitted, and the created row stays `status='draft'`."""
    llm = FakeAgentLLM(
        steps=[
            TextDelta("Drafting that now. "),
            ToolCallStep(
                "create_draft", {"title": "529 Plans 101", "body_md": "A drafted article body."}
            ),
            TextDelta("Draft created."),
            LlmDone(),
        ]
    )
    messages = [{"role": "user", "content": "Draft an article about 529 plans."}]

    events = list(
        run_agent(
            messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=NoopChunkPipeline()
        )
    )

    called_tools = {e.tool for e in events if isinstance(e, ToolCall)}
    assert called_tools == {"create_draft"}
    assert "publish" not in called_tools

    content = db_session.execute(
        select(Content).where(Content.title == "529 Plans 101")
    ).scalar_one()
    assert content.status == "draft"


# ---------------------------------------------------------------------------
# 7. Pipeline threading pin (t02 amendment, controller pin).
# ---------------------------------------------------------------------------


def test_loop_threads_the_given_pipeline_into_call_tool_for_publish(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """t02 amendment: `run_agent` MUST thread its own `pipeline` argument into every
    `call_tool` call — publishing through the agent must run the SAME chunk-rebuild path the
    REST `POST /content/{id}/publish` route does, never silently defaulting to
    `NoopChunkPipeline`."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()
    llm = FakeAgentLLM(steps=[ToolCallStep("publish", {"content_id": str(draft.id)}), LlmDone()])
    messages = [{"role": "user", "content": "Please publish the Roth IRA Basics draft now."}]

    list(run_agent(messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=pipeline))

    assert pipeline.rebuild_calls == [draft.id]


# ---------------------------------------------------------------------------
# 8-9. System-prompt textual pins (probe-derived, 2026-08-01, both load-bearing).
# ---------------------------------------------------------------------------


def test_system_prompt_forbids_publishing_without_explicit_instruction() -> None:
    """Probe-derived pin: the system prompt must explicitly forbid publishing UNLESS the
    user's message explicitly instructs it (PRD §6: "Agent-created drafts are ALWAYS status
    draft — never auto-published unless the user explicitly instructs publishing").

    Keyword-based, not exact-wording (a judgment call — the PRD marks synthesis system-prompt
    wording "adjustable" elsewhere, and nothing here pins this one word-for-word): any
    reasonable phrasing of this rule must mention both concepts together.
    """
    lower = SYSTEM_PROMPT.lower()
    assert "publish" in lower
    assert "draft" in lower
    assert "explicit" in lower or "unless the user" in lower or "only if the user" in lower


def test_system_prompt_steers_capability_questions_away_from_tool_calls() -> None:
    """Probe-derived pin (2026-08-01): without this steering line, the pinned model over-calls
    tools under `tool_choice="auto"` even for plain capability/general questions — the system
    prompt must tell it to answer those in TEXT, with no tool call.

    Keyword-based (see the sibling test's docstring for why): checks both required ideas are
    present rather than pinning exact phrasing.
    """
    lower = SYSTEM_PROMPT.lower()
    assert "tool" in lower
    assert any(
        phrase in lower
        for phrase in ("capability", "general question", "what you can do", "without calling")
    )
