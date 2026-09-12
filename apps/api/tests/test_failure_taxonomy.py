"""Failure taxonomy pins (phase-9 task-06, DESIGN "Diagnosis" row)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from app.eval.taxonomy import (
    CORPUS_GAP,
    FAILURE_CAUSES,
    GENERATION_UNFAITHFUL,
    JUDGE_DISAGREEMENT,
    NEAR_MISS_BAND,
    PROPOSAL_KIND_BY_CAUSE,
    RETRIEVAL_MISS,
    THRESHOLD_REFUSAL,
    classify_failure,
    failure_distribution,
)

_THRESHOLD = 0.5


@dataclass(frozen=True)
class Row:
    answerable: bool = True
    refused: bool = False
    verdict: str = "FAIL"
    fully_supported: bool | None = False
    top_similarity: float | None = 0.8
    cited_slugs: list[str] = field(default_factory=lambda: ["a"])


def _classify(row: Row, *, hits: int = 0, human: bool | None = None) -> str | None:
    return classify_failure(
        row, threshold=_THRESHOLD, expected_chunk_hits=hits, human_verdict=human
    )


def test_a_passing_row_has_no_cause() -> None:
    assert _classify(Row(verdict="PASS", fully_supported=True), hits=1) is None


def test_expected_chunk_missing_from_top_k_is_retrieval_miss() -> None:
    row = Row(refused=False, fully_supported=True, cited_slugs=["wrong-article"])

    assert _classify(row, hits=0) == RETRIEVAL_MISS


def test_refusal_with_nothing_close_is_a_corpus_gap() -> None:
    row = Row(refused=True, fully_supported=None, top_similarity=0.31, cited_slugs=[])

    assert _THRESHOLD - NEAR_MISS_BAND == pytest.approx(0.35)
    assert _classify(row) == CORPUS_GAP


def test_refusal_with_no_similarity_at_all_is_a_corpus_gap() -> None:
    row = Row(refused=True, fully_supported=None, top_similarity=None, cited_slugs=[])

    assert _classify(row) == CORPUS_GAP


def test_refusal_just_under_the_threshold_is_a_threshold_refusal() -> None:
    row = Row(refused=True, fully_supported=None, top_similarity=0.46, cited_slugs=[])

    assert _classify(row) == THRESHOLD_REFUSAL


def test_context_present_but_unsupported_answer_is_generation_unfaithful() -> None:
    row = Row(refused=False, fully_supported=False, cited_slugs=["a"])

    assert _classify(row, hits=1) == GENERATION_UNFAITHFUL


def test_an_off_domain_question_that_got_answered_is_a_threshold_refusal() -> None:
    row = Row(answerable=False, refused=False, fully_supported=None, cited_slugs=["distractor"])

    assert _classify(row) == THRESHOLD_REFUSAL


def test_human_label_contradicting_the_judge_outranks_every_other_cause() -> None:
    row = Row(refused=True, fully_supported=False, top_similarity=0.2, cited_slugs=[])

    assert _classify(row, human=True) == JUDGE_DISAGREEMENT


def test_human_label_agreeing_with_the_judge_does_not_shadow_the_real_cause() -> None:
    row = Row(refused=False, fully_supported=False, cited_slugs=["a"])

    assert _classify(row, hits=1, human=False) == GENERATION_UNFAITHFUL


def test_distribution_counts_causes_in_taxonomy_order_and_drops_none() -> None:
    causes = [CORPUS_GAP, None, GENERATION_UNFAITHFUL, CORPUS_GAP, None]

    distribution = failure_distribution(causes)

    assert list(distribution) == [CORPUS_GAP, GENERATION_UNFAITHFUL]
    assert distribution == {CORPUS_GAP: 2, GENERATION_UNFAITHFUL: 1}


def test_every_cause_maps_to_a_proposal_kind_or_explicitly_to_none() -> None:
    assert set(PROPOSAL_KIND_BY_CAUSE) == set(FAILURE_CAUSES)
    assert PROPOSAL_KIND_BY_CAUSE[CORPUS_GAP] == "new_article"
    assert PROPOSAL_KIND_BY_CAUSE[GENERATION_UNFAITHFUL] == "expand_article"
    assert PROPOSAL_KIND_BY_CAUSE[RETRIEVAL_MISS] == "retune"
    assert PROPOSAL_KIND_BY_CAUSE[THRESHOLD_REFUSAL] == "retune"
    assert PROPOSAL_KIND_BY_CAUSE[JUDGE_DISAGREEMENT] is None
