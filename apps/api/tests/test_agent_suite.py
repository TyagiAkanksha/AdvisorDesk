"""Agent trajectory suite pins (phase-9 task-07, DESIGN "Agent" row)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import LlmDone, LlmStep, TextDelta, ToolCallStep
from app.eval.agent_suite import (
    AgentTask,
    ReferenceStep,
    ToolCallRecord,
    evaluate_end_state,
    load_agent_tasks,
    run_agent_suite,
    score_trajectory,
)
from app.models import Content
from app.services.lifecycle import NoopChunkPipeline

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ScriptedAgentLLM:
    """Emits a fixed list of steps, then `LlmDone` — the reference trajectory, by construction."""

    steps: list[LlmStep]
    index: int = 0
    seen_schemas: list[int] = field(default_factory=list)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.seen_schemas.append(len(tool_schemas))
        if self.index >= len(self.steps):
            return LlmDone()
        step = self.steps[self.index]
        self.index += 1
        return step


# --- the committed task file -------------------------------------------------


def test_agent_tasks_yaml_loads_ten_validated_tasks() -> None:
    tasks = load_agent_tasks(_REPO_ROOT / "seed" / "agent_tasks.yaml")

    assert len(tasks) == 10
    assert len({task.id for task in tasks}) == 10
    ambiguous = next(task for task in tasks if task.id == "ambiguous-cleanup-should-ask")
    assert ambiguous.reference_trajectory == []
    assert "create_draft" in ambiguous.forbidden_tools
    for task in tasks:
        assert task.prompt.strip()
        assert task.min_steps >= 0
        assert len(task.reference_trajectory) >= task.min_steps


@pytest.mark.parametrize(
    "item, fragment",
    [
        ({"prompt": "p", "reference_trajectory": [], "min_steps": 0, "end_state": []}, "id"),
        ({"id": "a", "reference_trajectory": [], "min_steps": 0, "end_state": []}, "prompt"),
        ({"id": "a", "prompt": "p", "min_steps": 0, "end_state": []}, "reference_trajectory"),
        (
            {
                "id": "a",
                "prompt": "p",
                "reference_trajectory": [{"args_contains": {}}],
                "min_steps": 0,
                "end_state": [],
            },
            "tool",
        ),
        (
            {
                "id": "a",
                "prompt": "p",
                "reference_trajectory": [],
                "min_steps": -1,
                "end_state": [],
            },
            "min_steps",
        ),
        (
            {
                "id": "a",
                "prompt": "p",
                "reference_trajectory": [],
                "min_steps": 0,
                "end_state": [{"bogus_assertion": 1}],
            },
            "end_state",
        ),
    ],
)
def test_invalid_task_records_raise_value_error(
    tmp_path: Path, item: dict[str, object], fragment: str
) -> None:
    path = tmp_path / "agent_tasks.yaml"
    path.write_text(yaml.safe_dump([item], sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_agent_tasks(path)

    assert fragment in str(excinfo.value)


# --- scoring -----------------------------------------------------------------


def test_exact_reference_trajectory_scores_one_and_one() -> None:
    reference = [
        ReferenceStep(tool="search_content", args_contains={"q": "Index Funds"}),
        ReferenceStep(tool="tag_content", args_contains={"add": ["retirement"]}),
    ]
    actual = [
        ToolCallRecord(tool="search_content", arguments={"q": "index funds", "limit": 10}),
        ToolCallRecord(tool="tag_content", arguments={"content_id": "x", "add": ["retirement"]}),
    ]

    precision, recall, looped = score_trajectory(reference, actual)

    assert (precision, recall, looped) == (1.0, 1.0, False)


def test_an_extra_unrelated_call_lowers_precision_but_not_recall() -> None:
    reference = [ReferenceStep(tool="count_content", args_contains={})]
    actual = [
        ToolCallRecord(tool="count_content", arguments={"tag": "tax-planning"}),
        ToolCallRecord(tool="search_content", arguments={"q": "anything"}),
    ]

    precision, recall, _looped = score_trajectory(reference, actual)

    assert precision == pytest.approx(0.5)
    assert recall == pytest.approx(1.0)


def test_calling_nothing_when_nothing_was_expected_scores_perfectly() -> None:
    assert score_trajectory([], []) == (1.0, 1.0, False)


def test_calling_a_tool_when_none_was_expected_scores_zero_precision() -> None:
    precision, recall, _looped = score_trajectory(
        [], [ToolCallRecord(tool="delete_content", arguments={"content_id": "x"})]
    )

    assert precision == pytest.approx(0.0)
    assert recall == pytest.approx(1.0)


def test_two_identical_consecutive_calls_are_a_loop() -> None:
    call = ToolCallRecord(tool="search_content", arguments={"q": "same"})

    _precision, _recall, looped = score_trajectory([], [call, call])

    assert looped is True


# --- end-state assertions ----------------------------------------------------


def test_end_state_assertions_pass_and_fail_against_real_rows(db_session: Session) -> None:
    baseline = set(db_session.scalars(select(Content.id)).all())
    published = Content(
        title="Mega Backdoor Roth Basics",
        slug="mega-backdoor-roth-basics",
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add(published)
    db_session.flush()

    assert (
        evaluate_end_state(
            db_session,
            [{"content_title_exists": "Mega Backdoor Roth Basics", "status": "published"}],
            baseline_content_ids=baseline,
        )
        == []
    )
    assert (
        evaluate_end_state(
            db_session,
            [{"content_title_exists": "Mega Backdoor Roth Basics", "status": "draft"}],
            baseline_content_ids=baseline,
        )
        != []
    )
    assert (
        evaluate_end_state(
            db_session,
            [{"content_title_contains": "mega backdoor"}],
            baseline_content_ids=baseline,
        )
        == []
    )
    assert (
        evaluate_end_state(db_session, [{"no_new_content": True}], baseline_content_ids=baseline)
        != []
    )
    assert (
        evaluate_end_state(
            db_session, [{"content_count": 1, "status": "published"}], baseline_content_ids=baseline
        )
        == []
    )


# --- through the real agent loop ---------------------------------------------


def test_suite_runs_a_task_through_the_real_agent_loop_and_scores_it(
    db_session: Session,
) -> None:
    """A scripted LLM emitting the reference trajectory must score 1.0/1.0 and PASS — and the
    row it creates must really be in the DB (the loop's own `call_tool` did the work)."""
    task = AgentTask(
        id="draft-and-tag",
        prompt="Draft an article on Roth IRA conversion timing and tag it retirement.",
        reference_trajectory=[
            ReferenceStep(
                tool="create_draft",
                args_contains={"title": "Roth IRA conversion", "tags": ["retirement"]},
            )
        ],
        min_steps=1,
        end_state=[
            {
                "content_title_contains": "roth ira conversion timing",
                "status": "draft",
                "tags_include": ["retirement"],
            }
        ],
        forbidden_tools=[],
    )
    llm = ScriptedAgentLLM(
        steps=[
            ToolCallStep(
                name="create_draft",
                arguments={
                    "title": "Roth IRA Conversion Timing",
                    "body_md": "When to convert.",
                    "tags": ["retirement"],
                },
            ),
            TextDelta(text="Drafted and tagged."),
        ]
    )

    report = run_agent_suite(
        db_session,
        [task],
        llm=llm,
        actor_id=uuid.uuid4(),
        pipeline=NoopChunkPipeline(),
    )

    assert report.pct_fully_supported == pytest.approx(100.0)
    row = report.rows[0]
    assert row.verdict == "PASS"
    assert row.question == task.prompt
    assert row.cited_slugs == ["create_draft"]
    assert row.metrics is not None
    assert row.metrics["task_success"] is True
    assert row.metrics["tool_precision"] == pytest.approx(1.0)
    assert row.metrics["tool_recall"] == pytest.approx(1.0)
    assert row.metrics["steps"] == 1
    assert row.metrics["looped"] is False
    assert "Drafted and tagged." in row.answer_text


def test_a_forbidden_tool_call_fails_the_ambiguous_task(db_session: Session) -> None:
    task = AgentTask(
        id="ambiguous-cleanup-should-ask",
        prompt="Clean up the old stuff.",
        reference_trajectory=[],
        min_steps=0,
        end_state=[{"no_new_content": True}],
        forbidden_tools=["create_draft"],
    )
    llm = ScriptedAgentLLM(
        steps=[ToolCallStep(name="create_draft", arguments={"title": "Guessed", "tags": []})]
    )

    report = run_agent_suite(
        db_session, [task], llm=llm, actor_id=uuid.uuid4(), pipeline=NoopChunkPipeline()
    )

    row = report.rows[0]
    assert row.verdict == "FAIL"
    assert row.metrics is not None
    assert row.metrics["forbidden_tools_called"] == ["create_draft"]
    assert row.metrics["tool_precision"] == pytest.approx(0.0)
