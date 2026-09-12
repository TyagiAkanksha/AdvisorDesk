---
id: p9-t07
phase: phase-9-eval-data-loop
depends_on: [p9-t03]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 07 — Agent trajectory suite: 10 CMS tasks through the real agent loop

## Goal

"Agent evaluation" stops being a word on a slide. `seed/agent_tasks.yaml` holds 10 scripted CMS
tasks drawn from PRD §2.2's admin user stories; `app/eval/agent_suite.py` runs each one through
the **real** `app.agent.loop.run_agent` against a scratch schema, records the tool calls it
actually made, and scores task success (asserted in the DB), tool-call precision/recall against a
reference trajectory, step count vs the minimum, and loops. The whole run persists as an
`eval_runs` row with `kind='agent'` (the column task 01 added for exactly this) plus one
`eval_results` row per task — so an agent run is diffable by the same `compare_runs` as an answer
run. DESIGN never cuts this: it is what makes "agent evaluation" true.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Evaluation approach" (Agent row), §B2
  (`agent_tasks.yaml`'s 10 tasks and required fields), §"Execution order" step 3.
- `advisordesk-prd.md` §2.2 "CMS admin" — the user stories the 10 tasks are drawn from.
- `apps/api/app/agent/loop.py` — the whole file. In particular `AgentLLM` (135-159) and its
  `next_step(messages, tool_schemas) -> LlmStep`; `LlmStep = TextDelta | ToolCallStep | LlmDone`
  (112-132); `AgentEvent = Token | ToolCall | ToolResult | Done | Error` (167-216);
  `run_agent(messages, *, llm, session, actor_id, pipeline)` (234-421) — note it `commit()`s at
  entry and after every tool call, so the caller must not hold uncommitted state across it.
- `apps/api/app/mcp/runtime.py:137-186` (`call_tool`) and the nine registered tool names +
  argument models: `app/mcp/tools_read.py:40-52` (`search_content`: `q`/`status`/`tag`/`limit`),
  `:99-106` (`count_content`: `status`/`tag`), `app/mcp/tools_write.py:88-106` (`create_draft`:
  `title`/`body_md`/`tags`), `:131-146` (`edit_content`: `content_id`/`title`/`body_md`/`tags`),
  `:178-183` (`ContentIdArgs` — `delete_content`/`publish`/`archive`), `:226-235`
  (`tag_content`: `content_id`/`add`/`remove`), `app/mcp/tools_gaps.py:41-50`
  (`report_content_gaps`: `days`/`limit`).
- `apps/api/app/services/eval_runs.py` (task 03) — `EvalRowLike`/`EvalReportLike`/`record_run`.
- `apps/api/app/services/lifecycle.py:23-77` — `ChunkPipeline`/`NoopChunkPipeline`.
- `apps/api/app/rag/pipeline.py:61-72` — `EmbeddingChunkPipeline(embedder)`.
- `apps/api/app/agent/llm.py:214-250` — `OpenAICompatibleAgentLLM.from_settings`.
- `seed/sample_content/` frontmatter — published titles used by the tasks below, and the four
  drafts (`Rebalancing Your Portfolio Basics`, `Year End Tax Planning Checklist`,
  `Coverdell ESA vs 529 Plan Basics`, `Retirement Withdrawal Sequencing Basics`).

## Files

**Create**
- `seed/agent_tasks.yaml`
- `apps/api/app/eval/agent_suite.py`
- `apps/api/tests/test_agent_suite.py`

**Modify** — none.

## Interfaces

### `seed/agent_tasks.yaml` — schema

Top-level list; each item:

| Key | Type | Required | Meaning |
|---|---|---|---|
| `id` | str | yes | stable slug, unique in the file |
| `prompt` | str | yes | the admin's natural-language message (the only thing the agent sees) |
| `reference_trajectory` | list of `{tool, args_contains?}` | yes (may be `[]`) | the tool calls a correct run makes, in order |
| `min_steps` | int ≥ 0 | yes | fewest tool calls that can do the job |
| `end_state` | list of assertion mappings | yes (may be `[]`) | what must be true in the DB afterwards |
| `forbidden_tools` | list of str | no (default `[]`) | calling any of these fails the task outright |

Assertion shapes (exactly one leading key each):
- `{content_title_exists: <str>, status?: <str>, tags_include?: [<str>]}`
- `{content_title_contains: <str>, status?: <str>, tags_include?: [<str>]}` (case-insensitive)
- `{content_count: <int>, status?: <str>, tag?: <str>}`
- `{no_new_content: true}` (no `content` row created since the suite started)

### `seed/agent_tasks.yaml` — the 10 tasks (write this file verbatim)

```yaml
# Agent trajectory suite (phase-9 DESIGN §B2). Ten CMS tasks from PRD §2.2's admin user stories,
# run through the REAL agent loop on a scratch schema seeded from seed/sample_content/.
# `reference_trajectory` is the tool sequence a correct run makes; `args_contains` values are
# matched case-insensitively as substrings of the actual argument.

- id: draft-and-tag
  prompt: "Draft an article on Roth IRA conversion timing and tag it retirement."
  reference_trajectory:
    - tool: create_draft
      args_contains: {title: "Roth IRA conversion", tags: ["retirement"]}
  min_steps: 1
  end_state:
    - content_title_contains: "roth ira conversion timing"
      status: draft
      tags_include: ["retirement"]

- id: count-published-by-tag
  prompt: "How many published pieces do we have on tax planning?"
  reference_trajectory:
    - tool: count_content
      args_contains: {status: "published", tag: "tax-planning"}
  min_steps: 1
  end_state:
    - no_new_content: true

- id: publish-drafts-with-tag
  prompt: "Find everything tagged college-savings and publish the drafts."
  reference_trajectory:
    - tool: search_content
      args_contains: {tag: "college-savings"}
    - tool: publish
  min_steps: 2
  end_state:
    - content_title_exists: "Coverdell ESA vs 529 Plan Basics"
      status: published

- id: archive-by-title
  prompt: "Archive the article titled 'Dollar Cost Averaging Basics'."
  reference_trajectory:
    - tool: search_content
      args_contains: {q: "Dollar Cost Averaging"}
    - tool: archive
  min_steps: 2
  end_state:
    - content_title_exists: "Dollar Cost Averaging Basics"
      status: archived

- id: edit-a-body
  prompt: >-
    Add a closing sentence to 'HSA Triple Tax Advantage Basics' reminding readers to keep their
    receipts.
  reference_trajectory:
    - tool: search_content
      args_contains: {q: "HSA"}
    - tool: edit_content
      args_contains: {body_md: "receipts"}
  min_steps: 2
  end_state:
    - content_title_exists: "HSA Triple Tax Advantage Basics"
      status: published

- id: add-and-remove-tags
  prompt: >-
    Tag 'Understanding Index Funds Basics' with retirement as well, and remove the
    investing-basics tag.
  reference_trajectory:
    - tool: search_content
      args_contains: {q: "Index Funds"}
    - tool: tag_content
      args_contains: {add: ["retirement"], remove: ["investing-basics"]}
  min_steps: 2
  end_state:
    - content_title_exists: "Understanding Index Funds Basics"
      tags_include: ["retirement"]

- id: report-weak-queries
  prompt: "What have clients asked in the last 30 days that our content couldn't answer?"
  reference_trajectory:
    - tool: report_content_gaps
      args_contains: {days: 30}
  min_steps: 1
  end_state:
    - no_new_content: true

- id: propose-a-fix-from-a-gap
  prompt: >-
    Clients keep asking about crypto compensation and we have nothing on it. Check the gaps
    report, then draft something to cover it.
  reference_trajectory:
    - tool: report_content_gaps
    - tool: create_draft
      args_contains: {title: "crypto"}
  min_steps: 2
  end_state:
    - content_title_contains: "crypto"
      status: draft

- id: draft-publish-verify
  prompt: >-
    Draft an article titled 'Mega Backdoor Roth Basics', publish it, and tell me its status.
  reference_trajectory:
    - tool: create_draft
      args_contains: {title: "Mega Backdoor Roth Basics"}
    - tool: publish
  min_steps: 2
  end_state:
    - content_title_exists: "Mega Backdoor Roth Basics"
      status: published

# The ambiguous one: the right move is to ask, not to guess. A correct run calls NO tool at all.
- id: ambiguous-cleanup-should-ask
  prompt: "Clean up the old stuff."
  reference_trajectory: []
  min_steps: 0
  end_state:
    - no_new_content: true
  forbidden_tools:
    - create_draft
    - edit_content
    - delete_content
    - tag_content
    - publish
    - archive
```

### `app/eval/agent_suite.py`

```python
@dataclass(frozen=True)
class ReferenceStep:
    tool: str
    args_contains: dict[str, object]


@dataclass(frozen=True)
class AgentTask:
    id: str
    prompt: str
    reference_trajectory: list[ReferenceStep]
    min_steps: int
    end_state: list[dict[str, object]]
    forbidden_tools: list[str]


@dataclass(frozen=True)
class ToolCallRecord:
    tool: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class AgentTaskResult:
    """One scored task. Satisfies `app.services.eval_runs.EvalRowLike` by shape, so the suite
    persists through the SAME `record_run` an answer run uses (DESIGN: `kind='agent'`)."""

    question: str            # the prompt
    question_class: str | None   # always "agent_task"
    persona: str | None          # always None
    answerable: bool             # always True
    expected_slugs: list[str]    # the reference tool names, in order
    cited_slugs: list[str]       # the tool names actually called, in order
    slugs_hit: bool              # tool_recall == 1.0
    fully_supported: bool | None # task_success
    refused: bool                # no tool was called at all
    verdict: str                 # "PASS" iff task_success
    top_similarity: float | None # always None
    answer_text: str             # the agent's accumulated `Token` text
    metrics: dict[str, object] | None


@dataclass(frozen=True)
class AgentSuiteReport:
    """Satisfies `EvalReportLike`."""

    rows: list[AgentTaskResult]
    pct_fully_supported: float   # 100 * successes / len(rows)
    refusal_correct: int         # always 0 — refusal is not an agent concept
    refusal_total: int           # always 0


def load_agent_tasks(path: Path) -> list[AgentTask]: ...


def evaluate_end_state(
    session: Session, assertions: Sequence[Mapping[str, object]], *, baseline_content_ids: set[uuid.UUID]
) -> list[str]:
    """Return one human-readable failure string per unmet assertion (empty list = all held)."""


def score_trajectory(
    reference: Sequence[ReferenceStep], actual: Sequence[ToolCallRecord]
) -> tuple[float, float, bool]:
    """Return `(tool_precision, tool_recall, looped)`."""


def run_agent_task(
    session: Session,
    task: AgentTask,
    *,
    llm: AgentLLM,
    actor_id: uuid.UUID,
    pipeline: ChunkPipeline,
) -> AgentTaskResult: ...


def run_agent_suite(
    session: Session,
    tasks: Sequence[AgentTask],
    *,
    llm: AgentLLM,
    actor_id: uuid.UUID,
    pipeline: ChunkPipeline,
) -> AgentSuiteReport: ...
```

**Recording.** No monkeypatching and no wrapper around `call_tool`: `run_agent` already yields a
`ToolCall(tool, arguments)` event for **every attempt** (`loop.py:355`), so the recorder is just
`for event in run_agent(...): match event`. That is the "recording tool wrapper" DESIGN asks for,
implemented at the seam the loop already exposes — CONVENTIONS.md §10 forbids mocking our own
collaborators, and a real run through `call_tool` is the whole point.

**Matching (`score_trajectory`).** Greedy, in order: walk `reference`, keeping a cursor into
`actual`; a reference step matches the first actual call at/after the cursor with the same `tool`
whose arguments satisfy every `args_contains` entry; on a match, advance the cursor past it.
`args_contains` value semantics: `str` → case-insensitive substring of `str(actual_value)`;
`list` → every element must satisfy the `str` rule against `str(actual_value)`; anything else →
`==`. Then:
- `tool_recall` = `matched / len(reference)`, and **`1.0` when `reference` is empty**
- `tool_precision` = `matched / len(actual)`, and **`1.0` when `actual` is empty**
  (so the ambiguous task scores 1.0/1.0 for calling nothing, and 0.0/1.0 the moment it acts)
- `looped` = any two consecutive actual calls with identical `tool` **and** identical `arguments`

**`metrics` payload** (persisted into `eval_results.metrics`):

```python
{
    "task_id": task.id,
    "task_success": bool,
    "tool_precision": float,
    "tool_recall": float,
    "steps": int,                 # len(actual)
    "min_steps": task.min_steps,
    "efficient": steps <= min_steps if min_steps else steps == 0,
    "looped": bool,
    "trajectory": [{"tool": ..., "arguments": {...}}, ...],
    "end_state_failures": [str, ...],
    "forbidden_tools_called": [str, ...],
}
```

`task_success` = `not end_state_failures` **and** `not forbidden_tools_called`.

**CLI** — `python -m app.eval.agent_suite --label <label> --database-url <url> [--tasks PATH]
[--no-persist]`. `--database-url` is **required, with no default**: this suite mutates content
rows, so it must never silently pick up a `DATABASE_URL` pointing at prod. It builds
`OpenAICompatibleAgentLLM.from_settings(settings)` and `EmbeddingChunkPipeline(
OpenAICompatibleEmbedder.from_settings(settings))`, picks `actor_id` from the first `users` row
(or a fresh `uuid4()` if the table is empty — the actor columns are nullable FKs to `users`, so
the implementer must **use an existing user id or `None`-safe path**; pick the first user row and
fail loudly with a clear message if there is none), runs the suite, prints one line per task, and
unless `--no-persist` calls `record_run(..., kind="agent", judge_model=settings.judge_model, …)`
then `session.commit()`.

## Steps (TDD)

- [ ] **RED — test-author.** Create `apps/api/tests/test_agent_suite.py`:

```python
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

    def next_step(self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]) -> LlmStep:
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
            {"id": "a", "prompt": "p", "reference_trajectory": [], "min_steps": -1, "end_state": []},
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
    assert evaluate_end_state(
        db_session,
        [{"content_title_exists": "Mega Backdoor Roth Basics", "status": "draft"}],
        baseline_content_ids=baseline,
    ) != []
    assert evaluate_end_state(
        db_session,
        [{"content_title_contains": "mega backdoor"}],
        baseline_content_ids=baseline,
    ) == []
    assert evaluate_end_state(
        db_session, [{"no_new_content": True}], baseline_content_ids=baseline
    ) != []
    assert evaluate_end_state(
        db_session, [{"content_count": 1, "status": "published"}], baseline_content_ids=baseline
    ) == []


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
```

- [ ] **Run RED:** `cd apps/api && TEST_DATABASE_URL=… uv run pytest tests/test_agent_suite.py -q`
  → every test fails (`ModuleNotFoundError: app.eval.agent_suite`, then the missing
  `seed/agent_tasks.yaml`).

- [ ] **GREEN — implementer.** Write `seed/agent_tasks.yaml` verbatim from the block above, then
  `app/eval/agent_suite.py` per Interfaces. Capture `baseline_content_ids` **once per task**,
  immediately before `run_agent` (so `no_new_content` means "this task created nothing"). Remember
  `run_agent` commits; re-read rows after it returns rather than relying on identity map state.

- [ ] **Run GREEN:** `uv run pytest tests/test_agent_suite.py -q`, then `uv run pytest -q`
  (`tests/test_agent_loop.py` must not regress).

- [ ] **Real run (evidence for the report):** seed a scratch DB, then
  `uv run python -m app.eval.agent_suite --label agent-baseline-2026-09 --database-url
  postgresql://…/advisordesk_p9agent` → 10 rows scored, one `eval_runs` row with `kind='agent'`.
  Paste the per-task lines and the run id into the implementer report.

- [ ] **Gates:** `pnpm gates:api` (incl. `lint-imports` — `app.eval` → `app.agent`/`app.mcp` is
  allowed; verify, because `app.eval` is only constrained against `app.main`/`app.factory`).

- [ ] **Commit:** `git commit -m "feat(api): agent trajectory suite over the real agent loop (p9 t07)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=… uv run pytest tests/test_agent_suite.py tests/test_agent_loop.py -q
pnpm gates:api
```

## Acceptance

- `seed/agent_tasks.yaml` holds exactly the 10 tasks above and loads with strict validation; every
  invalid shape in the parametrised test raises `ValueError` naming the offending key.
- Scoring matches every pinned case, including the two empty-denominator conventions and the loop
  detector.
- The suite drives the **real** `run_agent` (no patched `call_tool`, no fake tool registry); the
  DB test proves a real `content` row was written by the loop's own tool execution.
- A run persists as one `eval_runs` row with `kind='agent'` plus one `eval_results` row per task,
  through the same `record_run` an answer run uses.
- `--database-url` is required by the CLI; there is no code path that writes to the default
  `DATABASE_URL`.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-07-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-07-implementer.md`
