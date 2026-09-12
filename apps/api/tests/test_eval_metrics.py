"""Metrics v2 (phase-9 task-05): pure IR math, the three rubric judges, per-class rollups.

Task brief: `docs/plans/phase-9-eval-data-loop/task-05-metrics-v2.md`, Steps "RED — test-author".
Every test below through `test_judge_model_setting_defaults_to_gpt_4o_and_is_zero_env_constructible`
is copied VERBATIM from the task file's own code block (the brief hands the test-author complete,
runnable tests, not a description to reimplement) — do not edit those without controller approval.

`app.eval.metrics` does not exist yet: the pure-math and rubric-judge tests fail at collection
(`ModuleNotFoundError: No module named 'app.eval.metrics'`) until the implementer creates it.
`Settings.judge_model` does not exist yet either, so the last test fails at
`AttributeError: 'Settings' object has no attribute 'judge_model'` once collection succeeds. The
two `run_eval(...)` end-to-end tests additionally require `EvalRow.metrics`/`EvalReport.by_class`
to be populated by `run_eval`/`_evaluate_question` (today they stay `None`/absent) — that RED
manifests as `AssertionError`/`KeyError` on the row's `metrics` dict rather than a collection
error.

Ruff isort gotcha (mirrors `tests/test_eval_questions_v2.py`'s own documented note, phase-9 task
04's test-author report): `from app.eval.metrics import ...` sorts into the FIRST-PARTY block only
when `app/eval/metrics.py` exists on disk. With the module absent (this file's honest RED state),
`ruff check --no-cache` — and therefore `lefthook`'s pre-commit `ruff check --fix` — treats it as
unclassifiable and moves it up next to `import yaml`/`from sqlalchemy.orm import Session` instead,
which would silently commit a GREEN-broken import order the implementer could not fix (an
authored test file). Verified empirically against a throwaway, never-staged
`app/eval/metrics.py` stub. The import block below keeps the GREEN-correct order (task file's own
code block); the stub trick — not editing this file — is how the test-author's commit avoids the
hook rewriting it (see the task-05 test-author report).

Controller addition (task-04 review, Minor 1 ruling — `.superpowers/sdd/phase-9-eval-data-loop/
progress.md`): `resolve_expected_chunks` silently skips an `expected_chunks` ref that matches no
chunk (task-04's own documented decision). The ruling requires task 05 to COUNT unresolved refs in
the report; `test_report_counts_expected_chunks_refs_that_fail_to_resolve` below (added by the
test-author per that ruling, not part of the task file's own verbatim block) pins
`EvalReport.unresolved_expected_chunks: int` for exactly that purpose — a stale/typo'd ref in a
committed eval file must surface in the report instead of silently falling back to slug-level
scoring with no trace.
"""

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

    def rank_chunk_relevance(self, question: str, chunk_texts: Sequence[str]) -> list[bool]:
        # Fix round 1 (Opus review, Cost ruling): additive method, added by the implementer (not
        # the test-author) so this fake keeps satisfying `MetricsJudge` after `_evaluate_question`
        # switched from one `is_chunk_relevant` call per chunk to one batched
        # `rank_chunk_relevance` call. No existing method/marker/assertion above is touched;
        # reuses `is_chunk_relevant`'s own marker logic per-chunk, so every ALREADY-AUTHORED
        # end-to-end assertion that exercises `run_eval(..., metrics_judge=...)` scores IDENTICALLY
        # (a single-chunk retrieval's RAGAS-rank-aware precision and the old plain-fraction
        # precision agree at n=1: both are 1.0 for one relevant chunk). See the fix-round-1
        # implementer report for why this addition was necessary rather than optional.
        self.calls.append(("rank_chunk_relevance", "|".join(chunk_texts)))
        return [self.is_chunk_relevant(question, text) for text in chunk_texts]

    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append(("is_claim_covered", claim_text))
        return not any(m in claim_text for m in self.uncovered_markers)


def test_context_precision_is_the_ragas_rank_aware_precision() -> None:
    # Controller amendment (task-05 review I3): the metric named `context_precision` must be the
    # RAGAS definition — Σ_i precision@i · rel_i / |relevant| — not the plain relevant fraction.
    # Verdicts [True, False, True] → (1/1 · 1 + 1/2 · 0 + 2/3 · 1) / 2 = 5/6.
    judge = FakeMetricsJudge(irrelevant_chunk_markers=("OFF_TOPIC",))

    value = context_precision(judge, "q?", ["relevant one", "OFF_TOPIC filler", "relevant two"])

    assert value == pytest.approx(5 / 6)


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
    assert row.metrics["answer_relevance_rubric"] is True
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
    assert metrics["answer_relevance_rubric"] is None
    assert metrics["context_precision"] is None


def test_judge_model_setting_defaults_to_gpt_4o_and_is_zero_env_constructible() -> None:
    settings = Settings()

    assert settings.judge_model == "gpt-4o"
    assert settings.chat_model == "gpt-4o-mini"


# --- controller addition: unresolved `expected_chunks` refs must be counted --


def test_report_counts_expected_chunks_refs_that_fail_to_resolve(
    db_session: Session, tmp_path: Path
) -> None:
    """Controller ruling (task-04 review, Minor 1 — `.superpowers/sdd/phase-9-eval-data-loop/
    progress.md`): `resolve_expected_chunks` silently skips a ref that resolves to nothing
    (task-04's own documented decision, `app/eval/questions.py` module docstring). This pin
    requires the report to surface that instead of only falling back to slug-level scoring with
    no trace: `EvalReport.unresolved_expected_chunks` is the count, across every row, of
    `expected_chunks` refs that did not resolve to a chunk id.

    Two questions share one seeded chunk (heading "What happens at vest?", slug
    `rsus-at-vest`): one references that heading correctly (resolves, contributes 0), the other
    references a heading that does not exist on that content (`#nonexistent-heading` — never
    resolves, contributes 1, and its row's `retrieval_mode` falls back to `"slug"` exactly as the
    task file's mode-selection rule specifies for an empty `resolved` set).
    """
    resolvable_question = "What happens to my RSUs when they vest?"
    unresolvable_question = "What is the RSU vesting cliff?"
    content = Content(
        title="RSUs at vest",
        slug="rsus-at-vest",
        body_md="unused",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.flush()
    db_session.add(
        Chunk(
            content_id=content.id,
            chunk_index=0,
            text="## What happens at vest?\n\nShares are delivered and taxed as ordinary income.",
            embedding=_unit_vector(0),
        )
    )
    db_session.flush()

    path = tmp_path / "eval_questions.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "question": resolvable_question,
                    "expected_slugs": ["rsus-at-vest"],
                    "answerable": True,
                    "expected_chunks": ["rsus-at-vest#what-happens-at-vest"],
                },
                {
                    "question": unresolvable_question,
                    "expected_slugs": ["rsus-at-vest"],
                    "answerable": True,
                    "expected_chunks": ["rsus-at-vest#nonexistent-heading"],
                },
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report = run_eval(
        db_session,
        embedder=ScriptedEmbedder(
            vectors={
                resolvable_question: _unit_vector(0),
                unresolvable_question: _unit_vector(0),
            }
        ),
        chat_llm=ScriptedChatLLM(
            answers={
                resolvable_question: "Shares are delivered and taxed as ordinary income.",
                unresolvable_question: "Shares are delivered and taxed as ordinary income.",
            }
        ),
        judge=FakeMetricsJudge(),
        questions_path=path,
    )

    assert report.unresolved_expected_chunks == 1
    by_question = {row.question: row for row in report.rows}
    resolvable_metrics = by_question[resolvable_question].metrics
    unresolvable_metrics = by_question[unresolvable_question].metrics
    assert resolvable_metrics is not None
    assert unresolvable_metrics is not None
    assert resolvable_metrics["retrieval_mode"] == "chunk"
    assert unresolvable_metrics["retrieval_mode"] == "slug"


# --- controller addition: task-06 failure taxonomy integration pin ----------


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
