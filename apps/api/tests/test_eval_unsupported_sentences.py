"""Persisted per-sentence faithfulness verdicts (controller addition, phase-9 task 05c).

Dispatch (task-05c implementer, controller addition): two triages this phase could not name
which sentence a row's faithfulness judge rejected. `EvalRow.metrics["unsupported_sentences"]`
(a `list[str]`, `app/eval/groundedness.py::_evaluate_question`) now records the claim(s) — post
`[n]`-marker stripping, i.e. exactly the text `judge.is_supported` was actually asked about —
that the faithfulness judge rejected for an answerable row; `[]` when every judged sentence was
supported (or the row is uncovered and nothing was judged at all). The short-circuit that already
decided `fully_supported` (the old `all(genexpr)`, now an equivalent `for`/`break` loop) is kept
exactly as it was — "no extra judge calls" (the controller's own cost constraint) — so this list
holds at most one entry: the sentence that made `fully_supported` False, not necessarily every
failing sentence in the answer.

Fixture helpers (`_add_content`, `_add_chunk`, `_write_questions_yaml`, `ScriptedEmbedder`,
`ScriptedChatLLM`, `ScriptedJudge`, `_query_vector`) are reused from `tests/test_groundedness.py`
by import — the same cross-test-file pattern `tests/test_eval_refusal_semantics.py` and
`tests/test_eval_metrics_judge_fixes.py` already establish; this file owns no local fakes.

CONVENTIONS.md §10: both tests below request `db_session` and are skipped by fixture name (not
silently dropped) when `TEST_DATABASE_URL` is unset (`tests/conftest.py`).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.eval.groundedness import run_eval
from tests.test_groundedness import (
    ScriptedChatLLM,
    ScriptedEmbedder,
    ScriptedJudge,
    _add_chunk,
    _add_content,
    _query_vector,
    _write_questions_yaml,
)


def test_second_sentence_rejected_is_recorded_stripped_of_its_marker(
    db_session: Session, tmp_path: Path
) -> None:
    """An answerable row whose answer's SECOND sentence is judged unsupported (content-scripted,
    same marker convention as `tests/test_groundedness.py::
    test_one_unsupported_sentence_marks_fully_supported_false`) records exactly that sentence in
    `metrics["unsupported_sentences"]` — with its `[1]` citation marker already gone, since
    `_evaluate_question` judges `strip_citation_markers(answer_text)`'s sentences, never the raw
    bracketed text.
    """
    question = "What is a Roth IRA conversion and how is it taxed?"
    content = _add_content(db_session, slug="roth-ira-conversion-basics")
    chunk_text = "Converting funds from a traditional IRA to a Roth IRA is a taxable event."
    _add_chunk(db_session, content.id, text=chunk_text, cos_theta=0.95)
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
    answer = (
        "Converting funds to a Roth IRA is a taxable event [1]. "
        "UNSUPPORTED_CLAIM_MARKER the conversion also guarantees higher retirement income [1]."
    )
    expected_second_sentence = (
        "UNSUPPORTED_CLAIM_MARKER the conversion also guarantees higher retirement income."
    )
    chat_llm = ScriptedChatLLM(answers={question: answer})
    judge = ScriptedJudge(unsupported_markers=("UNSUPPORTED_CLAIM_MARKER",))

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    row = report.rows[0]
    assert row.fully_supported is False
    assert row.metrics is not None
    assert row.metrics["unsupported_sentences"] == [expected_second_sentence]
    assert "[1]" not in expected_second_sentence


def test_fully_supported_row_records_an_empty_list(db_session: Session, tmp_path: Path) -> None:
    """An answerable row whose every judged sentence is supported (the default all-true
    `ScriptedJudge`) records `metrics["unsupported_sentences"] == []` — never omitted, never
    `None`.
    """
    question = "What is a Roth IRA conversion and how is it taxed?"
    content = _add_content(db_session, slug="roth-ira-conversion-basics")
    chunk_text = "Converting funds from a traditional IRA to a Roth IRA is a taxable event."
    _add_chunk(db_session, content.id, text=chunk_text, cos_theta=0.95)
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
    chat_llm = ScriptedChatLLM(
        answers={question: "Converting funds to a Roth IRA is a taxable event."}
    )
    judge = ScriptedJudge()  # all-true

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=judge,
        questions_path=questions_path,
    )

    row = report.rows[0]
    assert row.fully_supported is True
    assert row.metrics is not None
    assert row.metrics["unsupported_sentences"] == []
