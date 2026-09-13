"""Faithfulness-judge input hygiene (phase-9 task 05b, from the task-10 re-review)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy.orm import Session

from app.eval.groundedness import run_eval
from app.eval.judge_scorecard import judge_answer
from app.eval.metrics import split_sentences, strip_citation_markers
from app.models import Chunk, Content
from tests.test_eval_metrics import ScriptedChatLLM, ScriptedEmbedder, _unit_vector


@dataclass
class LetterOnlyJudge:
    """Supports any claim that has a letter and no `[n]` marker — exactly the two defects."""

    calls: list[str] = field(default_factory=list)

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append(claim_text)
        return any(ch.isalpha() for ch in claim_text) and "[" not in claim_text


# --- split_sentences -----------------------------------------------------------


def test_split_sentences_drops_ordinal_list_markers() -> None:
    sentences = split_sentences("Two options: 1. Sell at vest. 2. Hold the shares.")

    assert "1." not in sentences
    assert "2." not in sentences
    assert all(any(ch.isalpha() for ch in s) for s in sentences)
    assert "Sell at vest." in sentences
    assert "Hold the shares." in sentences


def test_split_sentences_still_splits_after_amounts_and_years() -> None:
    assert split_sentences("The limit is $25,000. It was set in 2026. Next year may differ.") == [
        "The limit is $25,000.",
        "It was set in 2026.",
        "Next year may differ.",
    ]


def test_split_sentences_keeps_a_sentence_that_starts_with_a_marker() -> None:
    assert split_sentences("Step 1. Sell.") == ["Step 1.", "Sell."]


# --- strip_citation_markers -----------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Costs $2,500 [2].", "Costs $2,500."),
        ("See [1][3] here.", "See here."),
        ("No markers.", "No markers."),
        ("Ends with marker [12]", "Ends with marker"),
        ("", ""),
    ],
)
def test_strip_citation_markers(text: str, expected: str) -> None:
    assert strip_citation_markers(text) == expected
    assert strip_citation_markers(strip_citation_markers(text)) == expected


# --- through the harness ------------------------------------------------------------


def _one_question_yaml(tmp_path: Path, question: str) -> Path:
    path = tmp_path / "eval_questions.yaml"
    path.write_text(
        yaml.safe_dump(
            [{"question": question, "expected_slugs": [], "answerable": True}], sort_keys=False
        ),
        encoding="utf-8",
    )
    return path


def test_cited_list_answer_is_fully_supported_when_markers_and_fragments_are_removed(
    db_session: Session, tmp_path: Path
) -> None:
    """The talk's 'what do you charge' answer shape: a numbered list with `[n]` citations."""
    question = "How do you charge?"
    answer = "Two ways: 1. A 0.75% advisory fee [1]. 2. A $4,500 flat plan [2]."
    judge = LetterOnlyJudge()

    # Test-author fixture addition (brief note): seed one published Content + Chunk whose
    # embedding matches `_unit_vector(0)` above the similarity threshold, so retrieval finds
    # something and the row is ANSWERED instead of refused — an empty corpus makes `run_eval`
    # refuse before the judge is ever called. Copied from `tests/test_eval_metrics.py::
    # test_run_eval_records_chunk_level_metrics_and_class_rollups`.
    content = Content(
        title="Advisory fees",
        slug="advisory-fees",
        body_md="unused",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.flush()
    chunk = Chunk(
        content_id=content.id,
        chunk_index=0,
        text="We charge either a 0.75% advisory fee or a $4,500 flat planning fee.",
        embedding=_unit_vector(0),
    )
    db_session.add(chunk)
    db_session.flush()

    report = run_eval(
        db_session,
        embedder=ScriptedEmbedder(vectors={question: _unit_vector(0)}),
        chat_llm=ScriptedChatLLM(answers={question: answer}),
        judge=judge,
        questions_path=_one_question_yaml(tmp_path, question),
    )

    row = report.rows[0]
    assert row.answer_text == answer  # the persisted answer stays raw
    assert all("[" not in claim for claim in judge.calls)
    assert all(any(ch.isalpha() for ch in claim) for claim in judge.calls)
    assert row.fully_supported is True


def test_judge_answer_uses_the_same_hygiene_as_the_harness() -> None:
    judge = LetterOnlyJudge()

    assert judge_answer(judge, "1. Fee is 0.75% [2]. 2. Plan is $4,500 [1].", ["c"]) is True
    assert all("[" not in claim and any(ch.isalpha() for ch in claim) for claim in judge.calls)
