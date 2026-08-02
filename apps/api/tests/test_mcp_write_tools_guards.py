"""Fix round 1 guard tests for phase-5 task-02's six MCP write tools (commit fcca3a9 review).

Covers the three Important findings from `.superpowers/sdd/reports/p5-t02-review.md`:

- I1: `app.mcp.tools_write._pipeline_from_session` must FAIL LOUD (`RuntimeError`) — not
  silently substitute a `NoopChunkPipeline()` — when a write-tool handler is reached without
  going through `app.mcp.runtime.call_tool`'s stash. A silent fallback there would let e.g.
  `publish` commit a `status='published'` row with zero chunks (PRD §4).
- I2: `SESSION_INFO_PIPELINE_KEY` moved from `app.services.lifecycle` to `app.mcp.tool_spec`
  (a services-layer module should not own an MCP-only symbol). No new runtime behavior to
  pin beyond "the existing suite still imports/uses it from its new home" — covered by every
  test below plus the whole existing `test_mcp_write_tools.py` suite still passing unchanged.
- I3: two `tag_content` PRD §6 contracts the original suite left unpinned: (a) `add`
  reactivates a SOFT-DELETED tag name with the SAME `Tag.id` (the `tag_content`-tool half of
  the §4.1 reactivation clause — `create_draft`'s half is pinned at
  `tests/test_mcp_write_tools.py:167`); (b) when a name appears in BOTH `add` and `remove` in
  one call, `add` wins (the implementer's disclosed, previously-untested ordering call).

This is a NEW file — `tests/test_mcp_write_tools.py` (and the other three pinned files) are
untouched; see the fix-round report for before/after hash verification.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp.runtime import call_tool
from app.mcp.tool_spec import SESSION_INFO_PIPELINE_KEY
from app.mcp.tools_write import ContentIdArgs, _publish
from app.models import Tag, User
from app.services import content as content_service
from app.services.tags import get_or_create_tags


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — mirrors `tests/test_mcp_write_tools.py::actor_id` (kept
    local per that file's own no-cross-test-file-dependency precedent)."""
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


# ---------------------------------------------------------------------------
# I1 — _pipeline_from_session fails loud when call_tool's stash never happened
# ---------------------------------------------------------------------------


def test_write_handler_invoked_outside_call_tool_raises_loud_runtime_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I1: calling a write-tool handler directly (bypassing `call_tool`, so `session.info`
    never carries a pipeline) must raise `RuntimeError` naming the wiring gap — not silently
    fall back to a `NoopChunkPipeline()` and let `publish` "succeed" with zero chunks.
    """
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_id = draft.id
    db_session.commit()

    assert SESSION_INFO_PIPELINE_KEY not in db_session.info

    with pytest.raises(RuntimeError, match="ChunkPipeline"):
        _publish(ContentIdArgs(content_id=content_id), session=db_session, actor_id=actor_id)

    # The loud failure happens BEFORE `publish_content` is ever called (it's raised while
    # resolving the `pipeline=` argument), so nothing was flushed — but roll back and re-read
    # from a fresh query anyway, proving no published-without-chunks row snuck through.
    db_session.rollback()
    reread = content_service.get_content(db_session, content_id)
    assert reread.status == "draft"
    assert reread.published_at is None


def test_call_tool_still_defaults_to_noop_pipeline_for_write_tools(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I1 non-regression: `call_tool` itself must keep defaulting `pipeline=None` to
    `NoopChunkPipeline()` — that's the seam `_pipeline_from_session` relies on to never see a
    missing key on the normal (in-process/HTTP) path. Going through `call_tool` without
    passing `pipeline=` (read-tool ergonomics + several pinned tests already rely on this)
    must keep working, not raise.
    """
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    result = call_tool(
        "publish", {"content_id": str(draft.id)}, session=db_session, actor_id=actor_id
    )

    assert result["status"] == "published"


# ---------------------------------------------------------------------------
# I3(a) — tag_content's `add` reactivates a soft-deleted tag name, same Tag.id
# ---------------------------------------------------------------------------


def test_tag_content_add_reactivates_soft_deleted_tag_name_with_same_id(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I3 / PRD §6 `tag_content` row: "Tags in `add` are created if missing (reactivating
    soft-deleted names, §4.1)" — the `tag_content`-tool half of the reactivation clause
    (`create_draft`'s half is already pinned at `tests/test_mcp_write_tools.py:167`).
    """
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    (tag,) = get_or_create_tags(db_session, ["estate-planning"])
    original_tag_id = tag.id
    tag.is_deleted = True
    db_session.flush()

    result = call_tool(
        "tag_content",
        {"content_id": str(draft.id), "add": ["estate-planning"]},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["tags"] == ["estate-planning"]
    reactivated = db_session.execute(select(Tag).where(Tag.name == "estate-planning")).scalar_one()
    assert reactivated.id == original_tag_id
    assert reactivated.is_deleted is False


# ---------------------------------------------------------------------------
# I3(b) — a name in both add and remove in one call: add wins
# ---------------------------------------------------------------------------


def test_tag_content_add_wins_when_same_name_in_add_and_remove(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """I3 / implementer Judgment call 2 (`app/services/content.py:396-398`): `remove` is
    applied before `add`, so a name present in both lists ends up associated. Starts from a
    content item that's already tagged "retirement" so this exercises a real
    remove-then-re-add round trip, not a no-op.
    """
    draft = content_service.create_draft(
        db_session, title="Roth IRA Basics", tags=["retirement"], actor_id=actor_id
    )

    result = call_tool(
        "tag_content",
        {"content_id": str(draft.id), "add": ["retirement"], "remove": ["retirement"]},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["tags"] == ["retirement"]
