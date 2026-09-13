"""Agent-suite alternative-tool matching + prompt-completion pins (phase-9 task-07b, RED).

Evidence: `.superpowers/sdd/phase-9-eval-data-loop/reports/agent-suite-regression.md`. Two
independent problems hid inside the 8/10, 10/10, 9/10 noise; this file pins the fix for both
WITHOUT editing `app/` or `seed/agent_tasks.yaml` (that is the implementer's job, task-07b brief
Rulings 1 and 2) — a separate file from `test_agent_suite.py`, which the test-author must not
touch.

Ruling 1 (scoring bug, ours): `seed/agent_tasks.yaml`'s `propose-a-fix-from-a-gap` reference
trajectory demands a literal `create_draft`, but `propose_content_fix` (registered after task-07
froze that reference) is now the system-prompt-taught idiomatic tool for exactly that scenario —
so a CORRECT run scores `tool_recall = 0.5` in every run, regardless of model. The fix: a
`ReferenceStep` gains an optional `any_of: list[str]` — a step matches when the actual call's tool
name is `tool` OR appears in `any_of`, `args_contains` still enforced either way. `load_agent_tasks`
must raise `ValueError` naming the offending task when a step has neither `tool` nor `any_of`.
`score_trajectory`'s greedy in-order matching is otherwise unchanged.

Ruling 2 (one sentence, `app.agent.loop.SYSTEM_PROMPT`): in 1 of 3 runs the agent drafted an
article and then declined to publish it, misreading the existing "don't auto-publish unless
explicitly instructed" guardrail as requiring a SECOND, later, standalone publish request — even
though the single message it was answering already asked for both draft AND publish. The fix is
one added sentence making explicit that such a message is itself the explicit instruction. The
existing, keyword-pinned guardrail sentence
(`tests/test_agent_loop.py::test_system_prompt_forbids_publishing_without_explicit_instruction`)
must survive verbatim alongside it.

RED expectation: every `any_of`-using test below fails with `TypeError` (`ReferenceStep` doesn't
accept `any_of` yet) until Ruling 1 lands; the prompt test fails on a missing-fragment
`AssertionError` until Ruling 2 lands. The three "existing conventions" tests and the
neither-key-raises-ValueError test are pins that already hold today and must keep holding
afterwards — they are not expected to be RED.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.agent.loop import SYSTEM_PROMPT
from app.eval.agent_suite import (
    ReferenceStep,
    ToolCallRecord,
    load_agent_tasks,
    score_trajectory,
)

# --- Ruling 1: `any_of` alternative-tool matching -----------------------------


def test_any_of_step_matches_when_actual_call_used_the_alternative_tool() -> None:
    """A step naming `any_of` alternatives matches an actual call that used one of them instead
    of the primary `tool` — but `args_contains` is still enforced against that alternative call,
    exactly as it is for `tool`."""
    reference = [
        ReferenceStep(
            tool="create_draft",
            any_of=["propose_content_fix"],
            args_contains={"title": "crypto"},
        )
    ]

    matching_call = [
        ToolCallRecord(tool="propose_content_fix", arguments={"title": "Crypto Comp 101"})
    ]
    precision, recall, _looped = score_trajectory(reference, matching_call)
    assert (precision, recall) == (pytest.approx(1.0), pytest.approx(1.0))

    non_matching_call = [
        ToolCallRecord(tool="propose_content_fix", arguments={"title": "Roth Basics"})
    ]
    precision2, recall2, _looped2 = score_trajectory(reference, non_matching_call)
    assert (precision2, recall2) == (pytest.approx(0.0), pytest.approx(0.0))


def test_any_of_step_still_matches_when_actual_call_used_the_primary_tool() -> None:
    """The same step, `any_of` and all, must still match when the actual call used the primary
    `tool` rather than one of its alternatives — adding alternatives must not cost the primary
    match."""
    reference = [
        ReferenceStep(
            tool="create_draft",
            any_of=["propose_content_fix"],
            args_contains={"title": "crypto"},
        )
    ]
    actual = [ToolCallRecord(tool="create_draft", arguments={"title": "Crypto Comp 101"})]

    precision, recall, _looped = score_trajectory(reference, actual)

    assert (precision, recall) == (pytest.approx(1.0), pytest.approx(1.0))


def test_reference_step_missing_both_tool_and_any_of_raises_value_error_naming_task(
    tmp_path: Path,
) -> None:
    """`load_agent_tasks` must validate that a step has at least one of `tool`/`any_of`, and name
    the offending task id in the `ValueError` when neither is present."""
    task_id = "step-with-neither-tool-nor-any-of"
    item = {
        "id": task_id,
        "prompt": "p",
        "reference_trajectory": [{"args_contains": {}}],
        "min_steps": 0,
        "end_state": [],
    }
    path = tmp_path / "agent_tasks.yaml"
    path.write_text(yaml.safe_dump([item], sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_agent_tasks(path)

    assert task_id in str(excinfo.value)


def test_propose_content_fix_trajectory_scores_full_recall_against_create_draft_any_of() -> None:
    """The exact regression scenario (agent-suite-regression.md §4c): a recorded trajectory that
    used `propose_content_fix` where the reference names `create_draft` with
    `any_of: [propose_content_fix]` must score `tool_recall == 1.0`, not the stale `0.5`."""
    reference = [
        ReferenceStep(tool="report_content_gaps", args_contains={}),
        ReferenceStep(
            tool="create_draft",
            any_of=["propose_content_fix"],
            args_contains={"title": "crypto"},
        ),
    ]
    actual = [
        ToolCallRecord(tool="report_content_gaps", arguments={"days": 30, "limit": 20}),
        ToolCallRecord(
            tool="propose_content_fix", arguments={"title": "Crypto Compensation Basics"}
        ),
    ]

    _precision, recall, _looped = score_trajectory(reference, actual)

    assert recall == pytest.approx(1.0)


# --- existing conventions, re-asserted so the new matching cannot silently break them ----------


def test_exact_reference_trajectory_still_scores_one_and_one() -> None:
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


def test_empty_reference_trajectory_still_scores_full_recall() -> None:
    assert score_trajectory([], []) == (1.0, 1.0, False)


def test_extra_unrelated_call_still_only_lowers_precision() -> None:
    reference = [ReferenceStep(tool="count_content", args_contains={})]
    actual = [
        ToolCallRecord(tool="count_content", arguments={"tag": "tax-planning"}),
        ToolCallRecord(tool="search_content", arguments={"q": "anything"}),
    ]

    precision, recall, _looped = score_trajectory(reference, actual)

    assert precision == pytest.approx(0.5)
    assert recall == pytest.approx(1.0)


# --- Ruling 2: the agent system prompt completes a draft-and-publish request -------------------

# Lifted verbatim from the controller brief's own prescribed sentence content (task-07b-brief.md,
# Ruling 2) — the implementer's most direct route to satisfying this pin is to use this wording.
_NEW_DRAFT_AND_PUBLISH_FRAGMENT = "both a draft and a publish is itself the explicit request"

# Copied verbatim (lower-cased) from the current `SYSTEM_PROMPT` — this exact sentence is pinned
# keyword-wise by `tests/test_agent_loop.py::
# test_system_prompt_forbids_publishing_without_explicit_instruction` and must survive unedited.
_EXISTING_PUBLISH_GUARDRAIL_FRAGMENT = (
    "never publish it unless the user's message explicitly instructs you to publish"
)


def test_system_prompt_completes_a_draft_and_publish_request_and_keeps_the_guardrail() -> None:
    """Ruling 2: one new sentence must make explicit that a single message asking for both a
    draft AND a publish is itself the explicit instruction to do both — and the existing,
    verbatim-pinned publish-guardrail sentence must survive alongside it, so a later edit cannot
    silently delete either rule."""
    lower = SYSTEM_PROMPT.lower()

    assert _NEW_DRAFT_AND_PUBLISH_FRAGMENT in lower
    assert _EXISTING_PUBLISH_GUARDRAIL_FRAGMENT in lower
