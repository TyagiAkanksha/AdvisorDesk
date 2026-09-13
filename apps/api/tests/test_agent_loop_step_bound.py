"""Fixer-owned test for `app.agent.loop.run_agent`'s step ceiling (final-review fix wave, F3 /
t03 M-7 promoted).

Task: /home/ak/Documents/github_akanksha/AdvisorDesk/.superpowers/sdd/reports/p5-final-review.md
§5 — "`run_agent` has no iteration bound — an adapter regression of the C-2 class makes the
suite HANG (observed: 10-minute timeout) instead of FAIL." `_MAX_TOOL_CALLS` (the §6 cap) only
bounds tool-call ATTEMPTS; an adapter that keeps returning `TextDelta` forever — never `LlmDone`,
never a tool call — was previously unbounded. `run_agent` now also enforces `_MAX_STEPS` (64), a
ceiling on total `next_step` queries, ending the exchange with a graceful `Error` event instead.

Written as a NEW, sibling file to `tests/test_agent_loop.py`/`tests/test_agent_loop_guards.py` —
mirrors those files' own no-cross-test-file-import precedent (a local, minimal `AgentLLM` fake
rather than importing `FakeAgentLLM` from either).

CONVENTIONS.md §10: this test requests `db_session`, so the module skips cleanly without a DB
(`TEST_DATABASE_URL` unset).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agent.loop import AgentEvent, Done, Error, LlmStep, TextDelta, run_agent
from app.services.lifecycle import NoopChunkPipeline

# Mirrors `app.agent.loop._MAX_STEPS` — duplicated here (not imported) so this test still fails
# loudly, rather than silently no-op-ing, if a future edit changes the private constant without
# updating this pin.
_EXPECTED_MAX_STEPS = 64


@dataclass
class NeverDoneAgentLLM:
    """An `AgentLLM` that never terminates: always returns a `TextDelta`, never `LlmDone`, never
    a tool call — the exact adapter-regression shape (C-2 class) the confirm pass reproduced
    hanging the suite for ~10 minutes before `run_agent` had any bound beyond the §6 tool-call
    cap (which never fires here, since no tool is ever called)."""

    calls: int = 0
    seen_tool_schema_names: list[tuple[str, ...]] = field(default_factory=list)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.calls += 1
        self.seen_tool_schema_names.append(tuple(schema["name"] for schema in tool_schemas))
        return TextDelta("still working, never finishing...")


def test_run_agent_bounds_a_never_terminating_llm_with_a_graceful_error(
    db_session: Session,
) -> None:
    """A `next_step` that always returns `TextDelta` must not hang `run_agent` forever: the loop
    yields exactly one terminal `Error` event (never a `Done`) once the internal step ceiling is
    hit, and does so QUICKLY (proving the bound actually fired, not merely that the fake was
    finite) — the whole exchange completes in well under a second, nowhere near the 10-minute
    hang the confirm pass measured pre-fix.
    """
    llm = NeverDoneAgentLLM()
    messages = [{"role": "user", "content": "start something that never finishes"}]

    started = time.monotonic()
    events: list[AgentEvent] = list(
        run_agent(
            messages,
            llm=llm,
            session=db_session,
            actor_id=uuid.uuid4(),
            pipeline=NoopChunkPipeline(),
        )
    )
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"the step-bounded loop must return quickly, took {elapsed:.2f}s"

    # Exactly `_EXPECTED_MAX_STEPS` queries were made — not fewer (the loop didn't stop early)
    # and not more (the fake's `AssertionError`-free design means only the loop's own bound could
    # have stopped it; a regression back to unbounded would run until the process was killed).
    assert llm.calls == _EXPECTED_MAX_STEPS

    assert len(events) == _EXPECTED_MAX_STEPS + 1, (
        "one Token per TextDelta step, plus exactly one terminal event"
    )
    token_events = events[:-1]
    assert all(type(event).__name__ == "Token" for event in token_events)

    terminal = events[-1]
    assert isinstance(terminal, Error), f"expected a graceful Error, got {type(terminal).__name__}"
    assert not isinstance(terminal, Done)
    assert terminal.code
    assert terminal.message

    # The loop kept offering the full, real tool registry on every query right up to the bound
    # (10 registered tools — phase-9 task-15 added report_weak_queries) — the ceiling stops the
    # EXCHANGE, not the loop's own normal behavior; this bound is orthogonal to
    # `_MAX_TOOL_CALLS`, which never engages here since no tool is ever called.
    assert llm.seen_tool_schema_names[0] == llm.seen_tool_schema_names[-1]
    assert len(llm.seen_tool_schema_names[0]) == 10
