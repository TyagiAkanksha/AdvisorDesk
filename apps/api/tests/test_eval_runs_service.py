"""`app.services.eval_runs` pins (phase-9 task-03, DESIGN §B1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Content, EvalResult
from app.services.errors import NotFoundError
from app.services.eval_runs import compare_runs, corpus_fingerprint, latest_runs, record_run


@dataclass(frozen=True)
class FakeRow:
    question: str
    answerable: bool = True
    expected_slugs: list[str] = field(default_factory=list)
    cited_slugs: list[str] = field(default_factory=list)
    slugs_hit: bool = True
    fully_supported: bool | None = True
    refused: bool = False
    verdict: str = "PASS"
    top_similarity: float | None = 0.8
    answer_text: str = "an answer"
    question_class: str | None = None
    persona: str | None = None
    metrics: dict[str, object] | None = None


@dataclass(frozen=True)
class FakeReport:
    rows: list[FakeRow]
    pct_fully_supported: float = 100.0
    refusal_correct: int = 0
    refusal_total: int = 0


def _record(session: Session, report: FakeReport, *, label: str = "t", kind: str = "answer"):
    return record_run(
        session,
        report,
        label=label,
        kind=kind,
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        judge_model="gpt-4o",
        similarity_threshold=0.5,
        retrieval_k=6,
        git_sha="deadbeef",
    )


def _publish(session: Session, slug: str, *, chunks: int = 1) -> Content:
    content = Content(
        title=f"Title {slug}",
        slug=slug,
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    for index in range(chunks):
        session.add(Chunk(content_id=content.id, chunk_index=index, text=f"chunk {index}"))
    session.flush()
    return content


def test_corpus_fingerprint_counts_published_chunks_and_changes_when_content_is_updated(
    db_session: Session,
) -> None:
    _publish(db_session, "alpha", chunks=2)
    _publish(db_session, "beta", chunks=1)
    before = corpus_fingerprint(db_session)

    assert before.content_count == 2
    assert before.chunk_count == 3
    assert len(before.digest) == 16

    target = db_session.scalars(select(Content).where(Content.slug == "beta")).one()
    target.updated_at = datetime.now(UTC) + timedelta(seconds=5)
    db_session.flush()
    after = corpus_fingerprint(db_session)

    assert after.digest != before.digest
    assert after.max_updated_at is not None and before.max_updated_at is not None
    assert after.max_updated_at > before.max_updated_at


def test_draft_and_deleted_content_are_outside_the_fingerprint(db_session: Session) -> None:
    _publish(db_session, "published-one")
    db_session.add(Content(title="Draft", slug="draft-one", status="draft"))
    deleted = _publish(db_session, "deleted-one")
    deleted.is_deleted = True
    db_session.flush()

    assert corpus_fingerprint(db_session).content_count == 1


def test_record_run_persists_the_run_and_one_result_per_row(db_session: Session) -> None:
    report = FakeReport(
        rows=[
            FakeRow(question="q1", expected_slugs=["a"], cited_slugs=["a"]),
            FakeRow(
                question="q2",
                answerable=False,
                fully_supported=None,
                refused=True,
                verdict="PASS",
                top_similarity=None,
                metrics={"failure_cause": None},
            ),
        ],
        pct_fully_supported=100.0,
        refusal_correct=1,
        refusal_total=1,
    )

    run = _record(db_session, report, label="baseline-2026-09")

    assert run.label == "baseline-2026-09"
    assert run.kind == "answer"
    assert run.git_sha == "deadbeef"
    assert run.total_questions == 2
    assert run.judge_model == "gpt-4o"
    results = db_session.scalars(
        select(EvalResult).where(EvalResult.run_id == run.id).order_by(EvalResult.question)
    ).all()
    assert [r.question for r in results] == ["q1", "q2"]
    assert results[0].cited_slugs == ["a"]
    assert results[1].top_similarity is None
    assert results[1].metrics == {"failure_cause": None}


def test_latest_runs_is_newest_first_and_filters_by_kind_and_label(db_session: Session) -> None:
    first = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="a")
    second = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="b")
    agent = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="b", kind="agent")

    ids = [run.id for run in latest_runs(db_session)]
    assert ids[0] == second.id
    assert first.id in ids
    assert agent.id not in ids
    assert [run.id for run in latest_runs(db_session, kind="agent")] == [agent.id]
    assert [run.id for run in latest_runs(db_session, label="a")] == [first.id]


def test_latest_runs_orders_newest_first_within_one_transaction_by_insertion_order(
    db_session: Session,
) -> None:
    """Fix round 1, C1: `EvalRun.created_at`'s server default is Postgres' TRANSACTION
    timestamp, so three runs recorded in one transaction (as this test's three `_record` calls,
    and any real `--runs 3` invocation, are) previously carried an IDENTICAL `created_at` and
    `latest_runs` fell back to a random-UUID tiebreaker — deterministic, but not newest-first
    (task-03 review, Critical C1). `record_run` now stamps `created_at` app-side
    (`datetime.now(UTC)`), which is distinct per call, so ordering must reflect actual insertion
    order regardless of how many runs share one transaction.
    """
    first = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="family")
    second = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="family")
    third = _record(db_session, FakeReport(rows=[FakeRow(question="q")]), label="family")

    ids = [run.id for run in latest_runs(db_session, label="family")]

    assert ids == [third.id, second.id, first.id]
    assert latest_runs(db_session, label="family", limit=1)[0].id == third.id


def test_compare_runs_classifies_regressions_improvements_added_and_removed(
    db_session: Session,
) -> None:
    before = _record(
        db_session,
        FakeReport(
            rows=[
                FakeRow(question="stays-pass", verdict="PASS"),
                FakeRow(question="regresses", verdict="PASS"),
                FakeRow(question="improves", verdict="FAIL", fully_supported=False),
                FakeRow(question="removed", verdict="PASS"),
            ],
            pct_fully_supported=75.0,
        ),
        label="before",
    )
    after = _record(
        db_session,
        FakeReport(
            rows=[
                FakeRow(question="stays-pass", verdict="PASS"),
                FakeRow(question="regresses", verdict="FAIL", fully_supported=False),
                FakeRow(question="improves", verdict="PASS"),
                FakeRow(question="added", verdict="PASS"),
            ],
            pct_fully_supported=80.0,
        ),
        label="after",
    )

    diff = compare_runs(db_session, before.id, after.id)

    assert diff.regressions == ["regresses"]
    assert diff.improvements == ["improves"]
    assert diff.unchanged == ["stays-pass"]
    assert diff.added == ["added"]
    assert diff.removed == ["removed"]
    assert diff.pct_delta == pytest.approx(5.0)


def test_compare_runs_raises_not_found_for_an_unknown_run_id(db_session: Session) -> None:
    run = _record(db_session, FakeReport(rows=[FakeRow(question="q")]))
    with pytest.raises(NotFoundError):
        compare_runs(db_session, run.id, uuid.uuid4())
