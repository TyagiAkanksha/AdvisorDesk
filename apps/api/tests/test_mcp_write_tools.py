"""Failing (RED) tests for the six MCP write tools (task-02 Step 1).

Task brief: docs/plans/phase-5-mcp-agent/task-02-mcp-write-tools.md, Step 1.
Spec: advisordesk-prd.md §6 tool table, §4 lifecycle rule, §4.1 actor/tag/soft-delete
conventions.

Everything here goes through `app.mcp.runtime.call_tool` directly (no HTTP, no
`TestClient`, no import of `app.mcp.tools_write`) — the exact seam task-03's agent loop
calls, and the one the controller's brief pins as the RED-mode boundary: `call_tool`
already exists (task-01), and today only `search_content`/`count_content` are
registered, so calling any of `create_draft`/`edit_content`/`delete_content`/
`tag_content`/`publish`/`archive` is expected to fail with `ToolNotFoundError` until the
implementer (a separate agent) creates `app/mcp/tools_write.py` and registers its
`ToolSpec`s. That `ToolNotFoundError` IS the RED evidence most tests below produce.

PIPELINE-THREADING ASSUMPTION (test-author decision, binding on the implementer per the
controller's brief: "design your tests around the OBVIOUS extension... state your
assumption explicitly"): `call_tool`'s signature today is
`call_tool(name, arguments, *, session, actor_id) -> dict` — no `ChunkPipeline` seam,
because the two read tools never need one. `publish`/`archive`/`delete_content`/
`edit_content` all wrap `app.services.content` functions that take a REQUIRED
`pipeline: ChunkPipeline` keyword argument, so that seam must reach the write tools
somehow. This file assumes and pins the following extension:

    call_tool(name, arguments, *, session, actor_id, pipeline: ChunkPipeline | None = None)

i.e. `call_tool` grows one new OPTIONAL keyword-only parameter, defaulting to
`NoopChunkPipeline()` when omitted (mirroring `app.factory.create_app`'s own
`chunk_pipeline: ChunkPipeline | None = None` -> `NoopChunkPipeline()` default — the
existing precedent for this exact seam elsewhere in this codebase) — never a module-level
mutable registry set via `monkeypatch`, per CONVENTIONS.md §10's "external seams are
injectable, never monkeypatched at a distance" rule (this seam is directly analogous to
that section's own listed examples: `Embedder`/LLM protocols into `rag` modules). The
write-tool handlers must obtain this pipeline through whatever internal mechanism the
implementer chooses (e.g. `session.info`) WITHOUT changing the 3-argument
`(args, *, session, actor_id)` handler-call shape `app.mcp.runtime.call_tool`'s existing
call site (`spec.handler(args, session=session, actor_id=actor_id)`) already uses for
every tool — that call site, and the read-tool handlers in `tools_read.py`, are pinned by
`tests/test_mcp_read_tools.py`/`tests/test_mcp_runtime_guards.py` and must not change.

Until the implementer adds this parameter, every test below that passes `pipeline=...` to
`call_tool` fails RED with `TypeError: call_tool() got an unexpected keyword argument
'pipeline'` rather than `ToolNotFoundError` — expected, and IS the RED evidence for the
pipeline-threading half of this task's contract (see this file's RED run in the test-author
report for the itemized list of which tests hit which failure mode).

CONVENTIONS.md §10: DB-touching tests request `db_session` and are skipped by fixture name
when `TEST_DATABASE_URL` is unset (see `tests/conftest.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp.runtime import call_tool
from app.models import Content, Tag, User
from app.services import content as content_service
from app.services.errors import (
    ConflictError,
    EmbeddingFailedError,
    NotFoundError,
    ToolInputError,
)
from app.services.lifecycle import NoopChunkPipeline
from app.services.tags import get_or_create_tags


@dataclass
class RecordingChunkPipeline:
    """Recording fake matching the `ChunkPipeline` protocol shape (`app.services.lifecycle`).

    Mirrors `tests/test_lifecycle_transitions.py::RecordingChunkPipeline` /
    `tests/test_services_content.py::FakeChunkPipeline` field-for-field (both PINNED
    reference files) — records every call's argument so a test can assert exactly-once /
    never-called behavior through the `call_tool` seam, without depending on the real
    (phase-4) embedding pipeline.
    """

    rebuild_return: int = 0
    remove_return: int = 0
    rebuild_calls: list[uuid.UUID] = field(default_factory=list)
    remove_calls: list[uuid.UUID] = field(default_factory=list)

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        self.rebuild_calls.append(content.id)
        return self.rebuild_return

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        self.remove_calls.append(content_id)
        return self.remove_return


@dataclass
class FailingChunkPipeline:
    """`ChunkPipeline` fake whose `rebuild_chunks` always raises `EmbeddingFailedError`.

    The §4 atomicity pin's trigger for the `publish` tool's failure test — mirrors
    `tests/test_lifecycle.py::FailingEmbedder`'s role, but at the `ChunkPipeline` seam
    `call_tool`'s `pipeline` argument takes (this file's own assumption, see module
    docstring) rather than the lower-level `Embedder` seam that file exercises directly.
    """

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        raise EmbeddingFailedError(
            "embedding provider call failed (FailingChunkPipeline test fake)"
        )

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        raise AssertionError("remove_chunks should not be called by this test")


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` `call_tool` takes (PRD §4.1).

    Mirrors `tests/test_mcp_read_tools.py::actor_id` (PINNED reference): kept local rather
    than imported, per that file's own no-cross-test-file-dependency precedent.
    """
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


@pytest.fixture
def other_actor_id(db_session: Session) -> uuid.UUID:
    """A second seeded `User` row's id — lets a test prove `updated_by` is the CALL's own
    actor, not merely whatever actor created the row."""
    user = User(email="editor@example.com", name="Test Editor")
    db_session.add(user)
    db_session.flush()
    return user.id


# ---------------------------------------------------------------------------
# create_draft
# ---------------------------------------------------------------------------


def test_create_draft_returns_id_slug_draft_status_and_stamps_actor(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §6: `create_draft` returns `{id, slug}`; the row is `status='draft'` with
    `author_id`/`updated_by` stamped to the acting admin (PRD §4.1)."""
    result = call_tool(
        "create_draft",
        {"title": "Roth IRA Basics", "body_md": "Some body", "tags": []},
        session=db_session,
        actor_id=actor_id,
    )

    assert set(result.keys()) == {"id", "slug"}
    assert result["slug"] == "roth-ira-basics"

    content = db_session.get(Content, uuid.UUID(result["id"]))
    assert content is not None
    assert content.status == "draft"
    assert content.author_id == actor_id
    assert content.updated_by == actor_id


def test_create_draft_reactivates_soft_deleted_tag_name_with_same_id(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """§4.1 pin: creating a draft tagged with a name matching a SOFT-DELETED tag reactivates
    that same row (same `id`, `is_deleted` flips back to `False`) rather than inserting a
    duplicate."""
    (tag,) = get_or_create_tags(db_session, ["tax-planning"])
    original_tag_id = tag.id
    tag.is_deleted = True
    db_session.flush()

    call_tool(
        "create_draft",
        {"title": "Roth IRA Basics", "tags": ["tax-planning"]},
        session=db_session,
        actor_id=actor_id,
    )

    reactivated = db_session.execute(select(Tag).where(Tag.name == "tax-planning")).scalar_one()
    assert reactivated.id == original_tag_id
    assert reactivated.is_deleted is False


def test_create_draft_empty_title_raises_tool_input_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """§9 floor: an empty title is a `ToolInputError`, not a degenerate row (mirrors
    `ContentCreate.title`'s `min_length=1` REST validation, PRD §6/§9)."""
    with pytest.raises(ToolInputError):
        call_tool("create_draft", {"title": ""}, session=db_session, actor_id=actor_id)


# ---------------------------------------------------------------------------
# edit_content
# ---------------------------------------------------------------------------


def test_edit_content_body_change_on_published_item_calls_rebuild_chunks_once(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §4/§6: editing a PUBLISHED item's `body_md` re-chunks/re-embeds exactly once."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.publish_content(
        db_session, draft.id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    pipeline = RecordingChunkPipeline()

    call_tool(
        "edit_content",
        {"content_id": str(draft.id), "body_md": "revised body"},
        session=db_session,
        actor_id=actor_id,
        pipeline=pipeline,
    )

    assert pipeline.rebuild_calls == [draft.id]


def test_edit_content_body_change_on_draft_never_calls_pipeline(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §4/§6: editing a DRAFT's `body_md` never touches the chunk pipeline."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()

    call_tool(
        "edit_content",
        {"content_id": str(draft.id), "body_md": "revised body"},
        session=db_session,
        actor_id=actor_id,
        pipeline=pipeline,
    )

    assert pipeline.rebuild_calls == []


def test_edit_content_stamps_updated_by_as_the_acting_admin(
    db_session: Session, actor_id: uuid.UUID, other_actor_id: uuid.UUID
) -> None:
    """PRD §4.1: `updated_by` records the CALL's own actor — distinct from `author_id`, which
    stays the original creator."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    call_tool(
        "edit_content",
        {"content_id": str(draft.id), "body_md": "revised body"},
        session=db_session,
        actor_id=other_actor_id,
    )

    assert draft.updated_by == other_actor_id
    assert draft.author_id == actor_id


def test_edit_content_title_edit_leaves_slug_unchanged(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §4.1: slugs are immutable after creation — editing the title never changes it."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    result = call_tool(
        "edit_content",
        {"content_id": str(draft.id), "title": "Roth IRA Basics (Revised)"},
        session=db_session,
        actor_id=actor_id,
    )

    assert set(result.keys()) == {"id", "slug", "status"}
    assert result["slug"] == "roth-ira-basics"


def test_edit_content_soft_deleted_id_raises_not_found_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """MCP half of the §9 soft-delete-visibility pin: a soft-deleted `content_id` is
    not-found through `edit_content`, exactly like the REST route."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.delete_content(
        db_session, draft.id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    with pytest.raises(NotFoundError):
        call_tool(
            "edit_content",
            {"content_id": str(draft.id), "title": "New Title"},
            session=db_session,
            actor_id=actor_id,
        )


# ---------------------------------------------------------------------------
# delete_content
# ---------------------------------------------------------------------------


def test_delete_content_soft_deletes_and_removes_chunks_returns_deleted_true(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §4/§6: soft-delete tombstones the row AND removes its chunks in one call."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.publish_content(
        db_session, draft.id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    pipeline = RecordingChunkPipeline()

    result = call_tool(
        "delete_content",
        {"content_id": str(draft.id)},
        session=db_session,
        actor_id=actor_id,
        pipeline=pipeline,
    )

    assert result == {"deleted": True}
    assert draft.is_deleted is True
    assert pipeline.remove_calls == [draft.id]


def test_delete_content_unknown_id_raises_not_found_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(NotFoundError):
        call_tool(
            "delete_content",
            {"content_id": str(uuid.uuid4())},
            session=db_session,
            actor_id=actor_id,
        )


# ---------------------------------------------------------------------------
# tag_content
# ---------------------------------------------------------------------------


def test_tag_content_adds_and_removes_tags_in_one_call(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §6: `add`/`remove` apply together in one call; `add` creates a missing tag."""
    draft = content_service.create_draft(
        db_session, title="Roth IRA Basics", tags=["retirement"], actor_id=actor_id
    )

    result = call_tool(
        "tag_content",
        {"content_id": str(draft.id), "add": ["tax-planning"], "remove": ["retirement"]},
        session=db_session,
        actor_id=actor_id,
    )

    assert set(result.keys()) == {"id", "tags"}
    assert result["id"] == str(draft.id)
    assert set(result["tags"]) == {"tax-planning"}


def test_tag_content_soft_deleted_id_raises_not_found_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.delete_content(
        db_session, draft.id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    with pytest.raises(NotFoundError):
        call_tool(
            "tag_content",
            {"content_id": str(draft.id), "add": ["tax-planning"]},
            session=db_session,
            actor_id=actor_id,
        )


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


def test_publish_draft_to_published_builds_chunks_and_sets_published_at(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """PRD §4/§6: publishing a draft runs the full publish transaction — status, published_at,
    chunk build."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()

    result = call_tool(
        "publish",
        {"content_id": str(draft.id)},
        session=db_session,
        actor_id=actor_id,
        pipeline=pipeline,
    )

    assert set(result.keys()) == {"id", "status", "published_at"}
    assert result["status"] == "published"
    assert result["published_at"] is not None
    assert pipeline.rebuild_calls == [draft.id]


def test_publish_already_published_preserves_published_at_and_does_not_rebuild_again(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """t00-inheritance pin: re-publishing an already-published item through the tool path
    preserves `published_at` exactly and does NOT re-call the pipeline (task-00 hardened
    `publish_content`, PRD §4)."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()

    first = call_tool(
        "publish",
        {"content_id": str(draft.id)},
        session=db_session,
        actor_id=actor_id,
        pipeline=pipeline,
    )
    second = call_tool(
        "publish",
        {"content_id": str(draft.id)},
        session=db_session,
        actor_id=actor_id,
        pipeline=pipeline,
    )

    assert second["published_at"] == first["published_at"]
    assert pipeline.rebuild_calls == [draft.id]


def test_publish_embedding_failure_propagates_and_leaves_item_draft_after_rollback(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """§4 atomicity through the tool path: an embedding failure raises `EmbeddingFailedError`
    and, once the caller rolls back (`call_tool` itself never commits/rollbacks —
    CONVENTIONS.md §3), the item is still `draft` with no `published_at`.

    Committed-baseline shape (mirrors `tests/test_lifecycle.py`'s rollback tests): the draft is
    committed BEFORE the failing `publish` call, so the later `db_session.rollback()` only undoes
    the failing call's own (flushed-but-uncommitted) writes, not the draft's own creation — a
    plain `db_session` (no savepoint wrapping) has one open transaction, and rolling it back after
    an uncommitted `create_draft` would discard the draft row too, making the post-rollback
    `get_content` read raise `NotFoundError` instead of exercising the atomicity pin this test is
    for.
    """
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_id = draft.id
    db_session.commit()

    with pytest.raises(EmbeddingFailedError):
        call_tool(
            "publish",
            {"content_id": str(content_id)},
            session=db_session,
            actor_id=actor_id,
            pipeline=FailingChunkPipeline(),
        )

    db_session.rollback()

    reread = content_service.get_content(db_session, content_id)
    assert reread.status == "draft"
    assert reread.published_at is None


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


def test_archive_published_to_archived_removes_chunks(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.publish_content(
        db_session, draft.id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )
    pipeline = RecordingChunkPipeline()

    result = call_tool(
        "archive",
        {"content_id": str(draft.id)},
        session=db_session,
        actor_id=actor_id,
        pipeline=pipeline,
    )

    assert set(result.keys()) == {"id", "status"}
    assert result["status"] == "archived"
    assert pipeline.remove_calls == [draft.id]


def test_archive_unknown_id_raises_not_found_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(NotFoundError):
        call_tool(
            "archive",
            {"content_id": str(uuid.uuid4())},
            session=db_session,
            actor_id=actor_id,
        )


def test_archive_draft_raises_conflict_error(db_session: Session, actor_id: uuid.UUID) -> None:
    """t00-inheritance pin: archiving a DRAFT is illegal (task-00 hardened `archive_content`'s
    pinned transition matrix, PRD §4) — surfaces as `ConflictError` through the tool path too."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    with pytest.raises(ConflictError):
        call_tool(
            "archive",
            {"content_id": str(draft.id)},
            session=db_session,
            actor_id=actor_id,
        )


# ---------------------------------------------------------------------------
# Cross-cutting: extra="forbid" must carry over from the read tools (t01 pattern)
# ---------------------------------------------------------------------------


def test_misspelled_argument_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """A misspelled `tags` (as `tagz`) on `create_draft` is rejected by name, not silently
    dropped — the same `extra="forbid"` pattern `tools_read.py`'s args models already use
    (`SearchContentArgs`/`CountContentArgs`, fix round 1 finding I5)."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool(
            "create_draft",
            {"title": "Roth IRA Basics", "tagz": ["tax-planning"]},
            session=db_session,
            actor_id=actor_id,
        )

    assert "tagz" in str(exc_info.value)
