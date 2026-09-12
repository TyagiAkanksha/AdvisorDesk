---
id: p9-t05
phase: phase-9-eval-data-loop
depends_on: [p9-t04]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 05 — Metrics v2: recall@k / precision@k / MRR, three rubric judges, per-class rollups

## Goal

The harness stops reporting one number. Each row gains standard retrieval metrics computed by
pure math over `retrieve()`'s output (recall@k, precision@k, MRR — against resolved
`expected_chunks` when the question has them, else a slug-level fallback) and three new rubric
judges (answer relevance, context precision, context recall) alongside the existing per-sentence
faithfulness judge. The judge model becomes a setting of its own (`judge_model="gpt-4o"`, DESIGN
D7 — the answerer stays `gpt-4o-mini`). Every new number is persisted in
`eval_results.metrics` — **the JSONB column task 01 already created, so this task adds no
migration** — and the printed report gains a per-class rollup.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Evaluation approach" (the metric table) and D7.
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` §"Global Constraints" (judge determinism:
  every judge call `temperature=0`; zero-env settings; no new runtime dependencies).
- `apps/api/app/eval/groundedness.py` at its post-task-04 state: `_SENTENCE_BOUNDARY_RE` (line
  70), `EvalRow`, `GroundednessJudge` (106-126), `_JUDGE_SYSTEM_PROMPT` (132-137), `OpenAIJudge`
  (140-185), `_split_sentences` (188-195), `_dedupe_preserve_order` (198-200),
  `_evaluate_question`, `_build_report`, `run_eval`, `_print_table`, `_print_report`.
- `apps/api/app/eval/questions.py` (task 04) — `EvalQuestion.expected_chunks`/`reference_answer`,
  `resolve_expected_chunks`.
- `apps/api/app/rag/retrieval.py:38-53` — `RetrievedChunk{chunk_id, content_id, title, slug, text,
  similarity}`; `retrieve()`'s `k: int = 6`.
- `apps/api/app/config.py:118` (`chat_model`) and the zero-env rule in the class docstring
  (lines 44-50).
- `apps/api/tests/test_groundedness.py` — all seven tests must stay green **untouched**; its
  `ScriptedJudge` implements only `is_supported`, which is why the new judge seam is a separate,
  optional parameter (see Interfaces).
- `apps/api/app/services/eval_runs.py` (task 03) — `EvalRowLike.metrics` is already the carrier.

## Files

**Create**
- `apps/api/app/eval/metrics.py`
- `apps/api/tests/test_eval_metrics.py`

**Modify**
- `apps/api/app/config.py` (`judge_model`)
- `apps/api/app/eval/groundedness.py` (judge protocol + prompts, row metrics, rollups, printing)

**No migration.** `eval_results.metrics` (jsonb, nullable) already exists.

## Interfaces

### `app/eval/metrics.py` (pure — no DB, no network, no `Settings`)

```python
@dataclass(frozen=True)
class RetrievalMetrics:
    """Standard IR metrics for one question's retrieval (DESIGN "Retrieval" row)."""

    mode: str                  # "chunk" when expected_chunks resolved, else "slug"
    recall_at_k: float | None  # None when the question has no expected items (off-domain)
    precision_at_k: float | None
    mrr: float | None
    hits: int                  # |expected ∩ retrieved| — task 06's `expected_chunk_hits`


def retrieval_metrics(
    expected: Sequence[str], retrieved: Sequence[str], *, mode: str
) -> RetrievalMetrics:
    """recall@k / precision@k / MRR over two ordered id (or slug) sequences.

    - `recall_at_k`  = |E ∩ R| / |E|
    - `precision_at_k` = |E ∩ R| / |R|, and `0.0` when `R` is empty (a refusal retrieves nothing,
      which is zero precision, not undefined)
    - `mrr` = 1 / (1-based position of the first element of `R` that is in `E`), else `0.0`
    - `E` empty (an off-domain question) ⇒ every metric is `None` and `hits` is `0`: there is
      nothing to recall, and scoring it 0.0 would drag the corpus-wide means down for questions
      that are *supposed* to retrieve nothing.
    `R` is deduped preserving order before scoring (a content item with two retrieved chunks must
    not inflate precision's denominator twice at slug level).
    """


def split_sentences(text: str) -> list[str]:
    """Moved verbatim from `groundedness._split_sentences` (same regex, same docstring rationale)."""


def context_precision(
    judge: MetricsJudge, question: str, chunk_texts: Sequence[str]
) -> float | None:
    """Fraction of RETRIEVED chunks the judge deems relevant to `question`. `None` if none were
    retrieved."""


def context_recall(
    judge: MetricsJudge, reference_answer: str | None, chunk_texts: Sequence[str]
) -> float | None:
    """Fraction of the reference answer's sentences the judge deems covered by the retrieved
    context. `None` when there is no reference answer (or it splits to zero sentences); `0.0` when
    a reference answer exists but nothing was retrieved."""
```

`MetricsJudge` is declared in `groundedness.py` (next to `GroundednessJudge`) and imported into
`metrics.py` under `TYPE_CHECKING` — or, simpler and preferred: declare **both** protocols in
`metrics.py` and re-export `GroundednessJudge` from `groundedness.py` for back-compat
(`tests/test_groundedness.py` does not import it, so either is safe; pick one and say which).

```python
class MetricsJudge(Protocol):
    """The four rubric judges (DESIGN "Generation" row). `is_supported` is the existing
    faithfulness judge, restated here so one object can satisfy the whole seam."""

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...
    def is_answer_relevant(self, question: str, answer_text: str) -> bool: ...
    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool: ...
    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...
```

### `app/config.py`

```python
    # DESIGN D7 (2026-09-12): recorded eval numbers are judged by a STRONGER model than the
    # answerer (`chat_model`, gpt-4o-mini) — a same-family caveat the human-labelled scorecard
    # (task 08) covers. Zero-env constructible like every other setting (CONVENTIONS.md §5).
    judge_model: str = "gpt-4o"
```

`OpenAIJudge.from_settings` switches `model=settings.chat_model` → `model=settings.judge_model`
(line 166). **This moves the recorded groundedness number**; that is the intent (DESIGN D7), and
task 09's baseline is the first run under it.

### `app/eval/groundedness.py`

- `OpenAIJudge` grows a private `_ask(self, system: str, user: str) -> str` (one
  `chat.completions.create(model=self._model, temperature=0, messages=[…])`, returns the stripped
  content) and the three new methods, each with its own system prompt constant. Every prompt ends
  with: `"Reply with YES or NO on the first line, then one short line giving your reason."` and is
  parsed with `.strip().upper().startswith("YES")`; the reason line is parsed off and logged at
  DEBUG, never stored (no schema for it, and DESIGN does not ask for one).
  - `_ANSWER_RELEVANCE_PROMPT`: "You judge whether an ANSWER actually addresses the QUESTION
    asked. Ignore whether it is factually correct — that is judged separately. Answer NO if it
    answers a different question, or is a refusal to a question that was asked in good faith."
  - `_CONTEXT_PRECISION_PROMPT`: "You judge whether one SOURCE passage is relevant to answering
    the QUESTION. Relevant means a correct answer would plausibly draw on it."
  - `_CONTEXT_RECALL_PROMPT`: "You judge whether one CLAIM from a reference answer is covered by
    the SOURCE passages. Covered means the sources state it or directly entail it."
- `run_eval(..., metrics_judge: MetricsJudge | None = None)` — **new, optional, keyword-only.**
  When `None`, the three judged metrics are `None` and only the pure-math retrieval metrics are
  computed. This is what keeps `tests/test_groundedness.py`'s `ScriptedJudge` (which implements
  only `is_supported`) working untouched — a global-constraint stop rule.
- `_evaluate_question` gains `metrics_judge` and builds `EvalRow.metrics`:

```python
{
    "retrieval_mode": metrics.mode,
    "recall_at_k": metrics.recall_at_k,
    "precision_at_k": metrics.precision_at_k,
    "mrr": metrics.mrr,
    "expected_chunk_hits": metrics.hits,
    "retrieved_chunk_ids": [str(chunk.chunk_id) for chunk in retrieval.chunks],
    "answer_relevance": answer_relevance,     # bool | None
    "context_precision": context_precision_value,   # float | None
    "context_recall": context_recall_value,         # float | None
}
```

  Mode selection: `resolved = resolve_expected_chunks(session, question.expected_chunks)`; if
  `question.expected_chunks` **and** `resolved` are both non-empty → `mode="chunk"`,
  `expected=[str(cid) for cid in sorted(resolved, key=str)]`,
  `retrieved=[str(c.chunk_id) for c in retrieval.chunks]`. Otherwise `mode="slug"`,
  `expected=question.expected_slugs`, `retrieved=cited_slugs`.
- `EvalReport` gains `by_class: dict[str, ClassRollup] = field(default_factory=dict)` (a
  defaulted field, so task 03's four-argument constructions keep working):

```python
@dataclass(frozen=True)
class ClassRollup:
    question_class: str
    count: int
    passed: int
    pct_fully_supported: float      # over that class's answerable rows; 0.0 if none
    mean_recall_at_k: float | None  # mean over rows whose recall_at_k is not None
```

- `_print_report` prints, after the unchanged summary line, a rollup block (only when
  `report.by_class` is non-empty):

```
by class:
  class            n  pass  supported%  recall@k
  answerable      17    10        58.8      1.00
  near_miss       10     8         0.0      0.00
```

  Format: `f"  {name:<14} {count:>3} {passed:>5} {pct:>11.1f} {recall:>9}"` with `recall`
  rendered as `f"{value:.2f}"` or `"-"` when `None`.

## Steps (TDD)

- [ ] **RED — test-author.** Create `apps/api/tests/test_eval_metrics.py`:

```python
"""Metrics v2 (phase-9 task-05): pure IR math, the three rubric judges, per-class rollups."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
import yaml
from sqlalchemy.orm import Session

from app.config import Settings
from app.eval.groundedness import run_eval
from app.eval.metrics import context_precision, context_recall, retrieval_metrics, split_sentences
from app.models import Chunk, Content


# --- pure math ---------------------------------------------------------------


def test_recall_precision_and_mrr_on_a_perfect_retrieval() -> None:
    m = retrieval_metrics(["c1"], ["c1"], mode="chunk")

    assert (m.recall_at_k, m.precision_at_k, m.mrr, m.hits) == (1.0, 1.0, 1.0, 1)
    assert m.mode == "chunk"


def test_partial_recall_and_precision_with_the_relevant_chunk_second() -> None:
    m = retrieval_metrics(["c1", "c2"], ["x1", "c2", "x3"], mode="chunk")

    assert m.recall_at_k == pytest.approx(0.5)
    assert m.precision_at_k == pytest.approx(1 / 3)
    assert m.mrr == pytest.approx(0.5)
    assert m.hits == 1


def test_nothing_retrieved_is_zero_precision_and_zero_mrr() -> None:
    m = retrieval_metrics(["c1"], [], mode="chunk")

    assert (m.recall_at_k, m.precision_at_k, m.mrr, m.hits) == (0.0, 0.0, 0.0, 0)


def test_no_expected_items_yields_none_metrics() -> None:
    m = retrieval_metrics([], ["x1"], mode="slug")

    assert (m.recall_at_k, m.precision_at_k, m.mrr, m.hits) == (None, None, None, 0)


def test_duplicate_retrieved_slugs_do_not_inflate_the_precision_denominator() -> None:
    m = retrieval_metrics(["a"], ["a", "a", "b"], mode="slug")

    assert m.precision_at_k == pytest.approx(0.5)


# --- rubric judges -----------------------------------------------------------


@dataclass
class FakeMetricsJudge:
    """Content-scripted `MetricsJudge`: substrings decide each verdict, never call order."""

    unsupported_markers: tuple[str, ...] = ()
    irrelevant_answer_markers: tuple[str, ...] = ()
    irrelevant_chunk_markers: tuple[str, ...] = ()
    uncovered_markers: tuple[str, ...] = ()
    calls: list[tuple[str, str]] = field(default_factory=list)

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append(("is_supported", claim_text))
        return not any(m in claim_text for m in self.unsupported_markers)

    def is_answer_relevant(self, question: str, answer_text: str) -> bool:
        self.calls.append(("is_answer_relevant", answer_text))
        return not any(m in answer_text for m in self.irrelevant_answer_markers)

    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool:
        self.calls.append(("is_chunk_relevant", chunk_text))
        return not any(m in chunk_text for m in self.irrelevant_chunk_markers)

    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append(("is_claim_covered", claim_text))
        return not any(m in claim_text for m in self.uncovered_markers)


def test_context_precision_is_the_fraction_of_relevant_retrieved_chunks() -> None:
    judge = FakeMetricsJudge(irrelevant_chunk_markers=("OFF_TOPIC",))

    value = context_precision(judge, "q?", ["relevant one", "OFF_TOPIC filler", "relevant two"])

    assert value == pytest.approx(2 / 3)


def test_context_precision_is_none_when_nothing_was_retrieved() -> None:
    assert context_precision(FakeMetricsJudge(), "q?", []) is None


def test_context_recall_is_the_fraction_of_reference_claims_covered() -> None:
    judge = FakeMetricsJudge(uncovered_markers=("MISSING",))
    reference = "RSUs are taxed at vest. MISSING the 22% supplemental rate applies."

    value = context_recall(judge, reference, ["a chunk"])

    assert value == pytest.approx(0.5)
    assert len(split_sentences(reference)) == 2


def test_context_recall_is_none_without_a_reference_answer_and_zero_without_context() -> None:
    assert context_recall(FakeMetricsJudge(), None, ["a chunk"]) is None
    assert context_recall(FakeMetricsJudge(), "One claim here.", []) == pytest.approx(0.0)


# --- end to end through run_eval --------------------------------------------


@dataclass
class ScriptedEmbedder:
    vectors: dict[str, list[float]]

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        return [self.vectors[text] for text in texts]


@dataclass
class ScriptedChatLLM:
    answers: dict[str, str]

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        yield self.answers[question]


def _unit_vector(axis: int, dims: int = 1024) -> list[float]:
    vector = [0.0] * dims
    vector[axis] = 1.0
    return vector


def test_run_eval_records_chunk_level_metrics_and_class_rollups(
    db_session: Session, tmp_path: Path
) -> None:
    question = "What happens to my RSUs when they vest?"
    content = Content(
        title="RSUs at vest",
        slug="rsus-at-vest",
        body_md="unused",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.flush()
    target = Chunk(
        content_id=content.id,
        chunk_index=0,
        text="## What happens at vest?\n\nShares are delivered and taxed as ordinary income.",
        embedding=_unit_vector(0),
    )
    db_session.add(target)
    db_session.flush()

    path = tmp_path / "eval_questions.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "question": question,
                    "expected_slugs": ["rsus-at-vest"],
                    "answerable": True,
                    "class": "answerable",
                    "persona": "Sam",
                    "expected_chunks": ["rsus-at-vest#what-happens-at-vest"],
                    "reference_answer": "Shares are delivered and taxed as ordinary income.",
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    judge = FakeMetricsJudge()

    report = run_eval(
        db_session,
        embedder=ScriptedEmbedder(vectors={question: _unit_vector(0)}),
        chat_llm=ScriptedChatLLM(
            answers={question: "Shares are delivered and taxed as ordinary income."}
        ),
        judge=judge,
        questions_path=path,
        metrics_judge=judge,
    )

    row = report.rows[0]
    assert row.question_class == "answerable"
    assert row.persona == "Sam"
    assert row.metrics is not None
    assert row.metrics["retrieval_mode"] == "chunk"
    assert row.metrics["recall_at_k"] == pytest.approx(1.0)
    assert row.metrics["mrr"] == pytest.approx(1.0)
    assert row.metrics["expected_chunk_hits"] == 1
    assert row.metrics["retrieved_chunk_ids"] == [str(target.id)]
    assert row.metrics["answer_relevance"] is True
    assert row.metrics["context_precision"] == pytest.approx(1.0)
    assert row.metrics["context_recall"] == pytest.approx(1.0)

    rollup = report.by_class["answerable"]
    assert (rollup.count, rollup.passed) == (1, 1)
    assert rollup.mean_recall_at_k == pytest.approx(1.0)


def test_metrics_judge_is_optional_so_the_pure_retrieval_metrics_still_land(
    db_session: Session, tmp_path: Path
) -> None:
    question = "Anything about crypto staking?"
    path = tmp_path / "eval_questions.yaml"
    path.write_text(
        yaml.safe_dump(
            [{"question": question, "expected_slugs": [], "answerable": False}], sort_keys=False
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

    metrics = report.rows[0].metrics
    assert metrics is not None
    assert metrics["recall_at_k"] is None
    assert metrics["answer_relevance"] is None
    assert metrics["context_precision"] is None


def test_judge_model_setting_defaults_to_gpt_4o_and_is_zero_env_constructible() -> None:
    settings = Settings()

    assert settings.judge_model == "gpt-4o"
    assert settings.chat_model == "gpt-4o-mini"
```

- [ ] **Run RED:** `cd apps/api && TEST_DATABASE_URL=… uv run pytest tests/test_eval_metrics.py -q`
  → all fail (`ModuleNotFoundError: app.eval.metrics`, `AttributeError: judge_model`).

- [ ] **GREEN — implementer.** Create `app/eval/metrics.py`; add `judge_model` to `Settings`;
  extend `OpenAIJudge` with `_ask` + the three rubric methods (all `temperature=0`) and point
  `from_settings` at `settings.judge_model`; thread `metrics_judge` through `run_eval` /
  `_evaluate_question`; build `EvalRow.metrics`; add `ClassRollup`/`by_class` to `_build_report`
  and the rollup block to `_print_report`. `_run_from_cli` passes `metrics_judge=judge` (the same
  `OpenAIJudge` instance) and `judge_model=settings.judge_model` to `record_run`.

- [ ] **Run GREEN:** `uv run pytest tests/test_eval_metrics.py tests/test_groundedness.py
  tests/test_groundedness_cli.py -q`, then `uv run pytest -q`.

- [ ] **Gates:** `pnpm gates:api` (incl. `lint-imports`; `app.eval` may import `app.rag`/
  `app.services`, so `metrics.py` stays legal as a pure leaf inside `app.eval`).

- [ ] **Commit:** `git commit -m "feat(api): retrieval metrics + rubric judges + per-class rollups (p9 t05)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=… uv run pytest tests/test_eval_metrics.py tests/test_groundedness.py -q
pnpm gates:api
```

## Acceptance

- `retrieval_metrics` matches every pinned case, including empty-expected → `None` and
  dedupe-before-precision.
- The three rubric judges are injectable, content-scripted in tests, and never reach OpenAI;
  `run_eval` without a `metrics_judge` still produces pure retrieval metrics and leaves the three
  judged keys `None` — and all seven `tests/test_groundedness.py` tests pass **unmodified**.
- `Settings().judge_model == "gpt-4o"` with zero env vars; `OpenAIJudge` uses it; the answerer
  still uses `chat_model`.
- Every metric lands in `eval_results.metrics` via task 03's `record_run` — **no new migration**.
- The per-class rollup block prints, and the phase-7 table + summary line above it are unchanged.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-05-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-05-implementer.md` — state
  explicitly that moving the judge to `gpt-4o` changes the recorded groundedness number, and that
  task 09's baseline is the first measurement under it.
