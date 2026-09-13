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
        chat_model="gpt-5.4-mini",
        judge_model="gpt-5.4",
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
    assert run.judge_model == "gpt-5.4"
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


# ---------------------------------------------------------------------------
# Fix wave F1: `compare_runs` grows a FAMILY mode — runs sharing a `label` AND `corpus_digest`
# form a family, and a question is a regression/improvement only when the family's MAJORITY
# verdict flips. A family of one (different labels, the two tests above) must keep behaving
# exactly as before -- confirmed by leaving those two tests untouched.
# ---------------------------------------------------------------------------


def test_compare_runs_family_mode_does_not_flag_a_regression_that_does_not_reproduce(
    db_session: Session,
) -> None:
    """A question that flips PASS -> FAIL in only ONE of three after-runs is not a majority
    regression: the after family's majority verdict is still PASS (2 of 3), so the question is
    `unchanged`, not `regressions` — a single flaky run must not block acceptance."""
    before = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="fam1-before",
    )
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="fam1-after",
    )
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="fam1-after",
    )
    flaky_after = _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="fam1-after",
    )

    diff = compare_runs(db_session, before.id, flaky_after.id)

    assert diff.regressions == []
    assert diff.unchanged == ["q1"]
    assert len(diff.before_family) == 1
    assert len(diff.after_family) == 3
    assert before.id in diff.before_family
    assert flaky_after.id in diff.after_family


def test_compare_runs_family_mode_flags_a_regression_that_reproduces_in_a_majority(
    db_session: Session,
) -> None:
    """Two of three after-runs failing the same question IS a majority regression, and the
    question is named -- a real regression must still be caught even when it does not reproduce
    on every single run (the flip side of the flakiness test above)."""
    before = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="fam2-before",
    )
    _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="fam2-after",
    )
    _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="fam2-after",
    )
    after = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="fam2-after",
    )

    diff = compare_runs(db_session, before.id, after.id)

    assert diff.regressions == ["q1"]
    assert len(diff.after_family) == 3


# ---------------------------------------------------------------------------
# Fix wave round 2 (M2): an after-side TIE counts as a FAIL for the regression vote (fail-closed
# where it matters) -- a before-side tie stays `unchanged`, and an improvement still requires a
# CLEAN "PASS" majority on the after side. `_majority_verdict` itself is unchanged (still `None`
# on a tie); only what `compare_runs` DOES with that `None` differs by side.
# ---------------------------------------------------------------------------


def test_compare_runs_after_side_tie_counts_as_a_regression_against_a_pass_baseline(
    db_session: Session,
) -> None:
    """Re-review probe F4 stage 2: a before-family majority PASS against an after-family EVEN
    split (2 PASS / 2 FAIL) on the same question is a regression, not `unchanged`. Pre-fix, this
    tie folded to `unchanged` and accepted the fix -- a genuine reproducing regression could be
    voted away by padding the after family with passing runs under the same label until the
    majority merely tied."""
    before = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="tie1-before",
    )
    _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie1-after",
    )
    _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie1-after",
    )
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="tie1-after",
    )
    after = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="tie1-after",
    )

    diff = compare_runs(db_session, before.id, after.id)

    assert diff.regressions == ["q1"]
    assert diff.unchanged == []
    assert len(diff.after_family) == 4


def test_compare_runs_after_side_tie_is_not_an_improvement(db_session: Session) -> None:
    """An improvement still requires a CLEAN "PASS" majority on the after side -- a before-family
    majority FAIL against an after-family EVEN split does not count as an improvement; it lands in
    `unchanged`, not `improvements` (the mirror of the regression rule above is deliberately NOT
    symmetric)."""
    before = _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie2-before",
    )
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="tie2-after",
    )
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="tie2-after",
    )
    _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie2-after",
    )
    after = _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie2-after",
    )

    diff = compare_runs(db_session, before.id, after.id)

    assert diff.improvements == []
    assert diff.unchanged == ["q1"]
    assert diff.regressions == []


def test_compare_runs_before_side_tie_stays_unchanged_with_a_clean_after_fail(
    db_session: Session,
) -> None:
    """Pinning UNCHANGED behaviour (fix wave round 2, M2): a before-side tie folds to `unchanged`
    regardless of the after side -- there is no majority verdict to have regressed FROM, so even a
    clean after-family FAIL does not count as a regression."""
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="tie3-before",
    )
    _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie3-before",
    )
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="tie3-before",
    )
    before = _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie3-before",
    )
    after = _record(
        db_session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict="FAIL", fully_supported=False)],
            pct_fully_supported=0.0,
        ),
        label="tie3-after",
    )

    diff = compare_runs(db_session, before.id, after.id)

    assert diff.regressions == []
    assert diff.unchanged == ["q1"]


def test_compare_runs_pct_delta_uses_family_means(db_session: Session) -> None:
    """`pct_delta` averages `pct_fully_supported` over each side's family, not just the two
    named runs -- the family mean is the number the acceptance gate's pct rung must compare."""
    before = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=50.0),
        label="fam3-before",
    )
    _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=90.0),
        label="fam3-after",
    )
    after = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=70.0),
        label="fam3-after",
    )

    diff = compare_runs(db_session, before.id, after.id)

    # after family mean = (90 + 70) / 2 = 80; before family mean = 50; delta = 30
    assert diff.pct_delta == pytest.approx(30.0)
    # Fix wave round 2 (M4): the means themselves are now their own fields, not just their
    # difference -- `pct_delta` is `pct_after - pct_before` by construction.
    assert diff.pct_before == pytest.approx(50.0)
    assert diff.pct_after == pytest.approx(80.0)
    assert diff.pct_delta == pytest.approx(diff.pct_after - diff.pct_before)


def test_compare_runs_family_only_includes_runs_with_the_same_corpus_digest(
    db_session: Session,
) -> None:
    """A re-used label does not mix corpora: two runs can share a label but belong to different
    families if a publish moved the digest between them (fix wave F1's digest guard)."""
    stale = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="mixed-digest",
    )
    _publish(db_session, "some-new-article-between-runs")
    second = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="mixed-digest",
    )
    third = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")], pct_fully_supported=100.0),
        label="mixed-digest",
    )
    assert stale.corpus_digest != second.corpus_digest == third.corpus_digest

    diff = compare_runs(db_session, stale.id, third.id)

    assert set(diff.before_family) == {stale.id}
    assert set(diff.after_family) == {second.id, third.id}


def test_run_diff_family_ids_are_ordered_by_created_at(db_session: Session) -> None:
    """`RunDiff.before_family`/`after_family` are ids, oldest-first (mirrors `latest_runs`'
    own newest-first convention, just the other direction) -- so a caller/report can show what
    was actually compared."""
    from app.services.eval_runs import run_family

    first = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")]),
        label="ordered-fam",
    )
    second = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")]),
        label="ordered-fam",
    )
    third = _record(
        db_session,
        FakeReport(rows=[FakeRow(question="q1", verdict="PASS")]),
        label="ordered-fam",
    )

    family = run_family(db_session, third)

    assert [run.id for run in family] == [first.id, second.id, third.id]
