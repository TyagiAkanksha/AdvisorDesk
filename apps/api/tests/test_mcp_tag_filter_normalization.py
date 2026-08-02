"""Checkpoint fix, finding L-2: read-tool `tag` filters are normalized like tag creation is.

Live symptom: "How many published pieces do we have on tax planning?" (PRD §2.2's own example
command) — the model calls `count_content {"status":"published","tag":"tax planning"}` (a space,
not the stored `"tax-planning"` — PRD §4.1: tag names are "lowercase, hyphenated"). Pre-fix,
`count_content`/`search_content` passed `tag` straight through to `app.services.content.
list_content`, which does an EXACT `Tag.name` match — a confidently wrong `count: 0` came back
while matching rows existed.

Fix: both read tools' `tag` argument is now run through `app.services.tags.normalize_tag_name`
(the exact normalizer tag CREATION already uses) before reaching `list_content`, in
`app.mcp.tools_read._search_content`/`_count_content`. `SYSTEM_PROMPT`
(`app.agent.loop`) also gained one sentence naming the lowercase-hyphenated convention, so the
model is steered to normalize on its own too, not just relying on the tool layer's safety net.

This file is NEW (not a pinned test file) — it does not modify any existing test.

CONVENTIONS.md §10: DB-touching tests request `db_session` and are skipped by fixture name when
`TEST_DATABASE_URL` is unset (see `tests/conftest.py`).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.agent.loop import SYSTEM_PROMPT
from app.mcp.runtime import call_tool
from app.models import User
from app.services import content as content_service
from app.services.lifecycle import NoopChunkPipeline


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — mirrors `tests/test_mcp_read_tools.py::actor_id` (kept local,
    per that file's own no-cross-test-file-dependency precedent)."""
    user = User(email="tag-normalization-admin@example.com", name="Tag Normalization Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


def _seed_published_tax_planning_and_retirement(session: Session, actor_id: uuid.UUID) -> None:
    """Two published `tax-planning` items, one published `retirement` item — enough for a
    tag-filtered count/search to distinguish a correct normalized match (2) from the pre-fix
    `0` (a mismatched exact-match filter) or an over-broad match (3, i.e. no filtering at all)."""
    pipeline = NoopChunkPipeline()
    for title in ("Tax Planning Basics", "Advanced Tax Planning"):
        draft = content_service.create_draft(
            session, title=title, tags=["tax-planning"], actor_id=actor_id
        )
        content_service.publish_content(session, draft.id, actor_id=actor_id, pipeline=pipeline)

    retirement_draft = content_service.create_draft(
        session, title="Retirement Basics", tags=["retirement"], actor_id=actor_id
    )
    content_service.publish_content(
        session, retirement_draft.id, actor_id=actor_id, pipeline=pipeline
    )


# ---------------------------------------------------------------------------
# count_content
# ---------------------------------------------------------------------------


def test_count_content_normalizes_capitalized_tag_name(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`tag="Tax Planning"` (title-cased, spaced) matches the seeded `tax-planning` rows — the
    live PRD §2.2 example command's own conversational phrasing."""
    _seed_published_tax_planning_and_retirement(db_session, actor_id)

    result = call_tool(
        "count_content",
        {"status": "published", "tag": "Tax Planning"},
        session=db_session,
        actor_id=actor_id,
    )

    assert result == {"count": 2}


def test_count_content_normalizes_lowercase_spaced_tag_name(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`tag="tax planning"` (lowercase, spaced — the exact string the live model produced)
    matches the seeded `tax-planning` rows."""
    _seed_published_tax_planning_and_retirement(db_session, actor_id)

    result = call_tool(
        "count_content",
        {"status": "published", "tag": "tax planning"},
        session=db_session,
        actor_id=actor_id,
    )

    assert result == {"count": 2}


# ---------------------------------------------------------------------------
# search_content
# ---------------------------------------------------------------------------


def test_search_content_normalizes_capitalized_tag_name(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """The same normalization applies to `search_content`'s `tag` filter, not just
    `count_content`'s."""
    _seed_published_tax_planning_and_retirement(db_session, actor_id)

    result = call_tool(
        "search_content",
        {"status": "published", "tag": "Tax Planning"},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["count"] == 2
    assert {item["title"] for item in result["items"]} == {
        "Tax Planning Basics",
        "Advanced Tax Planning",
    }


def test_search_content_normalizes_lowercase_spaced_tag_name(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _seed_published_tax_planning_and_retirement(db_session, actor_id)

    result = call_tool(
        "search_content",
        {"status": "published", "tag": "tax planning"},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["count"] == 2


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT — the new sentence naming the lowercase-hyphenated tag convention.
# ---------------------------------------------------------------------------


def test_system_prompt_states_tags_are_lowercase_hyphenated() -> None:
    """Checkpoint fix (finding L-2): the system prompt must tell the model tag names are
    lowercase-hyphenated, so it converts a conversational name itself rather than relying only
    on the tool layer's own normalization. Keyword-based (matches the existing pin style in
    `tests/test_agent_loop.py`'s `test_system_prompt_*` tests — not exact-wording, since the PRD
    marks system-prompt wording "adjustable")."""
    lower = SYSTEM_PROMPT.lower()
    assert "tag" in lower
    assert "lowercase" in lower and "hyphenat" in lower
    assert "tax-planning" in lower, "a concrete example anchors the abstract rule"
