"""The four proposal MCP tools (phase-9 task-16, DESIGN §D) through the real `call_tool` seam."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.agent.loop import SYSTEM_PROMPT
from app.mcp.runtime import call_tool, list_tool_schemas
from app.models import Chunk, Content, User
from app.services.errors import ConflictError, ToolInputError
from app.services.eval_runs import record_run
from app.services.lifecycle import NoopChunkPipeline

_PROPOSAL_TOOL_NAMES = {
    "propose_content_fix",
    "list_proposals",
    "accept_proposal",
    "reject_proposal",
}


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


def _record(session: Session, *, label: str, pct: float, verdict: str):
    return record_run(
        session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict=verdict, fully_supported=verdict == "PASS")],
            pct_fully_supported=pct,
        ),
        label=label,
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        judge_model="gpt-4o",
        similarity_threshold=0.5,
        retrieval_k=6,
    )


def _publish_something(session: Session, slug: str) -> None:
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


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_the_four_proposal_tools_are_registered_with_descriptions() -> None:
    by_name = {entry["name"]: entry for entry in list_tool_schemas()}

    assert _PROPOSAL_TOOL_NAMES <= set(by_name)
    assert len(by_name) == 14
    for name in _PROPOSAL_TOOL_NAMES:
        assert by_name[name]["description"].strip()
    assert "no regressions" in by_name["accept_proposal"]["description"]


# ---------------------------------------------------------------------------
# propose_content_fix
# ---------------------------------------------------------------------------


def test_propose_tool_creates_the_proposal_and_its_draft(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, label="baseline", pct=50.0, verdict="FAIL")

    result = call_tool(
        "propose_content_fix",
        {
            "title": "RSUs for employees outside the US",
            "rationale": "Four near-miss questions in 30 days.",
            "kind": "new_article",
            "evidence": [
                {
                    "normalized_question": "do rsus work outside the us",
                    "count": 4,
                    "kinds": ["near_miss"],
                    "worst_top_similarity": 0.41,
                }
            ],
        },
        session=db_session,
        actor_id=actor_id,
    )

    assert result["status"] == "proposed"
    assert result["kind"] == "new_article"
    assert isinstance(result["id"], str)
    uuid.UUID(result["id"])
    assert isinstance(result["draft_content_id"], str)
    assert result["draft_slug"] == "rsus-for-employees-outside-the-us"
    assert isinstance(result["eval_run_before_id"], str)


def test_propose_tool_derives_the_kind_from_a_failure_cause(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    result = call_tool(
        "propose_content_fix",
        {"title": "Crypto compensation", "rationale": "Refusals.", "failure_cause": "corpus_gap"},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["kind"] == "new_article"


def test_propose_tool_rejects_judge_disagreement_as_a_content_fix(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(ToolInputError, match="judge"):
        call_tool(
            "propose_content_fix",
            {"title": "T", "rationale": "R", "failure_cause": "judge_disagreement"},
            session=db_session,
            actor_id=actor_id,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"title": "T", "rationale": "R"},
        {"title": "T", "rationale": "R", "kind": "new_article", "failure_cause": "corpus_gap"},
        {"title": "   ", "rationale": "R", "kind": "new_article"},
        {"title": "T", "rationale": "R", "kind": "rewrite_all"},
        {"title": "T", "rationale": "R", "kind": "new_article", "bogus": 1},
    ],
)
def test_propose_tool_rejects_bad_arguments(
    db_session: Session, actor_id: uuid.UUID, arguments: dict[str, object]
) -> None:
    """Neither-nor-both `kind`/`failure_cause`, a blank title, an unknown kind, an unknown
    argument — all `ToolInputError` before the service is reached."""
    with pytest.raises(ToolInputError):
        call_tool("propose_content_fix", arguments, session=db_session, actor_id=actor_id)


# ---------------------------------------------------------------------------
# list / accept / reject
# ---------------------------------------------------------------------------


def test_list_tool_returns_json_able_rows_filtered_by_status(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    call_tool(
        "propose_content_fix",
        {"title": "First", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )

    result = call_tool(
        "list_proposals", {"status": "proposed"}, session=db_session, actor_id=actor_id
    )

    assert result["count"] == 1
    row = result["proposals"][0]
    assert row["title"] == "First"
    assert row["status"] == "proposed"
    assert isinstance(row["created_at"], str)
    datetime.fromisoformat(row["created_at"])
    assert result == call_tool("list_proposals", {}, session=db_session, actor_id=actor_id)


def test_accept_tool_accepts_a_clean_fix_and_reports_the_numbers(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, label="baseline", pct=50.0, verdict="FAIL")
    proposed = call_tool(
        "propose_content_fix",
        {"title": "The fix", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )
    # Implementer note (not a behavior/assertion change): "The fix" slugifies to "the-fix" via
    # `create_draft`'s own `generate_slug` (Interfaces: the draft uses the EXISTING content
    # service, so it is slugged exactly like a hand-made draft) — reusing that literal string
    # here would collide on `uq_content_slug` against the draft `propose_content_fix` just
    # created, unconditionally, before this line ever runs. A distinct slug is all this helper
    # needs: the test only cares that publishing SOMETHING moves the corpus fingerprint; nothing
    # downstream reads this slug.
    _publish_something(db_session, "an-unrelated-published-item")
    after = _record(db_session, label="after", pct=100.0, verdict="PASS")

    result = call_tool(
        "accept_proposal",
        {"proposal_id": proposed["id"], "eval_run_after_id": str(after.id)},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["status"] == "accepted"
    assert result["eval_run_after_id"] == str(after.id)
    assert result["pct_before"] == pytest.approx(50.0)
    assert result["pct_after"] == pytest.approx(100.0)
    assert result["regressions"] == 0
    assert result["improvements"] == 1


def test_accept_tool_surfaces_the_gate_refusal_as_a_conflict(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """No `try/except` anywhere in the tool path: the gate's message reaches the caller verbatim
    (the §9 409 envelope over HTTP, the self-correction feedback in the agent loop)."""
    _record(db_session, label="baseline", pct=50.0, verdict="FAIL")
    proposed = call_tool(
        "propose_content_fix",
        {"title": "Unpublished fix", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )
    after = _record(db_session, label="after", pct=100.0, verdict="PASS")

    with pytest.raises(ConflictError, match="corpus"):
        call_tool(
            "accept_proposal",
            {"proposal_id": proposed["id"], "eval_run_after_id": str(after.id)},
            session=db_session,
            actor_id=actor_id,
        )


def test_reject_tool_archives_the_published_draft_through_the_call_tool_pipeline(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Also proves Ruling B's moved pipeline reader works from this module: `call_tool` stashes
    the pipeline, the handler reads it back, `archive_content` gets a real one."""
    proposed = call_tool(
        "propose_content_fix",
        {"title": "Bad fix", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )
    call_tool(
        "publish",
        {"content_id": proposed["draft_content_id"]},
        session=db_session,
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    result = call_tool(
        "reject_proposal",
        {"proposal_id": proposed["id"], "reason": "Regressed two questions."},
        session=db_session,
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    assert result["status"] == "rejected"
    assert result["draft_status_after"] == "archived"
    draft = db_session.get(Content, uuid.UUID(proposed["draft_content_id"]))
    assert draft is not None and draft.status == "archived"


# ---------------------------------------------------------------------------
# Agent awareness
# ---------------------------------------------------------------------------


def test_system_prompt_teaches_the_propose_publish_rerun_accept_sequence() -> None:
    lower = SYSTEM_PROMPT.lower()

    assert "propose_content_fix" in lower
    assert "accept_proposal" in lower
    assert "reject_proposal" in lower
    # It must NOT read as permission to publish on its own initiative (the existing pin at
    # tests/test_agent_loop.py:485 stays green; this is the same rule stated from this side).
    assert "only if the admin asks" in lower or "unless the admin asks" in lower
