---
id: p9-t08
phase: phase-9-eval-data-loop
depends_on: [p9-t05]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 08 — Judge scorecard: κ vs human labels, self-consistency, position/verbosity spot-check

## Goal

The judge stops being taken on faith. `python -m app.eval.judge_scorecard` reports Cohen's κ and
raw agreement against human-labelled rows (`seed/judge_labels.yaml`), self-consistency over three
repeat judgements, and a position/verbosity spot-check — one report, no new dependency (κ is
implemented inline; **no sklearn**). Because the 40 human labels come from a separate labelling
session (owner + Abhishek), the same module writes the unlabelled rows out for them:
`--export-pending N` samples N `(question, answer, chunks)` rows from the latest persisted
answer-eval run into `seed/judge_labels.pending.yaml`. Until labels exist the scorecard reports
self-consistency only (INDEX plan-time ruling).

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Evaluation approach" (Judge row: agreement with
  ~40 human labels, target κ ≥ 0.8, self-consistency ×3, position/verbosity spot-check), §B2
  (`judge_labels.yaml`'s fields), D7.
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` §"Plan-time rulings" (the pending-export flow).
- `apps/api/app/eval/groundedness.py` post-task-05: `GroundednessJudge.is_supported`,
  `OpenAIJudge` (incl. `from_settings` now reading `settings.judge_model`), and the
  "fully supported = every sentence supported" definition in `_evaluate_question`.
- `apps/api/app/eval/metrics.py` (task 05) — `split_sentences`; and the `metrics` payload key
  `retrieved_chunk_ids`, which is what makes the pending export able to show real chunk texts.
- `apps/api/app/models/eval.py` (task 01) — `EvalRun.kind`, `EvalResult.question/answer_text/
  metrics`.
- `apps/api/app/services/eval_runs.py` (task 03) — `latest_runs`.
- `apps/api/app/models/chunks.py:41-47` — `Chunk.id/text`.

## Files

**Create**
- `seed/judge_labels.yaml` (the committed file starts as a small, honestly-labelled seed: **4
  rows**, hand-written below, so the loader and κ have real data; the remaining ~36 arrive from
  the labelling session through `--export-pending`)
- `apps/api/app/eval/judge_scorecard.py`
- `apps/api/tests/test_judge_scorecard.py`

**Modify** — none.

## Interfaces

### `seed/judge_labels.yaml` — schema and the four seed rows

Top-level list; each item: `question` (str) · `answer` (str) · `chunks` (list of str, may be
empty) · `human_verdict` (`supported` | `unsupported` | `null` — null = not yet labelled) ·
`labeller` (str, `""` when unlabelled). Unknown keys are an error.

```yaml
# Human-labelled judge calibration rows (phase-9 DESIGN §B2, Judge row).
# `human_verdict`: does the ANSWER stay inside what the `chunks` actually say?
# Rows with `human_verdict: null` are pending — see `--export-pending`.

- question: "What is a Roth IRA conversion and how is it taxed?"
  answer: "A Roth IRA conversion moves money from a traditional IRA to a Roth IRA, and the
    converted amount is taxed as ordinary income in the year of the conversion."
  chunks:
    - "A Roth IRA conversion moves funds from a traditional IRA into a Roth IRA. The converted
      amount is included in your ordinary income for the year of the conversion."
  human_verdict: supported
  labeller: "akanksha"

- question: "What is a Roth IRA conversion and how is it taxed?"
  answer: "A Roth IRA conversion is taxed as ordinary income, and it also guarantees a higher
    retirement income than leaving the money in a traditional IRA."
  chunks:
    - "A Roth IRA conversion moves funds from a traditional IRA into a Roth IRA. The converted
      amount is included in your ordinary income for the year of the conversion."
  human_verdict: unsupported
  labeller: "akanksha"

- question: "How does dollar-cost averaging work?"
  answer: "Dollar-cost averaging invests a fixed amount on a fixed schedule, regardless of whether
    the market is up or down."
  chunks:
    - "Dollar-cost averaging (DCA) is the practice of investing a fixed amount of money at regular
      intervals — say, monthly — regardless of whether the market is up or down."
  human_verdict: supported
  labeller: "akanksha"

- question: "What does the firm recommend about cryptocurrency staking rewards?"
  answer: "Staking rewards are taxed as ordinary income when you gain control of them."
  chunks: []
  human_verdict: unsupported
  labeller: "akanksha"
```

### `app/eval/judge_scorecard.py`

```python
@dataclass(frozen=True)
class JudgeLabel:
    question: str
    answer: str
    chunks: list[str]
    human_verdict: bool | None   # True == "supported"
    labeller: str


@dataclass(frozen=True)
class SpotCheck:
    sampled: int
    position_consistency: float | None   # None when `sampled == 0`
    verbosity_consistency: float | None


@dataclass(frozen=True)
class JudgeScorecard:
    labelled: int
    agreement: float | None          # None when there are no human labels yet
    kappa: float | None
    self_consistency: float | None   # None when there are no rows at all
    repeats: int
    spot_check: SpotCheck


def load_judge_labels(path: Path) -> list[JudgeLabel]:
    """Raises ValueError on: a non-list file, a non-mapping item, a missing/mistyped required key,
    an unknown key, or a `human_verdict` outside {supported, unsupported, null}."""


def judge_answer(judge: GroundednessJudge, answer: str, chunks: Sequence[str]) -> bool:
    """The harness's own "fully supported" definition, reused verbatim: every sentence of `answer`
    (via `app.eval.metrics.split_sentences`) must be supported by the union of `chunks`. An empty
    answer is `True` (nothing unsupported was said) — stated here because it is the one edge the
    harness never hits."""


def cohen_kappa(judge_calls: Sequence[bool], human_calls: Sequence[bool]) -> float:
    """Cohen's κ for two binary raters, implemented inline (no sklearn — DESIGN: no new deps).

        po = fraction of rows the two raters agree on
        pe = p_j·p_h + (1 - p_j)·(1 - p_h)      (p_x = that rater's "supported" rate)
        κ  = (po - pe) / (1 - pe),  and 1.0 when pe == 1.0 (both raters constant and agreeing)

    Raises:
        ValueError: the sequences are empty or differ in length.
    """


def self_consistency(
    judge: GroundednessJudge, labels: Sequence[JudgeLabel], *, repeats: int = 3
) -> float | None:
    """Fraction of rows whose `repeats` independent judgements are all identical.

    Iteration order is pinned: **row-by-row, repeats as the inner loop** (`for label: for _ in
    range(repeats)`), not repeats-outer. The order is observable through a stateful judge and one
    test depends on it. `None` when `labels` is empty.
    """


def position_verbosity_spotcheck(
    judge: GroundednessJudge, labels: Sequence[JudgeLabel], *, sample: int = 10
) -> SpotCheck:
    """Two bias probes over the first `sample` rows (file order — deterministic, no RNG):

    - **position**: judge the answer against `chunks`, then against `list(reversed(chunks))`;
      `position_consistency` = fraction where the verdict did not move. A row with fewer than two
      chunks is skipped for this probe (reversal is a no-op).
    - **verbosity**: judge the answer, then judge `answer + " " + split_sentences(answer)[0]` —
      the answer with its OWN first sentence restated, so nothing new is claimed and a calibrated
      judge's verdict must not move. `verbosity_consistency` = fraction where it did not.
    """


def score_judge(
    judge: GroundednessJudge,
    labels: Sequence[JudgeLabel],
    *,
    repeats: int = 3,
    sample: int = 10,
) -> JudgeScorecard: ...


def export_pending(
    session: Session, *, count: int, out_path: Path, seed: int = 0
) -> Path:
    """Write `count` unlabelled rows from the latest `kind='answer'` run to `out_path`.

    Rows are sampled with `random.Random(seed).sample(...)` over that run's `eval_results`
    ordered by `question` (deterministic given a run), skipping rows with an empty `answer_text`.
    Chunk texts come from `metrics["retrieved_chunk_ids"]` resolved against `chunks.id`; ids that
    no longer resolve (the corpus was re-chunked since) are dropped, and a row whose ids all fail
    is exported with `chunks: []` — an honest "the judge saw nothing" row a labeller can still
    label. Emits `human_verdict: null` and `labeller: ""` for every row.

    Raises:
        NotFoundError: there is no persisted `kind='answer'` run to sample from.
    """
```

**CLI** — `python -m app.eval.judge_scorecard [--labels PATH] [--repeats 3] [--sample 10]
[--export-pending N] [--out PATH]`.
- With `--export-pending N`: open a session from `Settings().database_url`, call `export_pending`
  (default `--out` = `seed/judge_labels.pending.yaml` via `seed_data_dir()`), print the path and
  row count, and **exit without calling the judge** (the export is a DB job, not a judging job).
- Otherwise: load labels (default `seed_data_dir() / "judge_labels.yaml"`), build
  `OpenAIJudge.from_settings(Settings())`, run `score_judge`, and print:

```
judge scorecard (model=gpt-4o, labels=4 labelled / 4 total)
  agreement              100.0%
  cohen's kappa          1.00   (target >= 0.80)
  self-consistency x3    100.0%
  position consistency   100.0% (n=3)
  verbosity consistency  100.0% (n=4)
```

  A `None` metric prints as `n/a (no human labels yet)` — the state the INDEX ruling describes
  until the labelling session lands.

## Steps (TDD)

- [ ] **RED — test-author.** Create `apps/api/tests/test_judge_scorecard.py`:

```python
"""Judge scorecard pins (phase-9 task-08, DESIGN "Judge" row)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from app.eval.judge_scorecard import (
    JudgeLabel,
    cohen_kappa,
    judge_answer,
    load_judge_labels,
    position_verbosity_spotcheck,
    score_judge,
    self_consistency,
)

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
def test_kappa_rejects_empty_or_mismatched_inputs(
    judge: list[bool], human: list[bool]
) -> None:
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
            {"question": "q", "answer": "a", "chunks": "not-a-list",
             "human_verdict": "supported", "labeller": "x"},
            "chunks",
        ),
        (
            {"question": "q", "answer": "a", "chunks": [], "human_verdict": "maybe",
             "labeller": "x"},
            "human_verdict",
        ),
        (
            {"question": "q", "answer": "a", "chunks": [], "human_verdict": None,
             "labeller": "x", "extra": 1},
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
```

  Plus one DB test for the exporter, appended to the same file:

```python
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
    assert rows[0]["chunks"] == ["Converting is a taxable event."]   # the stale id was dropped
    assert rows[0]["human_verdict"] is None
    assert rows[0]["labeller"] == ""
```

  (this second block needs `import uuid`, `from datetime import UTC, datetime`,
  `from sqlalchemy.orm import Session`, `from app.models import Chunk, Content, EvalResult,
  EvalRun`, and `export_pending` added to the module import.)

- [ ] **Run RED:** `cd apps/api && TEST_DATABASE_URL=… uv run pytest tests/test_judge_scorecard.py
  -q` → all fail on `ModuleNotFoundError: app.eval.judge_scorecard` and the missing
  `seed/judge_labels.yaml`.

- [ ] **GREEN — implementer.** Write `seed/judge_labels.yaml` (the four rows above, verbatim) and
  `app/eval/judge_scorecard.py` per Interfaces. Every judge call goes through the injected
  `GroundednessJudge` seam — no direct OpenAI construction outside `_run_from_cli`.

- [ ] **Run GREEN:** `uv run pytest tests/test_judge_scorecard.py -q`, then `uv run pytest -q`.

- [ ] **Real run (evidence):** against the seeded local stack with the real `gpt-4o` judge,
  `uv run python -m app.eval.judge_scorecard` → paste the printed scorecard into the implementer
  report. Then `uv run python -m app.eval.judge_scorecard --export-pending 40` → confirm
  `seed/judge_labels.pending.yaml` is written with 40 rows (or the run's row count, if fewer) and
  is **not** committed (add it to `.gitignore` only if the repo does not already ignore it —
  otherwise leave it untracked and say so).

- [ ] **Gates:** `pnpm gates:api` (incl. `lint-imports`).

- [ ] **Commit:** `git commit -m "feat(api): judge scorecard (kappa, self-consistency, spot-check) (p9 t08)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=… uv run pytest tests/test_judge_scorecard.py -q
pnpm gates:api
```

## Acceptance

- κ is computed inline and matches the four pinned cases (perfect, chance, systematic
  disagreement, constant-and-agreeing) and rejects empty/mismatched input; **no sklearn, no new
  dependency in `pyproject.toml`**.
- `judge_answer` reuses the harness's "every sentence supported" definition rather than inventing
  a second one.
- Self-consistency detects a flipping judge; the spot-check skips the position probe on
  single-chunk rows and uses the answer's own first sentence as the verbosity padding.
- With no human labels, `agreement`/`kappa` are `None` and the CLI prints `n/a (no human labels
  yet)` — the INDEX-ruled interim state.
- `--export-pending N` writes a valid, loadable worksheet with `human_verdict: null`, real chunk
  texts where the ids still resolve, and stale ids dropped rather than crashing.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-08-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-08-implementer.md`
