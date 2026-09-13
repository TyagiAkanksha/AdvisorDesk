"""Refusal semantics: credit a model-level decline (phase-9 task 05c).

Task brief: `.superpowers/sdd/phase-9-eval-data-loop/task-05c-brief.md`. `refused` (I.2,
`app/eval/groundedness.py`) is `not retrieval_found` — a RETRIEVAL-level signal only. A
`near_miss` row is, by construction, a question where retrieval clears the similarity threshold
on a nearly-relevant (distractor) chunk, the answerer then correctly declines ("No published
guidance covers this...") anyway, and the row is scored FAIL: `refused` is `False` (a chunk WAS
found) even though the model never answered. Persisted-run evidence (`wave1-b-fix1`,
`advisordesk_p9wave1b`) cited by the brief: the Berlin-payroll ESPP question and the
divorce/stock-option-split question both retrieved an over-threshold distractor, both got a
correct decline from the answerer, and both scored FAIL — the two questions that most need a
"did it decline instead of fabricating" credit are exactly the ones the current signal can never
credit.

The fix (Interfaces, task-05c-brief.md): `MetricsJudge` gains `is_refusal(question, answer_text)
-> bool`; `EvalRow` gains `model_declined: bool = False`; `_evaluate_question` calls
`is_refusal` once, on the RAW answer text, for every row where a `metrics_judge` is present AND
retrieval found something (`retrieval_found`) -- never for a full miss, never without a
`metrics_judge`. The uncovered-row verdict rule becomes `PASS iff (refused and not cited_slugs)
or model_declined`; answerable rows are unchanged (a decline on an answerable question still
FAILs, but `model_declined` is still recorded for triage).

RED note: `app.eval.groundedness.EvalRow` has no `model_declined` field yet and
`OpenAIJudge`/the `MetricsJudge` Protocol have no `is_refusal` member yet, so every pin below that
touches either one fails now (`AttributeError` on `EvalRow.model_declined` /
`OpenAIJudge.is_refusal`, `KeyError` on `row.metrics["model_declined"]`, or a plain count/verdict
assertion failing because the pre-fix code never makes the new judge call at all). Pin 2
(`test_uncovered_question_answered_confidently_still_fails`) is the one exception by design: it
pins a case the CURRENT code already gets right (a confident hallucination over a cleared-
threshold distractor stays FAIL) and exists as a boundary/regression guard on the fix's new `or
model_declined` clause, not as a defect demonstration -- it is expected to pass both before and
after the implementer's change.

Fixture helpers (`_add_content`, `_add_chunk`, `_write_questions_yaml`, `ScriptedEmbedder`,
`ScriptedChatLLM`, `ScriptedJudge`, `_query_vector`) are reused from `tests/test_groundedness.py`
by import (all are plain module-level names, importable despite the leading underscore on some --
same cross-test-file pattern already established by
`tests/test_eval_metrics_judge_fixes.py::from tests.test_eval_metrics import ...`). Every other
fake in this file (`_FakeMetricsJudge`, the fake OpenAI client chain for `OpenAIJudge`) is defined
locally, per this codebase's no-cross-test-file-fakes convention
(`tests/test_groundedness.py`/`tests/test_eval_metrics_fix_round1.py` module docstrings) --
`tests/test_eval_metrics_fix_round1.py`'s `_FakeMessage`/`_FakeChoice`/`_FakeCompletion`/
`_FakeChat`/`_FakeOpenAIClient` shape is copied (not imported), and `_FakeCompletions` is widened
here to record every call's kwargs (the round-1 version discards them) since pin 5 needs to
assert `temperature`/`model` were actually passed through.

CONVENTIONS.md §10: every test below that requests `db_session` is skipped by fixture name (not
silently dropped) when `TEST_DATABASE_URL` is unset (`tests/conftest.py`); pin 5 needs no DB and
always runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from openai import OpenAI
from sqlalchemy.orm import Session

from app.eval.groundedness import OpenAIJudge, run_eval
from tests.test_groundedness import (
    ScriptedChatLLM,
    ScriptedEmbedder,
    ScriptedJudge,
    _add_chunk,
    _add_content,
    _query_vector,
    _write_questions_yaml,
)

# ---------------------------------------------------------------------------
# Local fake: a `MetricsJudge` (and, incidentally, `GroundednessJudge` -- it has `is_supported`
# too) that answers every rubric question `True` and scripts/records `is_refusal` only. Every pin
# below exercises `is_refusal`; the other methods are stubbed just deeply enough to satisfy
# `_evaluate_question`'s unconditional `rank_chunk_relevance` call and its answered-row-only
# `is_answer_relevant` call without ever reaching a real judge.
# ---------------------------------------------------------------------------


@dataclass
class _FakeMetricsJudge:
    """`declines` scripts every `is_refusal` reply; `refusal_calls` records each call's
    `(question, answer_text)` pair so pins 4 and 6 can assert exact call counts.
    """

    declines: bool = False
    refusal_calls: list[tuple[str, str]] = field(default_factory=list)

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        return True

    def is_answer_relevant(self, question: str, answer_text: str) -> bool:
        return True

    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool:
        return True

    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        return True

    def rank_chunk_relevance(self, question: str, chunk_texts: Sequence[str]) -> list[bool] | None:
        return [True for _ in chunk_texts]

    def is_refusal(self, question: str, answer_text: str) -> bool:
        self.refusal_calls.append((question, answer_text))
        return self.declines


# ---------------------------------------------------------------------------
# Local fake: a minimal fake OpenAI client for exercising `OpenAIJudge.is_refusal` directly (the
# shape copied from `tests/test_eval_metrics_fix_round1.py`'s `_FakeMessage`/`_FakeChoice`/
# `_FakeCompletion`/`_FakeChat`/`_FakeOpenAIClient` -- but `_FakeCompletions` here RECORDS every
# call's kwargs instead of discarding them, since pin 5 asserts `temperature`/`model`).
# ---------------------------------------------------------------------------


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeCompletion:
    choices: list[_FakeChoice]


@dataclass
class _FakeCompletions:
    reply: str
    calls: list[dict[str, object]] = field(default_factory=list)

    def create(self, **kwargs: object) -> _FakeCompletion:
        self.calls.append(kwargs)
        return _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(content=self.reply))])


@dataclass
class _FakeChat:
    completions: _FakeCompletions


@dataclass
class _FakeOpenAIClient:
    """Structurally satisfies the one `client.chat.completions.create(...)` call `OpenAIJudge`
    makes -- never a real `OpenAI` instance, `cast` at the call site tells mypy this is
    deliberate (mirrors `tests/test_eval_metrics_fix_round1.py`'s own `_FakeOpenAIClient`).
    """

    chat: _FakeChat


def _fake_openai_judge(reply: str) -> tuple[OpenAIJudge, _FakeCompletions]:
    completions = _FakeCompletions(reply=reply)
    client = _FakeOpenAIClient(chat=_FakeChat(completions=completions))
    return OpenAIJudge(client=cast(OpenAI, client), model="gpt-5.4"), completions


# ---------------------------------------------------------------------------
# Pin 1.
# ---------------------------------------------------------------------------


def test_near_miss_decline_over_threshold_counts_as_a_correct_refusal(
    db_session: Session, tmp_path: Path
) -> None:
    """Brief evidence: the Berlin-payroll ESPP question, `answerable: false`, whose distractor
    chunk clears the similarity threshold (`cos_theta=0.9`, the same over-threshold shape as
    `tests/test_groundedness.py::
    test_uncovered_question_with_hallucinated_answer_counts_as_refusal_incorrect`) makes
    `retrieval_found=True` -- so `refused` (the retrieval-only I.2 signal) is `False` even though
    the model correctly declines. A metrics judge that recognizes the decline (`is_refusal`
    True) must credit this row as a correct refusal anyway.
    """
    question = "I am on our Berlin payroll — how is my ESPP purchase taxed in Germany?"
    distractor = _add_content(db_session, slug="dollar-cost-averaging-basics")
    _add_chunk(
        db_session,
        distractor.id,
        text="Dollar-cost averaging invests a fixed amount on a fixed schedule.",
        cos_theta=0.9,
    )
    questions_path = _write_questions_yaml(
        tmp_path, [{"question": question, "expected_slugs": [], "answerable": False}]
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    chat_llm = ScriptedChatLLM(
        answers={question: "No published guidance covers this. Please ask the advisory team."}
    )
    metrics_judge = _FakeMetricsJudge(declines=True)

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=ScriptedJudge(),
        questions_path=questions_path,
        metrics_judge=metrics_judge,
    )

    row = report.rows[0]
    assert row.refused is False
    assert row.model_declined is True
    assert len(row.cited_slugs) > 0
    assert row.verdict == "PASS"
    assert report.refusal_correct == 1
    assert report.refusal_total == 1
    assert row.metrics is not None
    assert row.metrics["model_declined"] is True


# ---------------------------------------------------------------------------
# Pin 2.
# ---------------------------------------------------------------------------


def test_uncovered_question_answered_confidently_still_fails(
    db_session: Session, tmp_path: Path
) -> None:
    """Same near-miss shape as pin 1 (an over-threshold distractor, `cos_theta=0.9`), but the
    model answers confidently from the distractor instead of declining, and the metrics judge's
    `is_refusal` correctly says so (`False`). This must still FAIL and must NOT count toward
    `refusal_correct` -- the new `or model_declined` verdict clause must never fire for a genuine
    hallucination just because a `metrics_judge` happens to be wired in.

    Boundary/regression pin (see module docstring): the current, pre-fix code already gets this
    case right (`refused=False` already routes it to FAIL), so this specific pin is expected to
    pass both before and after the implementer's change -- it guards the fix, it does not
    demonstrate the defect.
    """
    question = "My divorce is being finalized — how do we split my stock options?"
    distractor = _add_content(db_session, slug="dollar-cost-averaging-basics")
    _add_chunk(
        db_session,
        distractor.id,
        text="Dollar-cost averaging invests a fixed amount on a fixed schedule.",
        cos_theta=0.9,
    )
    questions_path = _write_questions_yaml(
        tmp_path, [{"question": question, "expected_slugs": [], "answerable": False}]
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    chat_llm = ScriptedChatLLM(
        answers={
            question: "Covered calls generate steady premium income with no meaningful downside."
        }
    )
    metrics_judge = _FakeMetricsJudge(declines=False)

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=ScriptedJudge(),
        questions_path=questions_path,
        metrics_judge=metrics_judge,
    )

    row = report.rows[0]
    assert row.verdict == "FAIL"
    assert report.refusal_correct == 0


# ---------------------------------------------------------------------------
# Pin 3.
# ---------------------------------------------------------------------------


def test_answerable_question_the_model_declines_still_fails_but_is_recorded(
    db_session: Session, tmp_path: Path
) -> None:
    """An `answerable: true` row whose expected chunk IS retrieved (`slugs_hit=True`), but the
    model declines instead of answering it. Answerable-row verdicts are UNCHANGED by this fix
    (module docstring) -- the decline sentence fails the pre-existing faithfulness check (a
    `ScriptedJudge` marker matching the decline wording), so `verdict` stays "FAIL" for the same
    reason it always has. `model_declined` is still recorded for triage regardless of verdict:
    `_evaluate_question` calls `is_refusal` for every row where retrieval found something,
    independent of `question.answerable`.
    """
    question = "What is a Roth IRA conversion and how is it taxed?"
    content = _add_content(db_session, slug="roth-ira-conversion-basics")
    _add_chunk(
        db_session,
        content.id,
        text="Converting funds from a traditional IRA to a Roth IRA is a taxable event.",
        cos_theta=0.95,
    )
    questions_path = _write_questions_yaml(
        tmp_path,
        [
            {
                "question": question,
                "expected_slugs": ["roth-ira-conversion-basics"],
                "answerable": True,
            }
        ],
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    decline = "No published guidance covers this. Please ask the advisory team."
    chat_llm = ScriptedChatLLM(answers={question: decline})
    judge = ScriptedJudge(unsupported_markers=("No published guidance",))
    metrics_judge = _FakeMetricsJudge(declines=True)

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
        metrics_judge=metrics_judge,
    )

    row = report.rows[0]
    assert row.verdict == "FAIL"
    assert row.metrics is not None
    assert row.metrics["model_declined"] is True


# ---------------------------------------------------------------------------
# Pin 4.
# ---------------------------------------------------------------------------


def test_without_a_metrics_judge_no_refusal_call_is_made_and_behaviour_is_unchanged(
    db_session: Session, tmp_path: Path
) -> None:
    """Pin 1's exact set-up, but `metrics_judge=None`: the pre-fix behaviour is preserved
    (`model_declined` stays the dataclass default `False`, `verdict` stays "FAIL" -- a
    retrieval-level non-refusal with citations attached, unaffected by a `model_declined` that
    was never computed) and nothing calls `is_refusal`.

    The fake standing in for the required `judge=` seam here ALSO exposes `is_refusal` (it is the
    same `_FakeMetricsJudge`, which structurally satisfies `GroundednessJudge` too via
    `is_supported`) precisely so this is a real regression guard: an implementation that gated
    the call on `hasattr(judge, "is_refusal")` instead of strictly on whether a `metrics_judge`
    was supplied would be caught red-handed by `refusal_calls` being non-empty.
    """
    question = "I am on our Berlin payroll — how is my ESPP purchase taxed in Germany?"
    distractor = _add_content(db_session, slug="dollar-cost-averaging-basics")
    _add_chunk(
        db_session,
        distractor.id,
        text="Dollar-cost averaging invests a fixed amount on a fixed schedule.",
        cos_theta=0.9,
    )
    questions_path = _write_questions_yaml(
        tmp_path, [{"question": question, "expected_slugs": [], "answerable": False}]
    )
    embedder = ScriptedEmbedder(vectors={question: _query_vector()})
    chat_llm = ScriptedChatLLM(
        answers={question: "No published guidance covers this. Please ask the advisory team."}
    )
    judge = _FakeMetricsJudge(declines=True)

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
        metrics_judge=None,
    )

    row = report.rows[0]
    assert row.model_declined is False
    assert row.verdict == "FAIL"
    assert judge.refusal_calls == []


# ---------------------------------------------------------------------------
# Pin 5.
# ---------------------------------------------------------------------------


def test_refusal_judge_call_is_temperature_zero_on_the_judge_model() -> None:
    """`OpenAIJudge.is_refusal` (task-05c Interfaces): one `chat.completions.create` call at
    `temperature=0` on the judge model ("gpt-5.4" here, p9 t05d), parsed via the same
    first-line YES/NO convention as its siblings (`OpenAIJudge._ask_yes_no`) -- "YES" (any case)
    means the answer declines; anything else, including a junk/malformed reply, means it does not.
    """
    yes_judge, yes_completions = _fake_openai_judge(
        "YES\nThe answer declines to address the question."
    )

    result = yes_judge.is_refusal(
        "What does the firm recommend about cryptocurrency staking rewards?",
        "No published guidance covers this. Please ask the advisory team.",
    )

    assert result is True
    assert len(yes_completions.calls) == 1
    assert yes_completions.calls[0]["temperature"] == 0
    assert yes_completions.calls[0]["model"] == "gpt-5.4"

    no_judge, _no_completions = _fake_openai_judge("no")
    assert no_judge.is_refusal("Q?", "A confident, on-topic answer.") is False

    junk_judge, _junk_completions = _fake_openai_judge("this reply is neither yes nor no")
    assert junk_judge.is_refusal("Q?", "A confident, on-topic answer.") is False


# ---------------------------------------------------------------------------
# Pin 6.
# ---------------------------------------------------------------------------


def test_one_refusal_call_per_answered_row(db_session: Session, tmp_path: Path) -> None:
    """Three questions through one `run_eval` call, each on its own isolated axis
    (`tests/test_groundedness.py` module docstring convention: axis pairs 0/1, 2/3, 4/5 are
    mutually orthogonal, so one question's seeded chunk can never leak into another's
    retrieval). Two rows have `retrieval_found=True` (one answerable, one near-miss-shaped) and
    get exactly one `is_refusal` call apiece; the third, a full miss with nothing seeded near its
    axis at all (`retrieval_found=False`), gets none -- the call is gated on `retrieval_found`,
    not on `question.answerable`.
    """
    q_answerable = "What is a Roth IRA conversion and how is it taxed?"
    q_near_miss = "My divorce is being finalized — how do we split my stock options?"
    q_full_miss = "What does the firm recommend about cryptocurrency staking rewards?"

    answerable_content = _add_content(db_session, slug="roth-ira-conversion-basics")
    _add_chunk(
        db_session,
        answerable_content.id,
        text="Converting funds from a traditional IRA to a Roth IRA is a taxable event.",
        cos_theta=0.95,
        axis=0,
    )
    distractor_content = _add_content(db_session, slug="dollar-cost-averaging-basics")
    _add_chunk(
        db_session,
        distractor_content.id,
        text="Dollar-cost averaging invests a fixed amount on a fixed schedule.",
        cos_theta=0.9,
        axis=2,
    )
    # axis=4 (q_full_miss): no chunk seeded near it at all -- retrieval finds nothing.

    questions_path = _write_questions_yaml(
        tmp_path,
        [
            {
                "question": q_answerable,
                "expected_slugs": ["roth-ira-conversion-basics"],
                "answerable": True,
            },
            {"question": q_near_miss, "expected_slugs": [], "answerable": False},
            {"question": q_full_miss, "expected_slugs": [], "answerable": False},
        ],
    )
    embedder = ScriptedEmbedder(
        vectors={
            q_answerable: _query_vector(axis=0),
            q_near_miss: _query_vector(axis=2),
            q_full_miss: _query_vector(axis=4),
        }
    )
    chat_llm = ScriptedChatLLM(
        answers={
            q_answerable: "A Roth IRA conversion is a taxable event.",
            q_near_miss: "No published guidance covers this. Please ask the advisory team.",
            q_full_miss: "No published guidance covers this. Please ask the advisory team.",
        }
    )
    metrics_judge = _FakeMetricsJudge(declines=True)

    run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=ScriptedJudge(),
        questions_path=questions_path,
        metrics_judge=metrics_judge,
    )

    assert len(metrics_judge.refusal_calls) == 2
