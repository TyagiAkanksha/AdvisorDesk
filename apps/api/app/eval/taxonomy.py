"""Failure taxonomy (phase-9 task-06, DESIGN "Diagnosis" row): one machine-assigned cause per
failed eval row, computed by a single pure function from signals already in hand.

Pure — no DB, no network, no `Settings` (mirrors `app.eval.metrics`'s own module docstring
rationale) — so `classify_failure` is unit-testable with plain values and
`app.eval.groundedness` (which DOES touch the DB/network/`Settings`) can import from this module
without this module ever importing back.

Spec: `docs/plans/phase-9-eval-data-loop/task-06-failure-taxonomy.md` Interfaces (the decision
table) and DESIGN.md's "Evaluation approach" (the Diagnosis row) / §D (the near-miss band).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

RETRIEVAL_MISS = "retrieval_miss"
CORPUS_GAP = "corpus_gap"
THRESHOLD_REFUSAL = "threshold_refusal"
GENERATION_UNFAITHFUL = "generation_unfaithful"
JUDGE_DISAGREEMENT = "judge_disagreement"

FAILURE_CAUSES: tuple[str, ...] = (
    RETRIEVAL_MISS,
    CORPUS_GAP,
    THRESHOLD_REFUSAL,
    GENERATION_UNFAITHFUL,
    JUDGE_DISAGREEMENT,
)

# DESIGN §D: the same band that separates `refused` from `near_miss` in weak-query
# classification (task 15) — defined once here so the two never drift apart.
NEAR_MISS_BAND: float = 0.15

# DESIGN "Diagnosis" row: the taxonomy maps 1:1 onto `content_proposals.kind` (task 16).
# `judge_disagreement` maps to no proposal: the fix is judge calibration (task 08), not content.
PROPOSAL_KIND_BY_CAUSE: dict[str, str | None] = {
    RETRIEVAL_MISS: "retune",
    CORPUS_GAP: "new_article",
    THRESHOLD_REFUSAL: "retune",
    GENERATION_UNFAITHFUL: "expand_article",
    JUDGE_DISAGREEMENT: None,
}


class ClassifiableRow(Protocol):
    """The subset of `EvalRow` the classifier reads (structural, like every other seam here)."""

    @property
    def answerable(self) -> bool: ...
    @property
    def refused(self) -> bool: ...
    @property
    def verdict(self) -> str: ...
    @property
    def fully_supported(self) -> bool | None: ...
    @property
    def top_similarity(self) -> float | None: ...
    @property
    def cited_slugs(self) -> Sequence[str]: ...


def classify_failure(
    row: ClassifiableRow,
    *,
    threshold: float,
    expected_chunk_hits: int,
    human_verdict: bool | None = None,
) -> str | None:
    """Assign one failure cause to `row`, or `None` when it did not fail.

    First match wins, in the pinned decision-table order (task file Interfaces) — each branch
    below carries its own row number.
    """
    # Row 1: a human label contradicting the judge is a *judge* problem whatever else is true, so
    # it outranks everything.
    if (
        human_verdict is not None
        and row.fully_supported is not None
        and human_verdict != row.fully_supported
    ):
        return JUDGE_DISAGREEMENT

    # Row 2: nothing failed.
    if row.verdict == "PASS":
        return None

    # Row 3: an off-domain question that got answered means a distractor cleared the threshold —
    # DESIGN calls threshold "the retune class".
    if row.answerable is False:
        return THRESHOLD_REFUSAL

    # Row 4: retrieval returned chunks, but not the expected ones.
    if not row.refused and expected_chunk_hits == 0:
        return RETRIEVAL_MISS

    # Row 5: nothing in the corpus is even close.
    if row.refused and (
        row.top_similarity is None or row.top_similarity < threshold - NEAR_MISS_BAND
    ):
        return CORPUS_GAP

    # Row 6: a relevant chunk existed but scored under the threshold.
    if row.refused:
        return THRESHOLD_REFUSAL

    # Row 7: context was present, the answer went beyond it.
    if row.cited_slugs and row.fully_supported is False:
        return GENERATION_UNFAITHFUL

    # Row 8: a FAIL with hits but a faithful answer can only be unmet slug-level coverage.
    return RETRIEVAL_MISS


def failure_distribution(causes: Iterable[str | None]) -> dict[str, int]:
    """Count non-`None` `causes`, returned as a dict ordered by `FAILURE_CAUSES`, omitting any
    cause with a zero count.
    """
    counts = {cause: 0 for cause in FAILURE_CAUSES}
    for cause in causes:
        if cause is not None:
            counts[cause] += 1
    return {cause: count for cause, count in counts.items() if count > 0}
