"""Judge scorecard pins (phase-9 task-08, DESIGN "Judge" row)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy.orm import Session

from app.eval.judge_scorecard import (
    JudgeLabel,
    cohen_kappa,
    export_pending,
    judge_answer,
    load_judge_labels,
    position_verbosity_spotcheck,
    score_judge,
    self_consistency,
)
from app.models import Chunk, Content, EvalResult, EvalRun

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class FakeJudge:
    """Content-scripted judge: a claim is unsupported iff it contains a marker.

    `flip_after` makes the judge non-deterministic on purpose (the self-consistency probe): once
    that many calls have been made, every verdict inverts.
    """

    unsupported_markers: tuple[str, ...] = ()
    flip_after: int | None = None
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append((claim_text, tuple(chunk_texts)))
        verdict = not any(m in claim_text for m in self.unsupported_markers)
        if self.flip_after is not None and len(self.calls) > self.flip_after:
            return not verdict
        return verdict


def _label(
    answer: str, *, verdict: bool | None = None, chunks: list[str] | None = None
) -> JudgeLabel:
    return JudgeLabel(
        question="q?",
        answer=answer,
        chunks=["chunk one", "chunk two"] if chunks is None else chunks,
        human_verdict=verdict,
        labeller="test",
    )


# --- kappa -------------------------------------------------------------------


def test_kappa_is_one_for_perfect_agreement_with_both_classes_present() -> None:
    assert cohen_kappa([True, False, True, False], [True, False, True, False]) == pytest.approx(1.0)


def test_kappa_is_zero_for_chance_level_agreement() -> None:
    judge = [True, True, False, False]
    human = [True, False, True, False]

    assert cohen_kappa(judge, human) == pytest.approx(0.0)


def test_kappa_is_negative_when_the_raters_systematically_disagree() -> None:
    assert cohen_kappa([True, True, False, False], [False, False, True, True]) < 0


def test_kappa_is_one_when_both_raters_are_constant_and_agree() -> None:
    assert cohen_kappa([True, True], [True, True]) == pytest.approx(1.0)


@pytest.mark.parametrize("judge, human", [([], []), ([True], [True, False])])
def test_kappa_rejects_empty_or_mismatched_inputs(judge: list[bool], human: list[bool]) -> None:
    with pytest.raises(ValueError):
        cohen_kappa(judge, human)


# --- judging one labelled row ------------------------------------------------


def test_judge_answer_requires_every_sentence_to_be_supported() -> None:
    judge = FakeJudge(unsupported_markers=("BAD",))

    assert judge_answer(judge, "One fine claim. Another fine claim.", ["c"]) is True
    assert judge_answer(judge, "One fine claim. BAD invented claim.", ["c"]) is False


# --- self-consistency --------------------------------------------------------


def test_self_consistency_is_one_for_a_deterministic_judge() -> None:
    labels = [_label("A claim."), _label("Another claim.")]

    assert self_consistency(FakeJudge(), labels, repeats=3) == pytest.approx(1.0)


def test_self_consistency_falls_when_the_judge_flips_between_repeats() -> None:
    """`flip_after=1` flips the judge partway through the FIRST row's three repeats, so that row
    is inconsistent while the second (judged entirely post-flip) stays self-consistent."""
    labels = [_label("A claim."), _label("Another claim.")]

    value = self_consistency(FakeJudge(flip_after=1), labels, repeats=3)

    assert value == pytest.approx(0.5)


# --- spot check --------------------------------------------------------------


def test_spotcheck_reports_full_consistency_for_an_unbiased_judge() -> None:
    labels = [_label("A claim."), _label("Another claim.")]

    result = position_verbosity_spotcheck(FakeJudge(), labels, sample=10)

    assert result.sampled == 2
    assert result.position_consistency == pytest.approx(1.0)
    assert result.verbosity_consistency == pytest.approx(1.0)


def test_spotcheck_skips_position_probe_for_rows_with_under_two_chunks() -> None:
    labels = [_label("A claim.", chunks=["only one"])]

    result = position_verbosity_spotcheck(FakeJudge(), labels, sample=10)

    assert result.position_consistency is None
    assert result.verbosity_consistency == pytest.approx(1.0)


# --- whole scorecard ---------------------------------------------------------


def test_scorecard_reports_agreement_and_kappa_over_labelled_rows_only() -> None:
    labels = [
        _label("A fine claim.", verdict=True),
        _label("BAD invented claim.", verdict=False),
        _label("Unlabelled claim.", verdict=None),
    ]

    card = score_judge(FakeJudge(unsupported_markers=("BAD",)), labels, repeats=3, sample=10)

    assert card.labelled == 2
    assert card.agreement == pytest.approx(1.0)
    assert card.kappa == pytest.approx(1.0)
    assert card.self_consistency == pytest.approx(1.0)
    assert card.repeats == 3


def test_scorecard_reports_none_for_kappa_when_nothing_is_labelled_yet() -> None:
    labels = [_label("A claim.", verdict=None)]

    card = score_judge(FakeJudge(), labels)

    assert card.labelled == 0
    assert card.agreement is None
    assert card.kappa is None
    assert card.self_consistency == pytest.approx(1.0)


# --- the committed label file ------------------------------------------------


def test_committed_judge_labels_file_loads_and_is_usable() -> None:
    labels = load_judge_labels(_REPO_ROOT / "seed" / "judge_labels.yaml")

    assert len(labels) >= 4
    verdicts = {label.human_verdict for label in labels}
    assert True in verdicts and False in verdicts
    assert all(label.question.strip() and label.answer.strip() for label in labels)


@pytest.mark.parametrize(
    "item, fragment",
    [
        ({"answer": "a", "chunks": [], "human_verdict": "supported", "labeller": "x"}, "question"),
        ({"question": "q", "chunks": [], "human_verdict": "supported", "labeller": "x"}, "answer"),
        (
            {
                "question": "q",
                "answer": "a",
                "chunks": "not-a-list",
                "human_verdict": "supported",
                "labeller": "x",
            },
            "chunks",
        ),
        (
            {
                "question": "q",
                "answer": "a",
                "chunks": [],
                "human_verdict": "maybe",
                "labeller": "x",
            },
            "human_verdict",
        ),
        (
            {
                "question": "q",
                "answer": "a",
                "chunks": [],
                "human_verdict": None,
                "labeller": "x",
                "extra": 1,
            },
            "unknown",
        ),
    ],
)
def test_invalid_label_records_raise_value_error(
    tmp_path: Path, item: dict[str, object], fragment: str
) -> None:
    path = tmp_path / "judge_labels.yaml"
    path.write_text(yaml.safe_dump([item], sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_judge_labels(path)

    assert fragment in str(excinfo.value)


def test_export_pending_writes_sampled_rows_with_real_chunk_texts(
    db_session: Session, tmp_path: Path
) -> None:
    """`--export-pending` turns the latest answer run into a labelling worksheet."""
    content = Content(
        title="Roth IRA Conversion Basics",
        slug="roth-ira-conversion-basics",
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.flush()
    chunk = Chunk(content_id=content.id, chunk_index=0, text="Converting is a taxable event.")
    db_session.add(chunk)
    db_session.flush()

    run = EvalRun(
        label="baseline",
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        judge_model="gpt-4o",
        similarity_threshold=0.5,
        retrieval_k=6,
        corpus_content_count=1,
        corpus_chunk_count=1,
        corpus_max_updated_at=datetime.now(UTC),
        corpus_digest="abc",
        total_questions=1,
        pct_fully_supported=100.0,
        refusal_correct=0,
        refusal_total=0,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        EvalResult(
            run_id=run.id,
            question="What is a Roth IRA conversion?",
            answerable=True,
            expected_slugs=["roth-ira-conversion-basics"],
            cited_slugs=["roth-ira-conversion-basics"],
            slugs_hit=True,
            fully_supported=True,
            refused=False,
            verdict="PASS",
            top_similarity=0.81,
            answer_text="Converting is a taxable event.",
            metrics={"retrieved_chunk_ids": [str(chunk.id), str(uuid.uuid4())]},
        )
    )
    db_session.flush()

    out = export_pending(db_session, count=5, out_path=tmp_path / "judge_labels.pending.yaml")

    rows = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["question"] == "What is a Roth IRA conversion?"
    assert rows[0]["answer"] == "Converting is a taxable event."
    assert rows[0]["chunks"] == ["Converting is a taxable event."]  # the stale id was dropped
    assert rows[0]["human_verdict"] is None
    assert rows[0]["labeller"] == ""
