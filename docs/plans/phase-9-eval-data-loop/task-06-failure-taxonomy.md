---
id: p9-t06
phase: phase-9-eval-data-loop
depends_on: [p9-t05]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 06 — Failure taxonomy: one cause per failed question

## Goal

Every failed eval row gets a machine-assigned cause — `retrieval_miss` · `corpus_gap` ·
`threshold_refusal` · `generation_unfaithful` · `judge_disagreement` — computed by one pure
function from signals already in hand, stored in `eval_results.metrics["failure_cause"]` (no
migration), summarised as a distribution under the printed report, and mapped 1:1 onto the
proposal kinds task 16 will create. This is what turns "10 of 17 failed" into "6 of them are a
corpus gap, 4 are the model going beyond its sources" — the slide the talk needs.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Evaluation approach" (the Diagnosis row: the
  five causes and their 1:1 mapping onto `new_article`/`expand_article`/`retune`) and §D (the
  `threshold - 0.15` near-miss band used by weak-query classification).
- `apps/api/app/eval/groundedness.py` post-task-05: `EvalRow` (fields `answerable`, `slugs_hit`,
  `fully_supported`, `refused`, `verdict`, `top_similarity`, `metrics`), `_evaluate_question`,
  `_build_report`, `_print_report`.
- `apps/api/app/eval/metrics.py` (task 05) — `RetrievalMetrics.hits` is the `expected_chunk_hits`
  argument below.
- `apps/api/app/config.py:176` — `similarity_threshold: float = 0.5` (the `threshold` argument).
- `apps/api/app/services/eval_runs.py` (task 03) — `metrics` is persisted verbatim.

## Files

**Create**
- `apps/api/app/eval/taxonomy.py`
- `apps/api/tests/test_failure_taxonomy.py`

**Modify**
- `apps/api/app/eval/groundedness.py` (call the classifier; print the distribution)

## Interfaces

### `app/eval/taxonomy.py` (pure — no DB, no network, no `Settings`)

```python
RETRIEVAL_MISS = "retrieval_miss"
CORPUS_GAP = "corpus_gap"
THRESHOLD_REFUSAL = "threshold_refusal"
GENERATION_UNFAITHFUL = "generation_unfaithful"
JUDGE_DISAGREEMENT = "judge_disagreement"

FAILURE_CAUSES: tuple[str, ...] = (
    RETRIEVAL_MISS, CORPUS_GAP, THRESHOLD_REFUSAL, GENERATION_UNFAITHFUL, JUDGE_DISAGREEMENT,
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
) -> str | None: ...


def failure_distribution(causes: Iterable[str | None]) -> dict[str, int]: ...
```

**Decision table for `classify_failure` — first match wins, in this order:**

| # | Condition | Result |
|---|---|---|
| 1 | `human_verdict is not None` and `row.fully_supported is not None` and `human_verdict != row.fully_supported` | `judge_disagreement` (a human label contradicting the judge is a *judge* problem whatever else is true, so it outranks everything) |
| 2 | `row.verdict == "PASS"` | `None` (nothing failed) |
| 3 | `row.answerable is False` | `threshold_refusal` — an off-domain question that got answered means a distractor cleared the threshold; DESIGN calls threshold "the retune class" |
| 4 | `not row.refused` and `expected_chunk_hits == 0` | `retrieval_miss` — retrieval returned chunks, but not the expected ones |
| 5 | `row.refused` and (`row.top_similarity is None` or `row.top_similarity < threshold - NEAR_MISS_BAND`) | `corpus_gap` — nothing in the corpus is even close |
| 6 | `row.refused` | `threshold_refusal` — a relevant chunk existed but scored under the threshold |
| 7 | `row.cited_slugs` non-empty and `row.fully_supported is False` | `generation_unfaithful` — context was present, the answer went beyond it |
| 8 | otherwise | `retrieval_miss` — a FAIL with hits but a faithful answer can only be unmet slug-level coverage |

`failure_distribution` counts non-`None` causes, returns a dict ordered by `FAILURE_CAUSES`,
omitting zero-count causes.

### `app/eval/groundedness.py`

- `_evaluate_question` computes the cause right after the metrics dict is built:

```python
    failure_cause = classify_failure(
        row_without_cause,
        threshold=settings.similarity_threshold,
        expected_chunk_hits=metrics.hits,
    )
    row_metrics["failure_cause"] = failure_cause
```

  (build the `EvalRow` once the metrics dict is complete — construct the dict, classify using the
  already-computed local values, then construct the frozen row; do **not** mutate a frozen row.)
  `human_verdict` stays `None` at run time — human labels arrive offline through task 08's
  scorecard, which reads the persisted rows.
- `_print_report` prints, after the per-class rollup block, when any cause is present:

```
failure causes:
  corpus_gap                6
  generation_unfaithful     4
  threshold_refusal         1
```

  Format: `f"  {cause:<24} {count:>3}"`, in `FAILURE_CAUSES` order.
- `EvalReport` gains `failure_causes: dict[str, int] = field(default_factory=dict)` (defaulted, so
  earlier constructions still work), filled by `_build_report` from each row's
  `metrics["failure_cause"]`.

## Steps (TDD)

- [ ] **RED — test-author.** Create `apps/api/tests/test_failure_taxonomy.py`:

```python
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
```

  Then add one integration pin to `apps/api/tests/test_eval_metrics.py` (the file task 05
  created), reusing its `ScriptedEmbedder`/`ScriptedChatLLM`/`FakeMetricsJudge`:

```python
def test_run_eval_stores_a_failure_cause_on_every_failed_row(
    db_session: Session, tmp_path: Path
) -> None:
    """A question the corpus cannot answer at all is recorded as a `corpus_gap`."""
    question = "How is crypto compensation taxed?"
    path = tmp_path / "eval_questions.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "question": question,
                    "expected_slugs": ["crypto-compensation"],
                    "answerable": True,
                    "class": "near_miss",
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report = run_eval(
        db_session,
        embedder=ScriptedEmbedder(vectors={question: _unit_vector(0)}),
        chat_llm=ScriptedChatLLM(answers={question: "No published guidance covers this."}),
        judge=FakeMetricsJudge(),
        questions_path=path,
    )

    row = report.rows[0]
    assert row.verdict == "FAIL"
    assert row.metrics is not None
    assert row.metrics["failure_cause"] == "corpus_gap"
    assert report.failure_causes == {"corpus_gap": 1}
```

- [ ] **Run RED:** `cd apps/api && TEST_DATABASE_URL=… uv run pytest tests/test_failure_taxonomy.py
  tests/test_eval_metrics.py -q` → the taxonomy module is missing (`ModuleNotFoundError`) and the
  integration pin fails on `KeyError: 'failure_cause'`.

- [ ] **GREEN — implementer.** Create `app/eval/taxonomy.py` implementing the decision table
  exactly in order (one `if` per row, each with the table's row number in a comment), then wire
  it into `_evaluate_question`, `_build_report` (`failure_causes`) and `_print_report`.

- [ ] **Run GREEN:** the two test files, then `uv run pytest -q`.

- [ ] **Gates:** `pnpm gates:api` (incl. `lint-imports`).

- [ ] **Commit:** `git commit -m "feat(api): failure taxonomy per failed eval row (p9 t06)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=… uv run pytest tests/test_failure_taxonomy.py tests/test_eval_metrics.py -q
pnpm gates:api
```

## Acceptance

- Every row of the decision table is covered by a passing test, in the pinned precedence order
  (notably: a human disagreement outranks everything; an agreeing human label changes nothing).
- `NEAR_MISS_BAND` is defined once here and reused (not re-typed) by task 15's weak-query
  classifier.
- `failure_cause` lands in `eval_results.metrics` through task 03's `record_run` — no migration.
- The printed report gains a `failure causes:` block; the phase-7 table and summary line above it
  are still byte-identical.
- `PROPOSAL_KIND_BY_CAUSE` covers all five causes, with `judge_disagreement` explicitly mapping to
  `None`.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-06-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-06-implementer.md`
