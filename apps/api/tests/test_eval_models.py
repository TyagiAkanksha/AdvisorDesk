"""Schema pins for the phase-9 tables and the two new `chat_messages` signal columns."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession, ContentProposal, EvalResult, EvalRun


def _run(session: Session, **overrides: object) -> EvalRun:
    values: dict[str, object] = {
        "label": "baseline",
        "embedding_model": "text-embedding-3-small",
        "chat_model": "gpt-4o-mini",
        "judge_model": "gpt-4o",
        "similarity_threshold": 0.5,
        "retrieval_k": 6,
        "corpus_content_count": 17,
        "corpus_chunk_count": 100,
        "corpus_max_updated_at": datetime.now(UTC),
        "corpus_digest": "0123456789abcdef",
        "total_questions": 21,
        "pct_fully_supported": 58.8,
        "refusal_correct": 4,
        "refusal_total": 4,
    }
    values.update(overrides)
    run = EvalRun(**values)  # type: ignore[arg-type]
    session.add(run)
    session.flush()
    return run


def test_eval_run_defaults_kind_answer_and_empty_git_sha(db_session: Session) -> None:
    run = _run(db_session)
    db_session.expire(run)
    assert run.kind == "answer"
    assert run.git_sha == ""
    assert isinstance(run.id, uuid.UUID)


def test_eval_run_kind_check_rejects_unknown_kind(db_session: Session) -> None:
    # `_run` flushes, so the CHECK violation surfaces from inside the helper.
    with pytest.raises(IntegrityError):
        _run(db_session, kind="bogus")
    db_session.rollback()


def test_eval_result_unique_per_run_and_question(db_session: Session) -> None:
    run = _run(db_session)
    for _ in range(2):
        db_session.add(
            EvalResult(
                run_id=run.id,
                question="What is a Roth IRA conversion and how is it taxed?",
                answerable=True,
                expected_slugs=["roth-ira-conversion-basics"],
                cited_slugs=["roth-ira-conversion-basics"],
                slugs_hit=True,
                fully_supported=True,
                refused=False,
                verdict="PASS",
                top_similarity=0.81,
                answer_text="It is a taxable event.",
            )
        )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_eval_result_metrics_jsonb_round_trips_and_cascades_with_its_run(
    db_session: Session,
) -> None:
    run = _run(db_session)
    db_session.add(
        EvalResult(
            run_id=run.id,
            question="q1",
            question_class="near_miss",
            persona="Sam",
            answerable=True,
            expected_slugs=[],
            cited_slugs=[],
            slugs_hit=False,
            fully_supported=None,
            refused=True,
            verdict="FAIL",
            top_similarity=None,
            answer_text="",
            metrics={"recall_at_k": 0.0, "failure_cause": "corpus_gap"},
        )
    )
    db_session.flush()
    stored = db_session.scalars(select(EvalResult)).one()
    assert stored.metrics == {"recall_at_k": 0.0, "failure_cause": "corpus_gap"}
    assert stored.question_class == "near_miss"

    db_session.delete(run)
    db_session.flush()
    assert db_session.scalars(select(EvalResult)).all() == []


def test_content_proposal_defaults_proposed_and_rejects_bad_kind(db_session: Session) -> None:
    proposal = ContentProposal(
        kind="new_article",
        title="RSUs for non-US employees",
        rationale="10 near-miss questions in 30 days",
        evidence={"weak_queries": []},
    )
    db_session.add(proposal)
    db_session.flush()
    db_session.expire(proposal)
    assert proposal.status == "proposed"
    assert isinstance(proposal.updated_at, datetime)

    db_session.add(ContentProposal(kind="bogus", title="t", rationale="r", evidence={}))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("value", [0, 2, -2])
def test_chat_message_feedback_check_rejects_values_other_than_minus_one_and_one(
    db_session: Session, value: int
) -> None:
    chat_session = ChatSession()
    db_session.add(chat_session)
    db_session.flush()
    db_session.add(
        ChatMessage(session_id=chat_session.id, role="assistant", content="a", feedback=value)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("value", [-1, 1, None])
def test_chat_message_feedback_accepts_minus_one_one_and_null(
    db_session: Session, value: int | None
) -> None:
    chat_session = ChatSession()
    db_session.add(chat_session)
    db_session.flush()
    message = ChatMessage(
        session_id=chat_session.id, role="assistant", content="a", feedback=value, latency_ms=1234
    )
    db_session.add(message)
    db_session.flush()
    db_session.expire(message)
    assert message.feedback == value
    assert message.latency_ms == 1234
