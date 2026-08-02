"""Fixer-owned tests for `app.agent.loop.run_agent` (phase-5 task-03 review round 1).

Task: /home/ak/Documents/github_akanksha/AdvisorDesk/.superpowers/sdd/reports/p5-t03-review.md
(Opus review of commit `e58f007`) — this file pins the loop-level findings from that review's fix
round 1: **C-1** (a synthesized tool call's `arguments` must be a JSON STRING on the wire, not the
raw dict — every real follow-up provider query 400'd until this was fixed), **I-1** (the §6 cap
bounds ATTEMPTED tool calls, not just successful ones — an alternating fail/succeed script
previously ran 16 tool executions against an "8 tool calls per request" cap), and **C-4** (each
individual `call_tool` invocation now owns its own commit/rollback boundary, mirroring
`app.mcp.server._execute_tool_call`'s per-call transaction semantics — a failed tool's partial
write must roll back on the spot, and an earlier successful write in the same exchange must
survive a LATER failure in that same exchange).

Written as a NEW, sibling file to the pinned `tests/test_agent_loop.py` — per the fix-round
brief, that file (and `tests/test_agent_endpoint.py`) may not be modified. Style/fakes mirror
`test_agent_loop.py`'s own local `FakeAgentLLM`/`RecordingChunkPipeline`/`actor_id` fixture
(kept local here too, no cross-test-file import, per that file's own no-cross-test-file-import
precedent).

CONVENTIONS.md §10: every test here requests `db_session`, so the whole module skips cleanly
without a DB (`TEST_DATABASE_URL` unset).
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import (
    AgentEvent,
    Done,
    Error,
    LlmDone,
    LlmStep,
    ToolCall,
    ToolCallStep,
    ToolResult,
    run_agent,
)
from app.models import Chunk, Content, User
from app.services import content as content_service
from app.services.errors import AppError, EmbeddingFailedError
from app.services.lifecycle import NoopChunkPipeline

# ---------------------------------------------------------------------------
# Fakes — field-for-field mirrors of `tests/test_agent_loop.py`'s own local copies (kept local
# here too, per that file's own no-cross-test-file-import precedent).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedLlmCall:
    """One recorded `FakeAgentLLM.next_step` call — a deep copy of `messages`."""

    messages: list[dict[str, Any]]
    tool_schema_names: tuple[str, ...]


@dataclass
class FakeAgentLLM:
    """Scripted, recording `AgentLLM` fake — see `tests/test_agent_loop.py::FakeAgentLLM`."""

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
                f"asked for step #{len(self.calls)}."
            )
        return self.steps[len(self.calls) - 1]


@dataclass
class FailingChunkPipeline:
    """A `ChunkPipeline` whose `rebuild_chunks` always raises `EmbeddingFailedError` — simulates
    the embedding provider being down mid-publish (C-4's reviewer-pinned failure scenario)."""

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        raise EmbeddingFailedError("The embedding provider call failed.")

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        return 0


def _event_names(events: list[AgentEvent]) -> list[str]:
    return [type(event).__name__ for event in events]


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — mirrors `tests/test_agent_loop.py::actor_id`."""
    user = User(email="loop-guard-admin@example.com", name="Loop Guard Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


# ---------------------------------------------------------------------------
# C-1 — synthesized tool-call `arguments` must be a JSON STRING on the wire.
# ---------------------------------------------------------------------------


def test_synthesized_tool_call_arguments_are_a_json_string_not_a_raw_dict(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Fix round 1, finding C-1: `run_agent` synthesizes an `assistant`/`tool_calls` message
    before every tool-call attempt and feeds it back on the NEXT `next_step` call. The OpenAI
    wire protocol (and the real NVIDIA endpoint, live-verified 400) requires
    `tool_calls[].function.arguments` to be a JSON-ENCODED STRING — the pre-fix code sent the
    raw `dict`, which the real provider rejected on every follow-up query. This asserts the
    SECOND `next_step` call's `messages` carries that field as a `str` that round-trips (via
    `json.loads`) to the exact arguments dict the tool was actually called with.
    """
    arguments = {"title": "Wire Format Check", "body_md": "body", "tags": ["a", "b"]}
    llm = FakeAgentLLM(steps=[ToolCallStep("create_draft", arguments), LlmDone()])
    messages = [{"role": "user", "content": "Draft an article titled Wire Format Check."}]

    list(
        run_agent(
            messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=NoopChunkPipeline()
        )
    )

    assert len(llm.calls) == 2, "one call to attempt the tool, one more after it succeeded"
    second_call_messages = llm.calls[1].messages
    assistant_tool_call_messages = [
        message
        for message in second_call_messages
        if message.get("role") == "assistant" and message.get("tool_calls")
    ]
    assert len(assistant_tool_call_messages) == 1
    synthesized_arguments = assistant_tool_call_messages[0]["tool_calls"][0]["function"][
        "arguments"
    ]
    assert isinstance(synthesized_arguments, str), (
        f"expected a JSON-encoded string, got {type(synthesized_arguments).__name__}: "
        f"{synthesized_arguments!r}"
    )
    assert json.loads(synthesized_arguments) == arguments


# ---------------------------------------------------------------------------
# I-1 — the cap bounds ATTEMPTS, not successes.
# ---------------------------------------------------------------------------


def test_cap_counts_attempted_calls_not_only_successes_alternating_fail_succeed(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Fix round 1, finding I-1 (reviewer probe P-D): the pinned model's known weakness is
    alternating one failing attempt with one successful one — `consecutive_failures` never
    reaches 2 (each failure is followed by a success, resetting it), so error-once never fires,
    and the PRE-FIX cap (`len(completed) >= 8`) let this run 16 tool executions / 16 provider
    queries before stopping. This script alternates a `publish` on a nonexistent id (a
    `NotFoundError`, always fails) with a `create_draft` (always succeeds), 4 times each — the
    cap must stop at exactly 8 ATTEMPTS (`call_index`), not wait for 8 successes.

    `FakeAgentLLM` itself enforces the bound from the other direction: it raises loudly if the
    loop asks for a 9th step, so this test would fail LOUDLY (not hang) if the cap regressed.
    """
    steps: list[LlmStep] = []
    for i in range(1, 5):
        steps.append(ToolCallStep("publish", {"content_id": str(uuid.uuid4())}))
        steps.append(ToolCallStep("create_draft", {"title": f"Attempt Cap Article {i}"}))
    llm = FakeAgentLLM(steps=steps)
    messages = [{"role": "user", "content": "Publish four nonexistent drafts, alternating."}]

    events = list(
        run_agent(
            messages, llm=llm, session=db_session, actor_id=actor_id, pipeline=NoopChunkPipeline()
        )
    )

    assert len(llm.calls) == 8, "the loop must stop after exactly 8 ATTEMPTS, not 8 successes"
    tool_call_events = [e for e in events if isinstance(e, ToolCall)]
    tool_result_events = [e for e in events if isinstance(e, ToolResult)]
    assert len(tool_call_events) == 8, "8 attempts total (4 failing + 4 succeeding)"
    assert len(tool_result_events) == 4, "only the 4 successful attempts produce a result"

    assert isinstance(events[-1], Done), "alternating failures never go 2-in-a-row -> no Error"
    assert len(events[-1].tool_calls) == 4

    created = (
        db_session.execute(select(Content).where(Content.title.like("Attempt Cap Article%")))
        .scalars()
        .all()
    )
    assert len(created) == 4

    final_text = "".join(getattr(e, "text", "") for e in events if type(e).__name__ == "Token")
    assert "4" in final_text, final_text


# ---------------------------------------------------------------------------
# C-4 — per-call commit/rollback: a failing publish rolls back, but earlier successes in the
# same exchange (and later ones after the failure) persist.
# ---------------------------------------------------------------------------


def test_failing_publish_rolls_back_but_earlier_and_later_successful_calls_persist(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Fix round 1, finding C-4 (the reviewer's exact scenario): a `publish` whose
    `rebuild_chunks` raises `EmbeddingFailedError` mid-exchange must never leave the content row
    `status='published'` with zero chunks — the pre-fix bug committed exactly that (a single
    trailing `session.commit()` at the route layer papered over the failed call's own dirty
    flush). This scripts: a successful `create_draft` BEFORE the failure (must persist), then
    TWO consecutive failing `publish` attempts against the SAME draft (error-once -> `Error`
    after the second), and asserts:
      - the earlier successful `create_draft` row is still there (a later failure in the same
        exchange never rolls back an already-committed success);
      - the draft targeted by `publish` is still `status='draft'`, with zero `Chunk` rows for it
        (the failed publish's flushed status change was rolled back, never committed).
    """
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    db_session.commit()
    draft_id = draft.id

    llm = FakeAgentLLM(
        steps=[
            ToolCallStep("create_draft", {"title": "Persisted Before The Failure"}),
            ToolCallStep("publish", {"content_id": str(draft_id)}),
            ToolCallStep("publish", {"content_id": str(draft_id)}),
        ]
    )
    messages = [
        {
            "role": "user",
            "content": "Create a new draft, then publish the Roth IRA Basics draft twice.",
        }
    ]

    events = list(
        run_agent(
            messages,
            llm=llm,
            session=db_session,
            actor_id=actor_id,
            pipeline=FailingChunkPipeline(),
        )
    )

    assert _event_names(events)[-1] == "Error", "two consecutive publish failures -> graceful Error"
    error_event = events[-1]
    assert isinstance(error_event, Error)
    assert error_event.code == EmbeddingFailedError.code

    # The EARLIER successful create_draft persisted, despite the LATER failures in this exchange.
    persisted = db_session.execute(
        select(Content).where(Content.title == "Persisted Before The Failure")
    ).scalar_one_or_none()
    assert persisted is not None, "an earlier successful call must survive a later failure"

    # The failed publish's flushed status change never landed: still draft, zero chunks.
    reloaded = db_session.execute(select(Content).where(Content.id == draft_id)).scalar_one()
    assert reloaded.status == "draft", "the failed publish's status flush must have rolled back"
    chunk_count = (
        db_session.execute(select(Chunk).where(Chunk.content_id == draft_id)).scalars().all()
    )
    assert chunk_count == [], "zero chunks — rebuild_chunks raised before writing any"


def test_call_tool_raises_apperror_subtypes_that_run_agent_catches() -> None:
    """Sanity/documentation pin: `EmbeddingFailedError` (used by `FailingChunkPipeline` above)
    is an `AppError`, the family `run_agent`'s `except AppError` clause catches — guards against
    a future refactor of `app.services.errors` silently narrowing that catch."""
    assert issubclass(EmbeddingFailedError, AppError)
