"""Agent trajectory suite: 10 CMS tasks through the REAL agent loop (phase-9 DESIGN §B2, task-07).

`seed/agent_tasks.yaml` holds 10 scripted CMS tasks drawn from PRD §2.2's admin user stories.
`run_agent_suite` drives each one through the real `app.agent.loop.run_agent` against a scratch
schema, scores task success (asserted in the DB), tool-call precision/recall against a reference
trajectory, step count vs the declared minimum, and loops — then the whole run persists as one
`app.services.eval_runs.record_run` invocation with `kind="agent"` (the same `EvalRun`/`EvalResult`
tables an answer run uses), so an agent run is diffable by the same `compare_runs`.

**Recording.** No monkeypatching and no wrapper around `app.mcp.runtime.call_tool`:
`app.agent.loop.run_agent` already yields a `ToolCall(tool, arguments)` event for every attempt, so
`run_agent_task` below just iterates `run_agent`'s own events — the exact seam the loop already
exposes (CONVENTIONS.md §10 forbids mocking our own collaborators; a real run through `call_tool`
is the whole point of this task).

`AgentTaskResult`/`AgentSuiteReport` satisfy `app.services.eval_runs.EvalRowLike`/`EvalReportLike`
by shape (no inheritance) — the same structural-Protocol seam `app.eval.groundedness.EvalRow`/
`EvalReport` already use, so this module persists through the identical `record_run` call.

**`metrics` payload** (persisted into `eval_results.metrics`): `task_id`, `task_success`,
`tool_precision`, `tool_recall`, `steps`, `min_steps`, `efficient`, `looped`, `trajectory`,
`end_state_failures`, `forbidden_tools_called`, and `error` (fix round 1, M4) — the failed
exchange's `Error.message`, or `None` when the exchange had no error. `answer_text` itself
accumulates ONLY `Token` text (task file: "the agent's accumulated `Token` text"); a graceful
failure's message lives in `metrics["error"]`, not appended into `answer_text`.
"""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import OpenAICompatibleAgentLLM
from app.agent.loop import AgentLLM, Done, Error, Token, ToolCall, run_agent
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.eval.groundedness import _git_sha
from app.models import Content, ContentTag, Tag, User
from app.rag.embeddings import OpenAICompatibleEmbedder
from app.rag.pipeline import EmbeddingChunkPipeline
from app.seed_paths import seed_data_dir
from app.services.eval_runs import record_run
from app.services.lifecycle import ChunkPipeline
from app.services.queries import active_select
from app.services.tags import tags_for_contents

__all__ = [
    "AgentSuiteReport",
    "AgentTask",
    "AgentTaskResult",
    "ReferenceStep",
    "ToolCallRecord",
    "evaluate_end_state",
    "load_agent_tasks",
    "run_agent_suite",
    "run_agent_task",
    "score_trajectory",
]

# The end-state assertion shapes this module understands (task file "Assertion shapes" table) —
# each mapping's single leading key must be one of these.
_VALID_ASSERTION_KEYS = {
    "content_title_exists",
    "content_title_contains",
    "content_count",
    "no_new_content",
}

# Fix round 1, M3: the secondary keys each assertion shape accepts alongside its leading key.
# `load_agent_tasks` rejects anything else (or a mistyped one, e.g. plural `tags_includes`) with a
# ValueError naming the offending key, instead of `_check_status_and_tags` silently ignoring it.
_SECONDARY_KEYS_BY_ASSERTION: dict[str, frozenset[str]] = {
    "content_title_exists": frozenset({"status", "tags_include"}),
    "content_title_contains": frozenset({"status", "tags_include"}),
    "content_count": frozenset({"status", "tag"}),
    "no_new_content": frozenset(),
}

_DEFAULT_TASKS_PATH: Path = seed_data_dir() / "agent_tasks.yaml"


# ---------------------------------------------------------------------------
# Data shapes (task file Interfaces).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferenceStep:
    """One step of a task's reference tool trajectory."""

    tool: str
    args_contains: dict[str, object]


@dataclass(frozen=True)
class AgentTask:
    """One scripted CMS task (`seed/agent_tasks.yaml` schema, task file)."""

    id: str
    prompt: str
    reference_trajectory: list[ReferenceStep]
    min_steps: int
    end_state: list[dict[str, object]]
    forbidden_tools: list[str]


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call the agent loop actually attempted."""

    tool: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class AgentTaskResult:
    """One scored task. Satisfies `app.services.eval_runs.EvalRowLike` by shape, so the suite
    persists through the SAME `record_run` an answer run uses (DESIGN: `kind='agent'`)."""

    question: str  # the prompt
    question_class: str | None  # always "agent_task"
    persona: str | None  # always None
    answerable: bool  # always True
    expected_slugs: list[str]  # the reference tool names, in order
    cited_slugs: list[str]  # the tool names actually called, in order
    slugs_hit: bool  # tool_recall == 1.0
    fully_supported: bool | None  # task_success
    refused: bool  # no tool was called at all
    verdict: str  # "PASS" iff task_success
    top_similarity: float | None  # always None
    answer_text: str  # the agent's accumulated `Token` text
    metrics: dict[str, object] | None


@dataclass(frozen=True)
class AgentSuiteReport:
    """Satisfies `EvalReportLike`."""

    rows: list[AgentTaskResult]
    pct_fully_supported: float  # 100 * successes / len(rows)
    refusal_correct: int  # always 0 — refusal is not an agent concept
    refusal_total: int  # always 0


# ---------------------------------------------------------------------------
# `seed/agent_tasks.yaml` loading + strict validation.
# ---------------------------------------------------------------------------


def _parse_reference_step(raw: object, *, task_id: str) -> ReferenceStep:
    """Parse one `reference_trajectory` entry, raising `ValueError` naming `tool` if missing."""
    if not isinstance(raw, dict) or "tool" not in raw:
        raise ValueError(
            f"{task_id}: a reference_trajectory step is missing required 'tool': {raw!r}"
        )
    tool = raw["tool"]
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError(
            f"{task_id}: a reference_trajectory step's 'tool' must be a non-empty string: {raw!r}"
        )
    args_contains = raw.get("args_contains", {})
    if not isinstance(args_contains, dict):
        raise ValueError(
            f"{task_id}: a reference_trajectory step's 'args_contains' must be a mapping: {raw!r}"
        )
    return ReferenceStep(tool=tool, args_contains=dict(args_contains))


def _validate_end_state_assertion(raw: object, *, task_id: str) -> dict[str, object]:
    """Validate one `end_state` assertion mapping, raising `ValueError` naming the offending key.

    Fix round 1, M3: beyond the leading key, also validates the SECONDARY keys against the
    per-shape allowed set (`_SECONDARY_KEYS_BY_ASSERTION`) and, when present, that `tags_include`
    is a list of str — a hand-edit typo (`tags_includes`, or a bare string) used to be silently
    ignored by `_check_status_and_tags` instead of failing loudly.
    """
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"{task_id}: an end_state assertion must be a non-empty mapping: {raw!r}")
    leading_key = next(iter(raw))
    if leading_key not in _VALID_ASSERTION_KEYS:
        raise ValueError(
            f"{task_id}: an end_state assertion has unknown leading key {leading_key!r} "
            f"(expected one of {sorted(_VALID_ASSERTION_KEYS)}): {raw!r}"
        )

    allowed_secondary = _SECONDARY_KEYS_BY_ASSERTION[leading_key]
    unknown_secondary = set(raw) - {leading_key} - allowed_secondary
    if unknown_secondary:
        offending = sorted(unknown_secondary)[0]
        raise ValueError(
            f"{task_id}: an end_state assertion for {leading_key!r} has unknown key "
            f"{offending!r} (expected a subset of {sorted(allowed_secondary)}): {raw!r}"
        )

    if "tags_include" in raw:
        tags_include = raw["tags_include"]
        if not isinstance(tags_include, list) or not all(
            isinstance(item, str) for item in tags_include
        ):
            raise ValueError(
                f"{task_id}: an end_state assertion's 'tags_include' must be a list of str, "
                f"got {tags_include!r}: {raw!r}"
            )

    return dict(raw)


def _parse_task(raw: object) -> AgentTask:
    """Parse and strictly validate one `seed/agent_tasks.yaml` record.

    Raises:
        ValueError: `raw` is missing a required key, or a key's value has the wrong shape — the
            message names the offending key (task file's authored-test contract: "every invalid
            shape ... raises ValueError naming the offending key").
    """
    if not isinstance(raw, dict):
        raise ValueError(f"an agent task record must be a mapping, got {raw!r}")

    task_id = raw.get("id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError(f"an agent task record is missing required 'id': {raw!r}")

    prompt = raw.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"{task_id}: missing required 'prompt': {raw!r}")

    if "reference_trajectory" not in raw:
        raise ValueError(f"{task_id}: missing required 'reference_trajectory'")
    raw_reference = raw["reference_trajectory"]
    if not isinstance(raw_reference, list):
        raise ValueError(f"{task_id}: 'reference_trajectory' must be a list, got {raw_reference!r}")
    reference_trajectory = [_parse_reference_step(step, task_id=task_id) for step in raw_reference]

    min_steps = raw.get("min_steps")
    if not isinstance(min_steps, int) or isinstance(min_steps, bool) or min_steps < 0:
        raise ValueError(f"{task_id}: 'min_steps' must be an int >= 0, got {min_steps!r}")

    if "end_state" not in raw:
        raise ValueError(f"{task_id}: missing required 'end_state'")
    raw_end_state = raw["end_state"]
    if not isinstance(raw_end_state, list):
        raise ValueError(f"{task_id}: 'end_state' must be a list, got {raw_end_state!r}")
    end_state = [_validate_end_state_assertion(item, task_id=task_id) for item in raw_end_state]

    raw_forbidden = raw.get("forbidden_tools", [])
    if not isinstance(raw_forbidden, list):
        raise ValueError(f"{task_id}: 'forbidden_tools' must be a list, got {raw_forbidden!r}")
    forbidden_tools = [str(name) for name in raw_forbidden]

    return AgentTask(
        id=task_id,
        prompt=prompt,
        reference_trajectory=reference_trajectory,
        min_steps=min_steps,
        end_state=end_state,
        forbidden_tools=forbidden_tools,
    )


def load_agent_tasks(path: Path) -> list[AgentTask]:
    """Load and strictly validate `path` (`seed/agent_tasks.yaml`'s own shape).

    Args:
        path: the YAML file to load — a top-level list of task records.

    Returns:
        One `AgentTask` per record, in file order.

    Raises:
        ValueError: `path` doesn't parse to a list, a task id repeats, or any record fails
            `_parse_task`'s validation.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a YAML list of task records, got {type(raw).__name__}")

    tasks = [_parse_task(item) for item in raw]

    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
        raise ValueError(f"{path}: duplicate task 'id' value(s): {duplicates}")

    return tasks


# ---------------------------------------------------------------------------
# Trajectory scoring.
# ---------------------------------------------------------------------------


def _value_matches(expected: object, actual: object) -> bool:
    """One `args_contains` value's match rule (task file "Matching" section).

    `str` -> case-insensitive substring of `str(actual)`; `list` -> every element must satisfy
    the `str` rule against `str(actual)` (the same `actual` value, not per-element indexing);
    anything else -> `==`.
    """
    if isinstance(expected, str):
        return expected.lower() in str(actual).lower()
    if isinstance(expected, list):
        return all(_value_matches(item, actual) for item in expected)
    return expected == actual


def _args_match(
    args_contains: Mapping[str, object], actual_arguments: Mapping[str, object]
) -> bool:
    """Whether `actual_arguments` satisfies every `args_contains` entry."""
    for key, expected in args_contains.items():
        if key not in actual_arguments:
            return False
        if not _value_matches(expected, actual_arguments[key]):
            return False
    return True


def score_trajectory(
    reference: Sequence[ReferenceStep], actual: Sequence[ToolCallRecord]
) -> tuple[float, float, bool]:
    """Greedily match `reference` against `actual`, in order (task file "Matching" section).

    Walks `reference`, keeping a cursor into `actual`; a reference step matches the first actual
    call at/after the cursor with the same `tool` whose arguments satisfy every `args_contains`
    entry — on a match, the cursor advances past it.

    Returns:
        `(tool_precision, tool_recall, looped)` — `tool_recall` is `matched / len(reference)`
        (`1.0` when `reference` is empty); `tool_precision` is `matched / len(actual)` (`1.0` when
        `actual` is empty); `looped` is true iff any two consecutive `actual` calls share both
        `tool` and `arguments`.
    """
    cursor = 0
    matched = 0
    for step in reference:
        for index in range(cursor, len(actual)):
            candidate = actual[index]
            if candidate.tool == step.tool and _args_match(step.args_contains, candidate.arguments):
                matched += 1
                cursor = index + 1
                break

    tool_recall = matched / len(reference) if reference else 1.0
    tool_precision = matched / len(actual) if actual else 1.0
    looped = any(
        actual[index].tool == actual[index + 1].tool
        and actual[index].arguments == actual[index + 1].arguments
        for index in range(len(actual) - 1)
    )
    return tool_precision, tool_recall, looped


# ---------------------------------------------------------------------------
# End-state assertions.
# ---------------------------------------------------------------------------


def _check_status_and_tags(
    session: Session, content: Content, assertion: Mapping[str, object]
) -> list[str]:
    """Shared `status`/`tags_include` checks for a resolved `Content` row (both `_exists`/
    `_contains` assertion shapes accept these two optional secondary keys)."""
    failures: list[str] = []

    expected_status = assertion.get("status")
    if expected_status is not None and content.status != expected_status:
        failures.append(
            f"expected status {expected_status!r} for {content.title!r}, found {content.status!r}"
        )

    raw_tags_include = assertion.get("tags_include")
    if isinstance(raw_tags_include, list) and raw_tags_include:
        expected_tags = [str(tag) for tag in raw_tags_include]
        actual_tags = set(tags_for_contents(session, [content.id])[content.id])
        missing = [tag for tag in expected_tags if tag not in actual_tags]
        if missing:
            failures.append(
                f"expected tags {expected_tags} to include {missing} on "
                f"{content.title!r}, found {sorted(actual_tags)}"
            )

    return failures


def evaluate_end_state(
    session: Session,
    assertions: Sequence[Mapping[str, object]],
    *,
    baseline_content_ids: set[uuid.UUID],
) -> list[str]:
    """Check every `assertions` entry against the real DB, right now.

    Args:
        session: the caller's `Session`.
        assertions: `AgentTask.end_state`-shaped mappings (task file "Assertion shapes" table).
        baseline_content_ids: every `Content.id` that existed immediately before this task ran
            (captured by the caller) — `no_new_content` compares against this set.

    Returns:
        One human-readable failure string per unmet assertion; `[]` means every assertion held.
    """
    failures: list[str] = []

    for assertion in assertions:
        if "content_title_exists" in assertion:
            title = str(assertion["content_title_exists"])
            content = session.execute(
                active_select(Content)
                .where(Content.title == title)
                .order_by(Content.created_at, Content.id)
                .limit(1)
            ).scalar_one_or_none()
            if content is None:
                failures.append(f"content_title_exists: no content titled {title!r} exists")
                continue
            failures.extend(_check_status_and_tags(session, content, assertion))

        elif "content_title_contains" in assertion:
            fragment = str(assertion["content_title_contains"])
            content = session.execute(
                active_select(Content)
                .where(Content.title.ilike(f"%{fragment}%"))
                .order_by(Content.created_at, Content.id)
                .limit(1)
            ).scalar_one_or_none()
            if content is None:
                failures.append(
                    f"content_title_contains: no content titled like {fragment!r} exists"
                )
                continue
            failures.extend(_check_status_and_tags(session, content, assertion))

        elif "content_count" in assertion:
            expected_count = assertion["content_count"]
            stmt = active_select(Content)
            status = assertion.get("status")
            if status is not None:
                stmt = stmt.where(Content.status == status)
            tag = assertion.get("tag")
            if tag is not None:
                stmt = (
                    stmt.join(ContentTag, ContentTag.content_id == Content.id)
                    .join(Tag, Tag.id == ContentTag.tag_id)
                    .where(Tag.name == tag)
                )
            actual_count = len(session.scalars(stmt).all())
            if actual_count != expected_count:
                failures.append(
                    f"content_count: expected {expected_count} (status={status!r}, tag={tag!r}), "
                    f"found {actual_count}"
                )

        elif "no_new_content" in assertion:
            # Deliberately UNfiltered (fix round 1, I1): a task that creates then soft-deletes a
            # row DID create content, and the authored test's own baseline capture is unfiltered
            # too — the two must stay unfiltered together.
            current_ids = set(session.scalars(select(Content.id)).all())
            new_ids = current_ids - baseline_content_ids
            if new_ids:
                failures.append(f"no_new_content: {len(new_ids)} new content row(s) were created")

        else:
            failures.append(f"unrecognized end_state assertion shape: {dict(assertion)!r}")

    return failures


# ---------------------------------------------------------------------------
# Driving the real agent loop.
# ---------------------------------------------------------------------------


def _fresh_llm_for_task(llm: AgentLLM) -> AgentLLM:
    """Return a per-task `AgentLLM` view, resetting any per-exchange state a real adapter carries
    between requests.

    `run_agent_suite` drives MANY tasks through one caller-supplied `llm`, but the real
    `app.agent.llm.OpenAICompatibleAgentLLM` keeps per-EXCHANGE state (`_pending_tool_calls`/
    `_finished` — that module's own "fix round 1, findings C-2/C-3") that must never survive past
    the exchange that created it: once one task's final turn sets `_finished=True`, EVERY later
    `next_step()` call on that SAME instance returns `LlmDone()` immediately, with no provider
    call — silently zeroing out every task after the first (live-verified during this task's own
    real-run evidence). `app.routes.deps.get_agent_llm` avoids exactly this by calling
    `new_conversation()` fresh per HTTP request; this does the same thing per TASK. Duck-typed
    (`AgentLLM` the Protocol declares no such method) so a test's scripted fake — carrying no such
    state and defining no `new_conversation` — is used as-is, unchanged from every already-
    authored test's behavior.
    """
    new_conversation = getattr(llm, "new_conversation", None)
    return new_conversation() if callable(new_conversation) else llm


def run_agent_task(
    session: Session,
    task: AgentTask,
    *,
    llm: AgentLLM,
    actor_id: uuid.UUID,
    pipeline: ChunkPipeline,
) -> AgentTaskResult:
    """Drive one `task` through the real `app.agent.loop.run_agent` and score the result.

    Captures `baseline_content_ids` immediately before `run_agent` runs (so `no_new_content` means
    "this task created nothing"), then iterates `run_agent`'s own events — no monkeypatching, no
    wrapper around `call_tool` (task file "Recording" section): every `ToolCall` event IS a real
    attempted tool call, executed by the loop's own `call_tool`.

    Args:
        session: the caller's `Session` — the same one `run_agent` commits/rolls back through.
        task: the task to run.
        llm: the `AgentLLM` seam (real or scripted).
        actor_id: the admin identity every tool call is stamped with.
        pipeline: the `ChunkPipeline` every write tool call threads through.

    Returns:
        One `AgentTaskResult`, `EvalRowLike`-shaped.

    Raises:
        ValueError: fix round 1, M1 — `actor_id` has no matching `users` row. Several write
            tools (`create_draft`/`edit_content`/...) stamp `actor_id` into `Content.author_id`/
            `updated_by` (both FKs to `users.id`); a dangling id used to be silently papered over
            by inserting a placeholder `User` row from library code — this now fails loudly
            instead, the same principle the CLI's own `--database-url` path already applies.
    """
    if session.get(User, actor_id) is None:
        raise ValueError(f"actor_id {actor_id} has no users row")
    baseline_content_ids = set(session.scalars(select(Content.id)).all())

    messages: list[dict[str, Any]] = [{"role": "user", "content": task.prompt}]
    trajectory: list[ToolCallRecord] = []
    answer_parts: list[str] = []
    error_message: str | None = None

    task_llm = _fresh_llm_for_task(llm)
    events = run_agent(
        messages, llm=task_llm, session=session, actor_id=actor_id, pipeline=pipeline
    )
    for event in events:
        if isinstance(event, ToolCall):
            trajectory.append(ToolCallRecord(tool=event.tool, arguments=dict(event.arguments)))
        elif isinstance(event, Token):
            answer_parts.append(event.text)
        elif isinstance(event, Error):
            # Fix round 1, M4: `answer_text` accumulates ONLY `Token` text (task file). The
            # error still needs to be disclosed somewhere, so it goes into `metrics["error"]`
            # instead of being appended here.
            error_message = event.message
        elif isinstance(event, Done):
            pass

    answer_text = "".join(answer_parts)

    forbidden_tools_called = [
        record.tool for record in trajectory if record.tool in task.forbidden_tools
    ]
    end_state_failures = evaluate_end_state(
        session, task.end_state, baseline_content_ids=baseline_content_ids
    )
    tool_precision, tool_recall, looped = score_trajectory(task.reference_trajectory, trajectory)
    task_success = not end_state_failures and not forbidden_tools_called
    steps = len(trajectory)
    efficient = steps <= task.min_steps if task.min_steps else steps == 0

    metrics: dict[str, object] = {
        "task_id": task.id,
        "task_success": task_success,
        "tool_precision": tool_precision,
        "tool_recall": tool_recall,
        "steps": steps,
        "min_steps": task.min_steps,
        "efficient": efficient,
        "looped": looped,
        "trajectory": [
            {"tool": record.tool, "arguments": dict(record.arguments)} for record in trajectory
        ],
        "end_state_failures": end_state_failures,
        "forbidden_tools_called": forbidden_tools_called,
        "error": error_message,
    }

    return AgentTaskResult(
        question=task.prompt,
        question_class="agent_task",
        persona=None,
        answerable=True,
        expected_slugs=[step.tool for step in task.reference_trajectory],
        cited_slugs=[record.tool for record in trajectory],
        slugs_hit=tool_recall == 1.0,
        fully_supported=task_success,
        refused=steps == 0,
        verdict="PASS" if task_success else "FAIL",
        top_similarity=None,
        answer_text=answer_text,
        metrics=metrics,
    )


def run_agent_suite(
    session: Session,
    tasks: Sequence[AgentTask],
    *,
    llm: AgentLLM,
    actor_id: uuid.UUID,
    pipeline: ChunkPipeline,
) -> AgentSuiteReport:
    """Run every `tasks` entry through `run_agent_task`, in order, and roll the results up.

    Args:
        session: the caller's `Session`.
        tasks: the tasks to run, in order (`load_agent_tasks`'s own file order in production).
        llm: the `AgentLLM` seam (real or scripted) every task runs through.
        actor_id: the admin identity every tool call is stamped with.
        pipeline: the `ChunkPipeline` every write tool call threads through.

    Returns:
        An `AgentSuiteReport` with one `AgentTaskResult` per task, plus the pass-rate summary.
    """
    rows = [
        run_agent_task(session, task, llm=llm, actor_id=actor_id, pipeline=pipeline)
        for task in tasks
    ]
    successes = sum(1 for row in rows if row.verdict == "PASS")
    pct_fully_supported = 100.0 * successes / len(rows) if rows else 0.0

    return AgentSuiteReport(
        rows=rows,
        pct_fully_supported=pct_fully_supported,
        refusal_correct=0,
        refusal_total=0,
    )


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the agent suite CLI's flags (task file "CLI" section).

    `--database-url` is REQUIRED, with no default: this suite mutates real content rows, so it
    must never silently pick up a `DATABASE_URL` pointed at prod.
    """
    parser = argparse.ArgumentParser(
        description="Run seed/agent_tasks.yaml through the real agent loop (phase-9 task-07)."
    )
    parser.add_argument("--label", required=True, help="Run family label for this invocation.")
    parser.add_argument(
        "--database-url",
        required=True,
        help=(
            "Postgres URL to run the suite against. Required, no default — never falls back to "
            "DATABASE_URL, since this suite writes/mutates real content rows."
        ),
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=_DEFAULT_TASKS_PATH,
        help="Path to an agent_tasks.yaml-shaped file.",
    )
    parser.add_argument(
        "--no-persist", action="store_true", help="Don't write an EvalRun/EvalResult row."
    )
    return parser.parse_args(argv)


def _format_score(value: object) -> str:
    """Render a metrics float at two decimals, or `str(value)` when it isn't one."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value)


def _print_task_line(row: AgentTaskResult) -> None:
    """Print one task's one-line result (task file: "prints one line per task")."""
    metrics = row.metrics or {}
    task_id = metrics.get("task_id", "?")
    steps = metrics.get("steps", "?")
    precision = _format_score(metrics.get("tool_precision"))
    recall = _format_score(metrics.get("tool_recall"))
    looped = metrics.get("looped")
    print(
        f"{task_id!s:<28} {row.verdict:<5} steps={steps} precision={precision} "
        f"recall={recall} looped={looped}"
    )


def _run_from_cli(argv: list[str] | None = None) -> None:
    """`python -m app.eval.agent_suite`: wire the REAL agent LLM/embedder, run the suite against
    `--database-url`, print one line per task, and (unless `--no-persist`) persist through the
    same `record_run` an answer run uses, with `kind="agent"`.

    Raises:
        SystemExit: `--database-url`'s database has no `users` row — the suite needs an existing
            user id to stamp as `actor_id` (every write tool's actor FK columns are nullable, but
            this CLI fails loudly rather than silently stamping a dangling/fresh `uuid4()`).
    """
    args = _parse_args(argv)
    settings = Settings()

    tasks = load_agent_tasks(args.tasks)

    llm = OpenAICompatibleAgentLLM.from_settings(settings)
    embedder = OpenAICompatibleEmbedder.from_settings(settings)
    pipeline = EmbeddingChunkPipeline(embedder)

    engine = make_engine(args.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()
    try:
        first_user = session.execute(
            select(User).order_by(User.created_at).limit(1)
        ).scalar_one_or_none()
        if first_user is None:
            raise SystemExit(
                "app.eval.agent_suite: no `users` row found at --database-url — the suite needs "
                "an existing user id to stamp as actor_id. Insert one before running this suite."
            )
        actor_id = first_user.id

        report = run_agent_suite(session, tasks, llm=llm, actor_id=actor_id, pipeline=pipeline)

        for row in report.rows:
            _print_task_line(row)
        passed = sum(1 for row in report.rows if row.verdict == "PASS")
        print(
            f"agent suite: {report.pct_fully_supported:.1f}% tasks passed "
            f"({passed}/{len(report.rows)})"
        )

        if not args.no_persist:
            run = record_run(
                session,
                report,
                label=args.label,
                kind="agent",
                embedding_model=settings.embedding_model,
                chat_model=settings.chat_model,
                judge_model=settings.judge_model,
                similarity_threshold=settings.similarity_threshold,
                retrieval_k=0,
                git_sha=_git_sha(),
            )
            session.commit()
            print(f"recorded eval_runs id={run.id}")
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    _run_from_cli()
