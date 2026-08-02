"""Checkpoint fix, finding L-1: actionable `ToolInputError` messages (task-03 brief pin).

Live symptom: "Draft an article on Roth IRA conversion basics and tag it retirement" — the
pinned model (meta/llama-3.1-8b-instruct) calls `create_draft` with `tags` as the STRING
`"['retirement']"` (its known first-shot habit, task-03 brief). `call_tool`'s Pydantic
validation raised `ToolInputError`, and the loop's §6 one-retry self-correction fed the error
text back — but the PRE-FIX message was field-name-only (`"tags: Input should be a valid
list"`), and the model just repeated the same mistake, so the exchange died with a graceful
`Error` and no draft.

Probe-established fact (2026-08-01, ledger): the model reliably self-corrects ONLY when the
fed-back error shows the expected shape with a LITERAL example (e.g. `Pass a JSON array of
strings, e.g. ["retirement"]`) — a field-name-only message or a schema-description example both
fail. `app.mcp.runtime._format_validation_error` now appends a generic, annotation-derived
`"Expected <type>, e.g. <example>."` hint to every failing field (never special-cased to `tags`
alone — see that function's own docstring).

This file is NEW (not a pinned test file) — it does not modify any existing test.

Tests:
  (a) `test_list_field_rejection_message_is_actionable`: unit-pins the enriched message for a
      list-of-strings field (`create_draft`'s `tags`, given the model's actual string-repr
      mistake) — must name the field, indicate a list/array is expected, and show a bracketed
      literal example.
  (b) `test_int_field_rejection_message_is_actionable`: same shape, for an int field
      (`search_content`'s `limit="x"` — the exact case `tests/test_mcp_read_tools.py`'s pinned
      `test_search_content_bad_limit_raises_tool_input_error_naming_field` already names the
      field for; this test additionally pins the richer message that test doesn't check).
  (c) `test_agent_loop_self_corrects_string_repr_tags_into_real_list`: loop-level integration —
      a scripted `FakeAgentLLM` that mimics the pinned model's actual live behavior: first
      `create_draft` with `tags` as a string-repr, then (having received an error message
      containing a bracketed example) retries with a real list. Asserts the loop ends in
      `Done` with the draft actually created — this locks the WHOLE chain the live failure
      traversed (`run_agent` -> `call_tool` -> `_format_validation_error` -> fed back verbatim
      -> model retries -> `call_tool` succeeds).

CONVENTIONS.md §10: DB-touching tests request `db_session` and are skipped by fixture name when
`TEST_DATABASE_URL` is unset (see `tests/conftest.py`).
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import (
    Done,
    LlmDone,
    LlmStep,
    ToolCall,
    ToolCallStep,
    ToolResult,
    run_agent,
)
from app.mcp.runtime import call_tool
from app.models import Content, User
from app.services.errors import ToolInputError
from app.services.lifecycle import NoopChunkPipeline


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — mirrors `tests/test_mcp_read_tools.py::actor_id` (kept local,
    per that file's own no-cross-test-file-dependency precedent)."""
    user = User(email="error-actionability-admin@example.com", name="Error Actionability Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


# ---------------------------------------------------------------------------
# (a) / (b): unit pins on `call_tool`'s `ToolInputError` message.
# ---------------------------------------------------------------------------


def test_list_field_rejection_message_is_actionable(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`create_draft` with `tags` as the model's actual string-repr mistake -> the raised
    `ToolInputError` names `tags`, says a list/array is expected, and shows a bracketed literal
    example — the shape the probe found necessary for self-correction to succeed."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool(
            "create_draft",
            {"title": "Roth IRA Conversion Basics", "tags": "['retirement']"},
            session=db_session,
            actor_id=actor_id,
        )

    message = str(exc_info.value)
    assert "tags" in message
    assert "list" in message.lower() or "array" in message.lower()
    assert "[" in message and "]" in message, "must show a bracketed literal example"


def test_int_field_rejection_message_is_actionable(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`search_content` with `limit="x"` -> the raised `ToolInputError` names `limit`, says an
    integer is expected, and shows a literal integer example."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("search_content", {"limit": "x"}, session=db_session, actor_id=actor_id)

    message = str(exc_info.value)
    assert "limit" in message
    assert "integer" in message.lower()
    assert "10" in message, "must show a literal integer example"


# ---------------------------------------------------------------------------
# (c) Loop-level integration: the whole self-correction chain, live-failure shape.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RecordedCall:
    """One recorded `_ScriptedLLM.next_step` call — deep-copied `messages` so later in-place
    mutation by the loop can't retroactively change what THIS call actually saw (mirrors
    `tests/test_agent_loop.py::RecordedLlmCall`, kept local per that file's own convention)."""

    messages: list[dict[str, Any]]


@dataclass
class _ScriptedLLM:
    """Minimal scripted, recording `AgentLLM` fake — index-based, not reactive to `messages`.
    Kept local to this file (no cross-test-file import), mirroring
    `tests/test_agent_loop.py::FakeAgentLLM`'s own documented convention."""

    steps: list[LlmStep]
    calls: list[_RecordedCall] = field(default_factory=list)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.calls.append(_RecordedCall(messages=copy.deepcopy(messages)))
        assert len(self.calls) <= len(self.steps), (
            f"script exhausted after {len(self.steps)} steps but the loop asked for step "
            f"#{len(self.calls)}"
        )
        return self.steps[len(self.calls) - 1]


def test_agent_loop_self_corrects_string_repr_tags_into_real_list(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Reproduces the live L-1 failure end-to-end: the model's first `create_draft` call sends
    `tags` as the string `"['retirement']"` (its known first-shot habit); the loop's §6
    one-retry self-correction feeds the (now actionable) error back; the scripted model retries
    with a real list and the exchange succeeds — a draft lands, never a graceful `Error`."""
    llm = _ScriptedLLM(
        steps=[
            ToolCallStep(
                "create_draft",
                {
                    "title": "Roth IRA Conversion Basics",
                    "body_md": "Roth IRA conversions, explained.",
                    "tags": "['retirement']",
                },
            ),
            ToolCallStep(
                "create_draft",
                {
                    "title": "Roth IRA Conversion Basics",
                    "body_md": "Roth IRA conversions, explained.",
                    "tags": ["retirement"],
                },
            ),
            LlmDone(),
        ]
    )
    messages = [
        {
            "role": "user",
            "content": "Draft an article on Roth IRA conversion basics and tag it retirement.",
        }
    ]

    events = list(
        run_agent(
            messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=NoopChunkPipeline()
        )
    )

    # The retry only happened because the fed-back error was actionable — pin the shape of what
    # the SECOND `next_step` call actually saw (the exact chain the live failure traversed).
    assert len(llm.calls) == 3
    second_call_text = str(llm.calls[1].messages)
    assert "tags" in second_call_text
    assert "[" in second_call_text and "]" in second_call_text

    tool_calls = [e for e in events if isinstance(e, ToolCall)]
    tool_results = [e for e in events if isinstance(e, ToolResult)]
    assert len(tool_calls) == 2, "both the failed attempt and the corrected retry are shown"
    assert len(tool_results) == 1, "only the successful retry produces a result"
    assert "Error" not in [type(e).__name__ for e in events], (
        "the self-correction must succeed — no graceful failure, no missing draft"
    )

    done = events[-1]
    assert isinstance(done, Done)
    assert len(done.tool_calls) == 1
    assert done.tool_calls[0]["tool"] == "create_draft"

    content = db_session.execute(
        select(Content).where(Content.title == "Roth IRA Conversion Basics")
    ).scalar_one()
    assert content.status == "draft"
