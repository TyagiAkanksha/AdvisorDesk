"""`app.services.proposals` pins (phase-9 task-16, DESIGN §D).

The acceptance gate is the point of this file: five refusal branches and one clean accept, all on
real `eval_runs`/`eval_results` rows written through `record_run` (no harness, no network) with a
real published-content change between them so the corpus digest genuinely moves.

`ContentProposal.kind`'s CHECK is already pinned by `tests/test_eval_models.py:111-126` (task 01);
this file pins the `status` CHECK, the half task 01 left uncovered, rather than duplicating it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Chunk, Content, ContentProposal, EvalRun, User
from app.services.content import publish_content
from app.services.errors import ConflictError, NotFoundError
from app.services.eval_policy import PROPOSAL_KIND_BY_CAUSE
from app.services.eval_runs import record_run
from app.services.lifecycle import NoopChunkPipeline
from app.services.proposals import (
    accept_proposal,
    check_acceptance,
    kind_for_cause,
    list_proposals,
    propose_content_fix,
    reject_proposal,
)

_EVIDENCE = [
    {
        "normalized_question": "do rsus work differently outside the us",
        "count": 4,
        "kinds": ["near_miss"],
        "worst_top_similarity": 0.41,
    },
    {
        "normalized_question": "what about qsbs",
        "count": 2,
        "kinds": ["refused"],
        "worst_top_similarity": None,
    },
]


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


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


def _record(session: Session, report: FakeReport, *, label: str, kind: str = "answer"):
    """One real `eval_runs` row (+ its results) — `record_run` computes the corpus fingerprint."""
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


def _publish(session: Session, slug: str) -> Content:
    """Publish one content row WITH a chunk, so the corpus fingerprint/digest actually moves."""
    content = Content(
        title=f"Title {slug}",
        slug=slug,
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    session.add(Chunk(content_id=content.id, chunk_index=0, text="chunk"))
    session.flush()
    return content


def _report(*questions_and_verdicts: tuple[str, str], pct: float) -> FakeReport:
    return FakeReport(
        rows=[
            FakeRow(question=question, verdict=verdict, fully_supported=verdict == "PASS")
            for question, verdict in questions_and_verdicts
        ],
        pct_fully_supported=pct,
    )


# ---------------------------------------------------------------------------
# The CHECK constraint task 01 left unpinned
# ---------------------------------------------------------------------------


def test_status_check_rejects_a_value_outside_the_three_states(db_session: Session) -> None:
    db_session.add(
        ContentProposal(
            kind="new_article", title="t", rationale="r", evidence={}, status="half-accepted"
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_kind_check_rejects_a_value_outside_the_three_kinds(db_session: Session) -> None:
    """The task-01 ruling asks for both CHECKs to be pinned behaviourally. `kind` is also pinned
    at `tests/test_eval_models.py:123-126`; it is re-asserted here so this task's own file is
    self-contained evidence for the reviewer (one line, no fixture, no overlap to maintain)."""
    db_session.add(
        ContentProposal(kind="rewrite_everything", title="t", rationale="r", evidence={})
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ---------------------------------------------------------------------------
# kind_for_cause
# ---------------------------------------------------------------------------


def test_kind_for_cause_maps_every_actionable_cause() -> None:
    assert kind_for_cause("corpus_gap") == "new_article"
    assert kind_for_cause("generation_unfaithful") == "expand_article"
    assert kind_for_cause("retrieval_miss") == "retune"
    assert kind_for_cause("threshold_refusal") == "retune"


def test_kind_for_cause_refuses_judge_disagreement_and_unknown_causes() -> None:
    """`judge_disagreement` maps to no proposal: the fix is judge calibration, not content."""
    assert PROPOSAL_KIND_BY_CAUSE["judge_disagreement"] is None
    with pytest.raises(ValueError, match="judge_disagreement"):
        kind_for_cause("judge_disagreement")
    with pytest.raises(ValueError, match="bogus_cause"):
        kind_for_cause("bogus_cause")


# ---------------------------------------------------------------------------
# propose_content_fix
# ---------------------------------------------------------------------------


def test_propose_creates_a_linked_draft_and_snapshots_the_evidence(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    baseline = _record(db_session, _report(("q1", "PASS"), pct=50.0), label="baseline")

    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="RSUs for employees outside the US",
        rationale="Four near-miss questions in 30 days, closest source at 0.41.",
        evidence=_EVIDENCE,
        actor_id=actor_id,
    )

    assert proposal.status == "proposed"
    assert proposal.kind == "new_article"
    assert proposal.eval_run_before_id == baseline.id
    assert proposal.created_by == actor_id
    assert proposal.draft_content_id is not None

    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None
    assert draft.status == "draft"
    assert draft.title == "RSUs for employees outside the US"
    assert draft.author_id == actor_id
    # The stub names the gap it exists to close — a human/agent finishes the body before publishing.
    assert "do rsus work differently outside the us" in draft.body_md
    assert "0.41" in draft.body_md

    assert proposal.evidence["weak_queries"] == _EVIDENCE
    assert isinstance(proposal.evidence["captured_at"], str)


def test_propose_with_no_baseline_run_still_records_the_proposal(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """No eval run yet is not an error HERE — it becomes one at `accept_proposal`."""
    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="Crypto compensation basics",
        rationale="Two refusals.",
        evidence=[],
        actor_id=actor_id,
    )

    assert proposal.eval_run_before_id is None
    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None and "no weak-query rows supplied" in draft.body_md


def test_propose_stamps_the_latest_answer_run_not_an_agent_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    answer_run = _record(db_session, _report(("q1", "PASS"), pct=60.0), label="answers")
    _record(db_session, _report(("task-1", "PASS"), pct=90.0), label="agents", kind="agent")

    proposal = propose_content_fix(
        db_session,
        kind="expand_article",
        title="ESPP dispositions, expanded",
        rationale="Low-confidence answers.",
        evidence=_EVIDENCE,
        actor_id=actor_id,
    )

    assert proposal.eval_run_before_id == answer_run.id


def test_propose_rejects_an_unknown_kind_before_touching_the_database(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(ValueError, match="kind"):
        propose_content_fix(
            db_session,
            kind="rewrite_everything",
            title="T",
            rationale="R",
            evidence=[],
            actor_id=actor_id,
        )

    assert db_session.scalars(select(ContentProposal)).all() == []
    assert db_session.scalars(select(Content)).all() == []


def test_propose_does_not_alias_the_callers_evidence(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    rows = [{"normalized_question": "q", "count": 1}]
    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="Aliasing check",
        rationale="R",
        evidence=rows,
        actor_id=actor_id,
    )

    rows[0]["count"] = 999

    assert proposal.evidence["weak_queries"][0]["count"] == 1


# ---------------------------------------------------------------------------
# list_proposals
# ---------------------------------------------------------------------------


def test_list_proposals_is_newest_first_and_filters_by_status(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    first = propose_content_fix(
        db_session, kind="new_article", title="First", rationale="R", evidence=[], actor_id=actor_id
    )
    second = propose_content_fix(
        db_session, kind="retune", title="Second", rationale="R", evidence=[], actor_id=actor_id
    )
    first.status = "rejected"
    db_session.flush()

    assert [p.id for p in list_proposals(db_session)][0] == second.id
    assert [p.id for p in list_proposals(db_session, status="proposed")] == [second.id]
    assert [p.id for p in list_proposals(db_session, status="rejected")] == [first.id]
    assert len(list_proposals(db_session, limit=1)) == 1
    # A typo'd filter must not read as "no proposals".
    with pytest.raises(ValueError, match="status"):
        list_proposals(db_session, status="propsed")


# ---------------------------------------------------------------------------
# accept_proposal — one test per gate
# ---------------------------------------------------------------------------


def test_accept_raises_not_found_for_an_unknown_proposal(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        accept_proposal(db_session, uuid.uuid4(), eval_run_after_id=uuid.uuid4())


def test_accept_refuses_when_there_is_no_baseline_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")

    with pytest.raises(ConflictError, match="before"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"
    assert proposal.eval_run_after_id is None


def test_accept_raises_not_found_for_an_unknown_after_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )

    with pytest.raises(NotFoundError):
        accept_proposal(db_session, proposal.id, eval_run_after_id=uuid.uuid4())


def test_accept_refuses_an_agent_run_as_the_after_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "the-fix")
    agent_run = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="a", kind="agent")

    with pytest.raises(ConflictError, match="kind"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=agent_run.id)


def test_accept_refuses_when_the_corpus_never_changed(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Gate 4: identical `corpus_digest` means the after-run measured the SAME corpus — nobody
    published the fix, so there is nothing validated."""
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")

    assert proposal.eval_run_before_id is not None
    before = db_session.get(EvalRun, proposal.eval_run_before_id)
    assert before is not None and before.corpus_digest == after.corpus_digest

    with pytest.raises(ConflictError, match="corpus"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)


def test_accept_refuses_when_the_headline_metric_dropped(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "PASS"), ("q2", "PASS"), pct=100.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "the-fix")
    after = _record(db_session, _report(("q1", "PASS"), ("q2", "PASS"), pct=90.0), label="after")

    with pytest.raises(ConflictError, match="pct_fully_supported"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)


def test_accept_refuses_a_fix_that_regressed_other_questions(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Gate 6 — the demo beat: the new article hijacked two questions' retrieval. Even though the
    headline percentage did not drop, two questions went PASS -> FAIL, so the system rejects its
    own fix."""
    _record(
        db_session,
        _report(("planted", "FAIL"), ("a", "PASS"), ("b", "PASS"), ("c", "PASS"), pct=75.0),
        label="baseline",
    )
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    # Fix round 2, I3: publish THIS proposal's own draft — the article that "hijacked" retrieval
    # IS this fix, so this is also more faithful to the test's own narrative than an unrelated row.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(
        db_session,
        _report(("planted", "PASS"), ("a", "FAIL"), ("b", "FAIL"), ("c", "PASS"), pct=75.0),
        label="after",
    )

    with pytest.raises(ConflictError) as excinfo:
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    message = str(excinfo.value)
    assert "regress" in message.lower()
    assert "a" in message and "b" in message

    db_session.refresh(proposal)
    assert proposal.status == "proposed"


def test_a_clean_fix_is_accepted_and_stamped(db_session: Session, actor_id: uuid.UUID) -> None:
    before = _record(
        db_session, _report(("planted", "FAIL"), ("a", "PASS"), pct=50.0), label="baseline"
    )
    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="RSUs for employees outside the US",
        rationale="R",
        evidence=_EVIDENCE,
        actor_id=actor_id,
    )
    # Fix round 2, I3: publish THIS proposal's own draft (not an unrelated row) — accept_proposal
    # now requires it.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(
        db_session, _report(("planted", "PASS"), ("a", "PASS"), pct=100.0), label="after"
    )

    check = check_acceptance(db_session, proposal, after.id)
    assert check.blocked_by is None
    assert check.corpus_changed is True
    assert check.regressions == []
    assert check.pct_before == pytest.approx(50.0)
    assert check.pct_after == pytest.approx(100.0)

    accepted = accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    assert accepted.status == "accepted"
    assert accepted.eval_run_before_id == before.id
    assert accepted.eval_run_after_id == after.id


def test_a_decided_proposal_cannot_be_accepted_again(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    # Fix round 2, I3: accept_proposal now requires THIS proposal's own draft to be published
    # (not merely some unrelated row) — publish it directly rather than an unrelated `_publish`.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")
    accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    with pytest.raises(ConflictError, match="accepted"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)


# ---------------------------------------------------------------------------
# accept_proposal — fix round 1 (reviewer C1 CRITICAL, I1 Important): an after-run that does
# not cover the before-run's questions, or that predates it, must not pass the gate.
# ---------------------------------------------------------------------------


def test_accept_refuses_an_after_run_with_zero_results(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """C1: `compare_runs` can only find a regression in a question BOTH runs measured, so an
    EMPTY after-run gives `regressions == []` and the old gate 6 passed vacuously — no forged
    header needed either, since the real harness writes `pct_fully_supported = 0.0` for an empty
    report, and `0.0 >= 0.0` clears the pct gate against a `0.0` baseline (exactly this shape)."""
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    # Fix round 2, I3: publish THIS proposal's own draft (not an unrelated row) — otherwise
    # "draft_not_published" would fire before this test ever reaches the coverage gate.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(db_session, _report(pct=0.0), label="after")  # zero rows

    with pytest.raises(ConflictError, match="did not measure") as excinfo:
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    assert "1" in str(excinfo.value)
    assert "q1" in str(excinfo.value)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"
    assert proposal.eval_run_after_id is None


def test_accept_refuses_an_after_run_covering_only_some_of_the_before_runs_questions(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """C1 — the realistic version: a narrowed re-run (a shipped `--questions <path>` CLI flag)
    legitimately measures fewer questions. A higher pct over a SMALLER question set must not read
    as "no regressions" when the missing questions are exactly the ones that broke."""
    _record(
        db_session,
        _report(("planted", "FAIL"), ("a", "PASS"), ("b", "PASS"), ("c", "PASS"), pct=75.0),
        label="baseline",
    )
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    # Fix round 2, I3: publish THIS proposal's own draft — accept_proposal now requires it.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(db_session, _report(("planted", "PASS"), pct=100.0), label="after")

    with pytest.raises(ConflictError, match="did not measure") as excinfo:
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    message = str(excinfo.value)
    assert "3" in message
    assert "a" in message and "b" in message and "c" in message

    db_session.refresh(proposal)
    assert proposal.status == "proposed"


def test_accept_refuses_an_after_run_older_than_the_before_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I1: a DIFFERENT corpus digest is not a LATER one. `stale` here has a genuinely different
    (earlier) digest and a HIGHER pct than `baseline` — neither the digest gate nor the pct gate
    would catch it on their own — so only an explicit ordering check closes this hole."""
    stale = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="stale-but-good")
    _publish(db_session, "an-earlier-unrelated-change")
    baseline = _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    assert proposal.eval_run_before_id == baseline.id

    with pytest.raises(ConflictError, match="newer"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=stale.id)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"
    assert proposal.eval_run_after_id is None


def test_accept_still_succeeds_with_equal_pct_full_coverage_and_a_later_after_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Regression pin (fix round 1): the two new gates (I1 ordering, C1 coverage) must not
    over-refuse a genuinely clean accept — equal pct, zero regressions, full question coverage,
    and a strictly later after-run must still ACCEPT, exactly as it did before this fix round."""
    before = _record(
        db_session, _report(("planted", "FAIL"), ("a", "PASS"), pct=50.0), label="baseline"
    )
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    # Fix round 2, I3: publish THIS proposal's own draft — accept_proposal now requires it.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(
        db_session, _report(("planted", "FAIL"), ("a", "PASS"), pct=50.0), label="after"
    )

    assert after.created_at > before.created_at
    assert after.pct_fully_supported == before.pct_fully_supported

    check = check_acceptance(db_session, proposal, after.id)
    assert check.blocked_by is None
    assert check.missing_questions == []

    accepted = accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    assert accepted.status == "accepted"
    assert accepted.eval_run_after_id == after.id


# ---------------------------------------------------------------------------
# accept_proposal — fix round 2 (reviewer I2 Important, I3 Important/owner ruling, M5/M6 Minor):
# an empty before-run, a proposal whose own fix was never published (or was published too late
# relative to the after-run), a same-count-different-question-set after-run, and the two
# accept-side boundaries mutation testing showed were untested.
# ---------------------------------------------------------------------------


def test_accept_refuses_when_the_before_run_measured_no_questions(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I2: `compare_runs`' verdict sets are computed over questions BOTH runs measured, so a
    before-run with ZERO questions compares zero questions against anything — a before-side twin
    of C1's after-side hole, reachable via a genuine `--questions <empty.yaml>` harness run (now
    also refused at the source, in `app.eval.groundedness.run_eval`)."""
    _record(db_session, _report(pct=0.0), label="empty-baseline")  # zero rows
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")

    with pytest.raises(ConflictError, match="no questions"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"
    assert proposal.eval_run_after_id is None


def test_accept_refuses_when_the_proposals_own_draft_is_not_published(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I3 (owner ruling): a proposal whose own draft was never published must not be accepted
    against a run whose digest moved for some UNRELATED reason — "validated" must mean this run
    measured a corpus containing THIS fix, not merely a corpus that changed."""
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "an-unrelated-article")  # NOT this proposal's own draft
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")

    with pytest.raises(ConflictError, match="not published"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"
    assert proposal.eval_run_after_id is None


def test_accept_refuses_when_the_after_run_predates_the_publish(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I3 (owner ruling): even when the after-run is newer than the before-run and the corpus
    already looks different, it must have measured a corpus that already contains THIS
    proposal's own published fix — a run recorded before the publish cannot show that, however
    good its numbers look."""
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "an-unrelated-earlier-change")  # moves the digest, unrelated to this fix
    stale_after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="too-early")
    # THIS proposal's own fix is published only AFTER `stale_after` was already recorded.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    with pytest.raises(ConflictError, match="predates"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=stale_after.id)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"
    assert proposal.eval_run_after_id is None


def test_accept_refuses_an_after_run_with_the_same_count_but_a_different_question_set(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """M5: `after.total_questions < before.total_questions` alone cannot catch a same-SIZE,
    different-CONTENT after-run — only `diff.removed` does. Mutation testing (re-review MUT-C)
    showed the whole suite passed even with `diff.removed` deleted from the coverage gate; this
    pins the half of the disjunction that actually does the work."""
    _record(
        db_session,
        _report(("q1", "PASS"), ("q2", "PASS"), ("q3", "FAIL"), pct=66.7),
        label="baseline",
    )
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    # Same COUNT (3) as the baseline, but a DIFFERENT question set: q3 silently dropped, q4
    # silently added.
    after = _record(
        db_session,
        _report(("q1", "PASS"), ("q2", "PASS"), ("q4", "PASS"), pct=100.0),
        label="after",
    )

    with pytest.raises(ConflictError, match="did not measure") as excinfo:
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    assert "q3" in str(excinfo.value)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"


def test_accept_still_succeeds_when_the_after_run_covers_the_before_run_plus_new_questions(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """M6: the golden set growing is a planned, ongoing activity — an after-run that covers every
    before-run question AND adds new ones must still ACCEPT (`>=`, not `==`, is the right
    comparison). Mutation testing (re-review MUT-E: `<` -> `!=`) showed the whole suite passed
    even when this was refused; this pins the accept."""
    before = _record(
        db_session, _report(("planted", "FAIL"), ("a", "PASS"), pct=50.0), label="baseline"
    )
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(
        db_session,
        _report(("planted", "PASS"), ("a", "PASS"), ("new-question", "PASS"), pct=100.0),
        label="after",
    )

    check = check_acceptance(db_session, proposal, after.id)
    assert check.blocked_by is None
    assert check.missing_questions == []

    accepted = accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    assert accepted.status == "accepted"
    assert accepted.eval_run_before_id == before.id
    assert accepted.eval_run_after_id == after.id


def test_accept_refuses_an_after_run_tied_with_the_before_run_at_the_same_instant(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """M6 (tie boundary): gate 5 uses `<=`, not `<` — a hand-stamped exact tie must refuse (fail
    closed: a tie cannot prove the after-run is later). Mutation testing (re-review MUT-F: `<=`
    -> `<`) showed the whole suite passed even when a tie was accepted; this pins the boundary."""
    baseline = _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")
    after.created_at = baseline.created_at  # hand-stamped exact tie
    db_session.flush()

    with pytest.raises(ConflictError, match="newer"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"


# ---------------------------------------------------------------------------
# reject_proposal
# ---------------------------------------------------------------------------


def test_reject_archives_a_published_draft_and_records_the_reason(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="Bad fix",
        rationale="R",
        evidence=[],
        actor_id=actor_id,
    )
    assert proposal.draft_content_id is not None
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    rejected = reject_proposal(
        db_session,
        proposal.id,
        reason="Regressed two questions in run after-2026-09-22.",
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    assert rejected.status == "rejected"
    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None and draft.status == "archived"
    rejection = rejected.evidence["rejection"]
    assert rejection["reason"] == "Regressed two questions in run after-2026-09-22."
    assert rejection["draft_status_after"] == "archived"
    assert isinstance(rejection["at"], str)


def test_reject_leaves_an_unpublished_draft_alone(db_session: Session, actor_id: uuid.UUID) -> None:
    """A draft has no chunks and is invisible to retrieval, and `archive_content` is legal from
    `published` only (the task-00 transition matrix) — so there is nothing to undo and nothing is
    destroyed. The outcome is recorded, not silent."""
    proposal = propose_content_fix(
        db_session,
        kind="retune",
        title="Never published",
        rationale="R",
        evidence=[],
        actor_id=actor_id,
    )

    rejected = reject_proposal(
        db_session,
        proposal.id,
        reason="Threshold change not worth it.",
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None and draft.status == "draft"
    assert rejected.evidence["rejection"]["draft_status_after"] == "draft"


def test_reject_is_only_legal_from_proposed(db_session: Session, actor_id: uuid.UUID) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    # Fix round 2, I3: publish THIS proposal's own draft so the accept below actually succeeds.
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")
    accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    with pytest.raises(ConflictError, match="accepted"):
        reject_proposal(
            db_session,
            proposal.id,
            reason="Too late.",
            actor_id=actor_id,
            pipeline=NoopChunkPipeline(),
        )


def test_reject_raises_not_found_for_an_unknown_proposal(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        reject_proposal(
            db_session, uuid.uuid4(), reason="R", actor_id=None, pipeline=NoopChunkPipeline()
        )
