"""Fix round 1 (phase-9 task-05, Opus review): new tests for the controller's rulings —
C1 (chunk-mode-only recall@k/precision@k/MRR; unresolved refs excluded, never downgraded to
slug), I1 (answer-relevance rubric skipped for refused rows), I3 (RAGAS rank-aware
`ragas_context_precision`; the `answer_relevance` -> `answer_relevance_rubric` rename), I4/I5
(per-class rollup printing: `-` for not-applicable cells, `doc_hit%` labelled separately), and
I7 (`_run_from_cli` actually builds the judge from `settings.judge_model` and forwards it as
BOTH `judge` and `metrics_judge`).

Round 1b (controller amendment, commit `b63a9eb`): `tests/test_eval_metrics.py` was itself
amended to re-pin `context_precision(judge, question, chunks)` onto the RAGAS rank-aware formula
(`5/6`, not the old plain fraction `2/3`) and `answer_relevance_rubric` as the ONLY metrics key
(`answer_relevance` dropped). The implementation's two round-1 legacy-compat shims (the old
non-rank-aware `context_precision` behaviour, the dual `answer_relevance`/`answer_relevance_
rubric` keys) were removed to match — this file's tests below were updated in lockstep (see each
test's own docstring for what changed).

Written by the implementer during fix round 1 (not the original task-05 test-author) per the
controller's explicit instruction: "you may ADD tests". Every test in `tests/test_eval_metrics.py`
stays green, and — apart from the controller's own round-1b amendment (`b63a9eb`) — byte-for-byte
unmodified except for one additive method on its `FakeMetricsJudge` (`rank_chunk_relevance` —
required so that fake keeps satisfying `MetricsJudge` after `_evaluate_question` switched to the
Cost ruling's batched call; see that file's own comment and the fix-round-1 implementer report for
the full rationale). Fakes here are defined locally (no cross-test-file imports), per this
codebase's established convention (`tests/test_groundedness.py`'s own module docstring).
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

from app.eval.groundedness import (
    ClassRollup,
    EvalReport,
    _print_class_rollups,
    _run_from_cli,
    run_eval,
)
from app.eval.metrics import ragas_context_precision
from app.models import Chunk, Content

# --- pure math: ragas_context_precision (I3) ---------------------------------


def test_ragas_context_precision_matches_the_rank_aware_worked_example() -> None:
    """The controller's own pinned example: verdicts `[1, 0, 1]` -> `(1/1 + 2/3) / 2`."""
    value = ragas_context_precision([True, False, True])

    assert value == pytest.approx((1 / 1 + 2 / 3) / 2)


def test_ragas_context_precision_is_none_when_nothing_was_retrieved() -> None:
    assert ragas_context_precision([]) is None


def test_ragas_context_precision_is_zero_when_nothing_relevant_was_retrieved() -> None:
    assert ragas_context_precision([False, False, False]) == pytest.approx(0.0)


def test_ragas_context_precision_is_one_for_a_single_relevant_chunk() -> None:
    """The n=1 case: one relevant chunk out of one retrieved scores `1.0` — this is exactly why
    the pre-existing single-chunk end-to-end tests in `tests/test_eval_metrics.py` needed no
    numeric change when `context_precision` started delegating to this same formula (round 1b).
    """
    assert ragas_context_precision([True]) == pytest.approx(1.0)


# --- fakes (defined locally; no cross-test-file imports) ---------------------


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


@dataclass
class ScriptedJudge:
    """An all-true `GroundednessJudge` — these tests aren't exercising faithfulness."""

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        return True


@dataclass
class RecordingMetricsJudge:
    """An all-true `MetricsJudge` that records every call, so I1's "no judge call for a refused
    row" pin can be asserted directly rather than inferred from output alone.
    """

    calls: list[tuple[str, str]] = field(default_factory=list)

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append(("is_supported", claim_text))
        return True

    def is_answer_relevant(self, question: str, answer_text: str) -> bool:
        self.calls.append(("is_answer_relevant", answer_text))
        return True

    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool:
        self.calls.append(("is_chunk_relevant", chunk_text))
        return True

    def rank_chunk_relevance(self, question: str, chunk_texts: Sequence[str]) -> list[bool]:
        self.calls.append(("rank_chunk_relevance", "|".join(chunk_texts)))
        return [True for _ in chunk_texts]

    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        self.calls.append(("is_claim_covered", claim_text))
        return True


def _unit_vector(axis: int, dims: int = 1024) -> list[float]:
    vector = [0.0] * dims
    vector[axis] = 1.0
    return vector


# --- C1: chunk-mode-only recall@k/precision@k/MRR; unresolved refs excluded --


def test_recall_at_k_is_chunk_mode_only_and_unresolved_refs_are_excluded_not_downgraded(
    db_session: Session, tmp_path: Path
) -> None:
    """A mixed report: two chunk-mode rows (resolvable `expected_chunks`), one slug-only row (no
    `expected_chunks` authored at all), and one unresolved row (`expected_chunks` authored but
    the ref matches no chunk). `recall_at_k`/`mrr` must be `None` for the slug-only AND the
    unresolved row (never a slug-level fallback number), so the class/overall mean is computed
    over EXACTLY the two chunk-mode rows; `unresolved_expected_chunks` counts only the truly
    unresolved row.
    """
    content_a = Content(
        title="Topic A",
        slug="topic-a",
        body_md="unused",
        status="published",
        published_at=datetime.now(UTC),
    )
    content_b = Content(
        title="Topic B",
        slug="topic-b",
        body_md="unused",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([content_a, content_b])
    db_session.flush()
    db_session.add_all(
        [
            Chunk(
                content_id=content_a.id,
                chunk_index=0,
                text="## Heading A\n\nContent about topic A.",
                embedding=_unit_vector(0),
            ),
            Chunk(
                content_id=content_b.id,
                chunk_index=0,
                text="## Heading B\n\nContent about topic B.",
                embedding=_unit_vector(2),
            ),
        ]
    )
    db_session.flush()

    q_chunk_a = "What is topic A?"
    q_chunk_b = "What is topic B?"
    q_slug_only = "Tell me generally about topic A."
    q_unresolved = "What about the missing heading in topic A?"

    path = tmp_path / "eval_questions.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "question": q_chunk_a,
                    "expected_slugs": ["topic-a"],
                    "answerable": True,
                    "expected_chunks": ["topic-a#heading-a"],
                },
                {
                    "question": q_chunk_b,
                    "expected_slugs": ["topic-b"],
                    "answerable": True,
                    "expected_chunks": ["topic-b#heading-b"],
                },
                {"question": q_slug_only, "expected_slugs": ["topic-a"], "answerable": True},
                {
                    "question": q_unresolved,
                    "expected_slugs": ["topic-a"],
                    "answerable": True,
                    "expected_chunks": ["topic-a#does-not-exist"],
                },
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    embedder = ScriptedEmbedder(
        vectors={
            q_chunk_a: _unit_vector(0),
            q_chunk_b: _unit_vector(2),
            q_slug_only: _unit_vector(0),
            q_unresolved: _unit_vector(0),
        }
    )
    chat_llm = ScriptedChatLLM(
        answers={
            q_chunk_a: "Topic A answer.",
            q_chunk_b: "Topic B answer.",
            q_slug_only: "Topic A answer.",
            q_unresolved: "Topic A answer.",
        }
    )

    report = run_eval(
        db_session,
        embedder=embedder,
        chat_llm=chat_llm,
        judge=ScriptedJudge(),
        questions_path=path,
    )

    assert report.unresolved_expected_chunks == 1

    by_question = {row.question: row for row in report.rows}
    chunk_a_metrics = by_question[q_chunk_a].metrics
    chunk_b_metrics = by_question[q_chunk_b].metrics
    slug_only_metrics = by_question[q_slug_only].metrics
    unresolved_metrics = by_question[q_unresolved].metrics
    assert chunk_a_metrics is not None and chunk_b_metrics is not None
    assert slug_only_metrics is not None and unresolved_metrics is not None

    assert chunk_a_metrics["recall_at_k"] == pytest.approx(1.0)
    assert chunk_b_metrics["recall_at_k"] == pytest.approx(1.0)
    assert slug_only_metrics["recall_at_k"] is None
    assert unresolved_metrics["recall_at_k"] is None

    assert report.overall.count == 4
    assert report.overall.mean_recall_at_k == pytest.approx(1.0)


# --- I1: answer-relevance rubric skipped for refused rows --------------------


def test_answer_relevance_rubric_is_none_and_unjudged_for_a_refused_row(
    db_session: Session, tmp_path: Path
) -> None:
    """An off-domain refusal (no chunk anywhere near the query, so retrieval finds nothing and
    the row is `refused`) has no answer-relevance verdict, and `is_answer_relevant` is never
    called for it.
    """
    question = "What does the firm recommend about llama grooming techniques?"
    path = tmp_path / "eval_questions.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "question": question,
                    "expected_slugs": [],
                    "answerable": False,
                    "class": "off_domain",
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    metrics_judge = RecordingMetricsJudge()

    report = run_eval(
        db_session,
        embedder=ScriptedEmbedder(vectors={question: _unit_vector(0)}),
        chat_llm=ScriptedChatLLM(answers={question: "No published guidance covers this."}),
        judge=ScriptedJudge(),
        questions_path=path,
        metrics_judge=metrics_judge,
    )

    row = report.rows[0]
    assert row.refused is True
    assert row.metrics is not None
    assert row.metrics["answer_relevance_rubric"] is None
    assert not any(call[0] == "is_answer_relevant" for call in metrics_judge.calls)


# --- I3: the `answer_relevance` -> `answer_relevance_rubric` rename ----------


def test_answer_relevance_metric_key_and_rollup_field_are_renamed_to_rubric(
    db_session: Session, tmp_path: Path
) -> None:
    """`EvalRow.metrics["answer_relevance_rubric"]` is the ONLY key (round 1b: the controller
    re-pinned `tests/test_eval_metrics.py` onto this name and the legacy `"answer_relevance"` key
    was dropped — see `_evaluate_question`'s `EvalRow(...)` construction), and `ClassRollup.
    mean_answer_relevance_rubric` is its class/overall aggregate (I6).
    """
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
            [{"question": question, "expected_slugs": ["rsus-at-vest"], "answerable": True}],
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report = run_eval(
        db_session,
        embedder=ScriptedEmbedder(vectors={question: _unit_vector(0)}),
        chat_llm=ScriptedChatLLM(
            answers={question: "Shares are delivered and taxed as ordinary income."}
        ),
        judge=ScriptedJudge(),
        questions_path=path,
        metrics_judge=RecordingMetricsJudge(),
    )

    row = report.rows[0]
    assert row.metrics is not None
    assert row.metrics["answer_relevance_rubric"] is True
    assert "answer_relevance" not in row.metrics
    assert report.overall.mean_answer_relevance_rubric == pytest.approx(1.0)


# --- I4/I5: per-class rollup printing (doc_hit% label, "-" for not applicable) --


def test_print_class_rollups_labels_doc_hit_and_dashes_not_applicable_cells(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Covers a normal class (every cell a real number), an all-refusal class (`pct_fully_
    supported`/`recall@k`/`mrr` all `-`, since none of its rows are chunk-mode or answerable), and
    the `overall` rollup — plus that `doc_hit%` (C1) is its own labelled column, separate from
    `recall@k`.
    """
    normal_rollup = ClassRollup(
        question_class="answerable",
        count=17,
        passed=10,
        pct_fully_supported=58.8,
        doc_hit_rate=0.941,
        mean_recall_at_k=1.0,
        mean_mrr=0.9,
        mean_precision_at_k=0.17,
        mean_answer_relevance_rubric=0.9,
        mean_context_precision=0.85,
        mean_context_recall=0.9,
    )
    all_refusal_rollup = ClassRollup(
        question_class="off_domain",
        count=8,
        passed=8,
        pct_fully_supported=None,
        doc_hit_rate=1.0,
        mean_recall_at_k=None,
        mean_mrr=None,
        mean_precision_at_k=None,
        mean_answer_relevance_rubric=None,
        mean_context_precision=None,
        mean_context_recall=None,
    )
    overall = ClassRollup(
        question_class="overall",
        count=25,
        passed=18,
        pct_fully_supported=40.0,
        doc_hit_rate=0.96,
        mean_recall_at_k=0.9,
        mean_mrr=0.85,
        mean_precision_at_k=0.15,
        mean_answer_relevance_rubric=0.88,
        mean_context_precision=0.8,
        mean_context_recall=0.87,
    )
    report = EvalReport(
        rows=[],
        pct_fully_supported=58.8,
        refusal_correct=8,
        refusal_total=8,
        by_class={"answerable": normal_rollup, "off_domain": all_refusal_rollup},
        overall=overall,
    )

    _print_class_rollups(report)

    out = capsys.readouterr().out
    lines = out.splitlines()

    assert lines[0] == "by class:"
    assert "doc_hit%" in lines[1]
    assert "recall@k" in lines[1]

    answerable_line = next(line for line in lines if line.strip().startswith("answerable"))
    assert "-" not in answerable_line

    off_domain_line = next(line for line in lines if line.strip().startswith("off_domain"))
    assert off_domain_line.split() == ["off_domain", "8", "8", "-", "100.0", "-", "-"]

    assert "judge metrics by class:" in out
    assert out.count("overall") == 2  # once in each of the two blocks


# --- I7: _run_from_cli wires settings.judge_model + forwards metrics_judge ---


def test_run_from_cli_builds_the_judge_from_judge_model_and_forwards_it_as_metrics_judge(
    db_session: Session,
) -> None:
    """`_run_from_cli` must build its judge from `settings.judge_model` (not `chat_model`) and
    pass that SAME instance as both `judge` and `metrics_judge` into `run_eval` — the two lines
    that make DESIGN D7 real in a recorded run (Opus review I7). `run_eval_fn` here never calls
    the real `run_eval`, so this never reaches OpenAI.
    """
    captured: dict[str, object] = {}

    def recording_run_eval(*_args: object, **kwargs: object) -> EvalReport:
        captured.update(kwargs)
        return EvalReport(rows=[], pct_fully_supported=0.0, refusal_correct=0, refusal_total=0)

    _run_from_cli(
        ["--label", "fix-round-1-i7", "--no-persist"],
        run_eval_fn=recording_run_eval,
        session_factory=lambda: db_session,
    )

    assert captured["judge"] is captured["metrics_judge"]
    assert getattr(captured["judge"], "_model", None) == "gpt-4o"
