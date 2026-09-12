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
    AgentSuiteReport,
    AgentTask,
    AgentTaskResult,
    ReferenceStep,
    ToolCallRecord,
    _parse_args,
    evaluate_end_state,
    load_agent_tasks,
    run_agent_suite,
    run_agent_task,
    score_trajectory,
)
from app.models import Content, EvalResult, EvalRun, User
from app.seed_paths import seed_data_dir
from app.services.eval_runs import record_run
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
    actor = User(email="agent-suite-draft-and-tag@example.test")
    db_session.add(actor)
    db_session.flush()
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
        actor_id=actor.id,
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
    actor = User(email="agent-suite-ambiguous-cleanup@example.test")
    db_session.add(actor)
    db_session.flush()
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
        db_session, [task], llm=llm, actor_id=actor.id, pipeline=NoopChunkPipeline()
    )

    row = report.rows[0]
    assert row.verdict == "FAIL"
    assert row.metrics is not None
    assert row.metrics["forbidden_tools_called"] == ["create_draft"]
    assert row.metrics["tool_precision"] == pytest.approx(0.0)


# --- fix round 1 -------------------------------------------------------------


def test_content_title_exists_ignores_a_soft_deleted_row(db_session: Session) -> None:
    """I1: a soft-deleted row must not satisfy `content_title_exists` — publish then
    soft-delete, and the assertion must fail rather than hitting the tombstone."""
    baseline = set(db_session.scalars(select(Content.id)).all())
    content = Content(
        title="Coverdell ESA vs 529 Plan Basics",
        slug="coverdell-esa-vs-529-plan-basics-fix1",
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.flush()
    content.is_deleted = True
    db_session.flush()

    failures = evaluate_end_state(
        db_session,
        [{"content_title_exists": "Coverdell ESA vs 529 Plan Basics", "status": "published"}],
        baseline_content_ids=baseline,
    )

    assert failures != []


@pytest.mark.parametrize(
    "item, fragment",
    [
        (
            {
                "id": "a",
                "prompt": "p",
                "reference_trajectory": [],
                "min_steps": 0,
                "end_state": [{"content_title_exists": "x", "tags_includes": ["retirement"]}],
            },
            "tags_includes",
        ),
        (
            {
                "id": "a",
                "prompt": "p",
                "reference_trajectory": [],
                "min_steps": 0,
                "end_state": [{"content_title_exists": "x", "tags_include": "retirement"}],
            },
            "tags_include",
        ),
    ],
)
def test_invalid_end_state_secondary_keys_raise_value_error(
    tmp_path: Path, item: dict[str, object], fragment: str
) -> None:
    """M3: an unknown or mistyped secondary key (plural `tags_includes`, or a bare string
    instead of a list) must fail loudly at load time, not be silently ignored at scoring time."""
    path = tmp_path / "agent_tasks.yaml"
    path.write_text(yaml.safe_dump([item], sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_agent_tasks(path)

    assert fragment in str(excinfo.value)


def test_run_agent_task_fails_loudly_when_actor_id_has_no_users_row(db_session: Session) -> None:
    """M1: a dangling `actor_id` must raise, not silently insert a placeholder `User` row."""
    task = AgentTask(
        id="whatever",
        prompt="Clean up the old stuff.",
        reference_trajectory=[],
        min_steps=0,
        end_state=[],
        forbidden_tools=[],
    )

    with pytest.raises(ValueError, match="has no users row"):
        run_agent_task(
            db_session,
            task,
            llm=ScriptedAgentLLM(steps=[]),
            actor_id=uuid.uuid4(),
            pipeline=NoopChunkPipeline(),
        )


@dataclass
class FreshInstanceAgentLLM:
    """I2(a): a scripted fake exposing `new_conversation()` — mirrors the real adapter's
    per-task reset contract `_fresh_llm_for_task` relies on. `new_conversation()` returns a
    brand-new instance sharing `seen_ids` so the test can tell which physical object served
    each task."""

    seen_ids: list[int]

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.seen_ids.append(id(self))
        return LlmDone()

    def new_conversation(self) -> FreshInstanceAgentLLM:
        return FreshInstanceAgentLLM(seen_ids=self.seen_ids)


@dataclass
class ReusedInstanceAgentLLM:
    """I2(a): a scripted fake with NO `new_conversation` — `_fresh_llm_for_task` must fall back
    to reusing the SAME instance for every task."""

    seen_ids: list[int]

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.seen_ids.append(id(self))
        return LlmDone()


def _two_noop_tasks() -> list[AgentTask]:
    return [
        AgentTask(
            id="t1",
            prompt="p1",
            reference_trajectory=[],
            min_steps=0,
            end_state=[],
            forbidden_tools=[],
        ),
        AgentTask(
            id="t2",
            prompt="p2",
            reference_trajectory=[],
            min_steps=0,
            end_state=[],
            forbidden_tools=[],
        ),
    ]


def test_run_agent_suite_gives_each_task_a_fresh_llm_when_the_adapter_supports_it(
    db_session: Session,
) -> None:
    actor = User(email="agent-suite-fresh-llm@example.test")
    db_session.add(actor)
    db_session.flush()
    seen_ids: list[int] = []
    llm = FreshInstanceAgentLLM(seen_ids=seen_ids)

    run_agent_suite(
        db_session, _two_noop_tasks(), llm=llm, actor_id=actor.id, pipeline=NoopChunkPipeline()
    )

    assert len(seen_ids) == 2
    assert seen_ids[0] != seen_ids[1]


def test_run_agent_suite_reuses_the_same_llm_when_the_adapter_has_no_new_conversation(
    db_session: Session,
) -> None:
    actor = User(email="agent-suite-reused-llm@example.test")
    db_session.add(actor)
    db_session.flush()
    seen_ids: list[int] = []
    llm = ReusedInstanceAgentLLM(seen_ids=seen_ids)

    run_agent_suite(
        db_session, _two_noop_tasks(), llm=llm, actor_id=actor.id, pipeline=NoopChunkPipeline()
    )

    assert len(seen_ids) == 2
    assert seen_ids[0] == seen_ids[1]


def test_parse_args_requires_database_url() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--label", "x"])


def test_parse_args_accepts_no_persist_and_defaults_tasks_path() -> None:
    args = _parse_args(["--label", "x", "--database-url", "postgresql://example/db"])

    assert args.no_persist is False
    assert args.tasks == seed_data_dir() / "agent_tasks.yaml"

    args_no_persist = _parse_args(
        ["--label", "x", "--database-url", "postgresql://example/db", "--no-persist"]
    )
    assert args_no_persist.no_persist is True


def test_agent_suite_report_persists_through_record_run(db_session: Session) -> None:
    """I2(c): `AgentTaskResult`/`AgentSuiteReport`'s `EvalRowLike`/`EvalReportLike` conformance
    is a RUNTIME fact, not just a mypy one — a two-task report persists as exactly one `EvalRun`
    with `kind == "agent"` and two `EvalResult` rows carrying the metrics payload."""

    def _metrics(task_id: str) -> dict[str, object]:
        return {
            "task_id": task_id,
            "task_success": True,
            "tool_precision": 1.0,
            "tool_recall": 1.0,
            "steps": 0,
            "min_steps": 0,
            "efficient": True,
            "looped": False,
            "trajectory": [],
            "end_state_failures": [],
            "forbidden_tools_called": [],
            "error": None,
        }

    def _result(task_id: str, prompt: str) -> AgentTaskResult:
        return AgentTaskResult(
            question=prompt,
            question_class="agent_task",
            persona=None,
            answerable=True,
            expected_slugs=[],
            cited_slugs=[],
            slugs_hit=True,
            fully_supported=True,
            refused=True,
            verdict="PASS",
            top_similarity=None,
            answer_text="",
            metrics=_metrics(task_id),
        )

    report = AgentSuiteReport(
        rows=[_result("t1", "prompt one"), _result("t2", "prompt two")],
        pct_fully_supported=100.0,
        refusal_correct=0,
        refusal_total=0,
    )

    run = record_run(
        db_session,
        report,
        label="agent-fix1-test",
        kind="agent",
        embedding_model="m",
        chat_model="m",
        judge_model="m",
        similarity_threshold=0.5,
        retrieval_k=0,
    )
    db_session.flush()

    assert run.kind == "agent"
    assert run.total_questions == 2
    assert db_session.scalars(select(EvalRun).where(EvalRun.id == run.id)).all() == [run]

    results = db_session.scalars(select(EvalResult).where(EvalResult.run_id == run.id)).all()
    expected_metric_keys = {
        "task_id",
        "task_success",
        "tool_precision",
        "tool_recall",
        "steps",
        "min_steps",
        "efficient",
        "looped",
        "trajectory",
        "end_state_failures",
        "forbidden_tools_called",
    }
    assert len(results) == 2
    for result in results:
        assert result.metrics is not None
        assert expected_metric_keys.issubset(result.metrics)
