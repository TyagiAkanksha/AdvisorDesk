"""Failing (RED) service-level tests for `app.services.content` + `app.services.lifecycle`.

Task brief: docs/plans/phase-2-auth-cms-crud/task-02-content-tag-services.md,
Step 1. These call the content-service functions directly against a `Session`
(no HTTP, no `TestClient`) — CONVENTIONS.md §10: DB tests run against a
throwaway Postgres schema when `TEST_DATABASE_URL` is set, and are skipped by
fixture name otherwise (see `tests/conftest.py::pytest_collection_modifyitems`).

`app.services.content` and `app.services.lifecycle` do not exist yet: every
test here is expected to fail at collection (`ModuleNotFoundError`) until the
implementer (a separate agent) creates them — that failure IS the RED
evidence this file exists to produce.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy.orm import Session

from app.models import Content, User
from app.services import content as content_service
from app.services.errors import NotFoundError
from app.services.lifecycle import NoopChunkPipeline


@dataclass
class FakeChunkPipeline:
    """Recording fake matching the `ChunkPipeline` protocol shape (brief, Interfaces block).

    `rebuild_chunks(session, content) -> int` / `remove_chunks(session, content_id) -> int` —
    records every call's argument (rather than doing any real chunking/embedding)
    so tests can assert exactly-once / never-called without depending on the
    real (phase-3) embedding pipeline.
    """

    rebuild_return: int = 3
    remove_return: int = 3
    rebuild_calls: list[uuid.UUID] = field(default_factory=list)
    remove_calls: list[uuid.UUID] = field(default_factory=list)

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        self.rebuild_calls.append(content.id)
        return self.rebuild_return

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        self.remove_calls.append(content_id)
        return self.remove_return


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` content-service writes stamp (PRD §4.1)."""
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


# ---- create_draft / generate_slug: §4 slug rules ----


def test_create_draft_sets_uuid_draft_status_and_slug(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Creating "Roth IRA Basics" yields a server-generated uuid, `status='draft'`, and the
    slugified title (PRD §4)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    assert isinstance(content.id, uuid.UUID)
    assert content.status == "draft"
    assert content.slug == "roth-ira-basics"


def test_create_draft_slug_collision_appends_dash_2(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """A second draft with the same title collides on slug and receives the `-2` suffix (PRD §4)."""
    content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    second = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    assert second.slug == "roth-ira-basics-2"


def test_slug_never_reused_after_soft_delete_skips_to_dash_3(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """§9 slug-permanence pin: soft-deleting the first "Roth IRA Basics" frees nothing — a third
    create with the same title still gets `-3`, never reclaiming the deleted row's bare slug
    (PRD §4.1: slug uniqueness spans soft-deleted rows)."""
    first = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.delete_content(
        db_session, first.id, actor_id=actor_id, pipeline=FakeChunkPipeline()
    )

    third = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    assert third.slug == "roth-ira-basics-3"


def test_generate_slug_slugifies_title(db_session: Session) -> None:
    """`generate_slug` on a fresh title returns the plain slugified form (PRD §4)."""
    assert content_service.generate_slug(db_session, "Roth IRA Basics") == "roth-ira-basics"


def test_generate_slug_appends_suffix_on_collision(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`generate_slug` called again for a title already in use previews the next `-N` suffix
    (PRD §4) without needing to create the colliding row itself."""
    content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    assert content_service.generate_slug(db_session, "Roth IRA Basics") == "roth-ira-basics-2"


def test_update_content_title_leaves_slug_unchanged(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Slugs are immutable after creation (PRD §4.1) — editing the title does not change it."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    updated = content_service.update_content(
        db_session,
        content.id,
        title="Roth IRA Basics (Revised)",
        actor_id=actor_id,
        pipeline=FakeChunkPipeline(),
    )

    assert updated.slug == "roth-ira-basics"
    assert updated.title == "Roth IRA Basics (Revised)"


# ---- update_content: actor stamping ----


def test_update_content_stamps_updated_by_and_bumps_updated_at(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Every write through `update_content` stamps `updated_by=actor_id` and advances
    `updated_at` (CONVENTIONS.md §3, PRD §4.1)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    original_updated_at = content.updated_at

    updated = content_service.update_content(
        db_session,
        content.id,
        body_md="revised body",
        actor_id=actor_id,
        pipeline=FakeChunkPipeline(),
    )

    assert updated.updated_by == actor_id
    assert updated.updated_at > original_updated_at


# ---- get_content / list_content: §9 soft-delete-visibility pin ----


def test_get_content_excludes_soft_deleted(db_session: Session, actor_id: uuid.UUID) -> None:
    """§9 soft-delete-visibility pin: a deleted row reads as not-found via `active_select`
    (PRD §4.1)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.delete_content(
        db_session, content.id, actor_id=actor_id, pipeline=FakeChunkPipeline()
    )

    with pytest.raises(NotFoundError):
        content_service.get_content(db_session, content.id)


def test_get_content_raises_not_found_for_unknown_id(db_session: Session) -> None:
    """A content id that never existed also raises `NotFoundError` (brief, Interfaces block)."""
    with pytest.raises(NotFoundError):
        content_service.get_content(db_session, uuid.uuid4())


def test_list_content_excludes_soft_deleted(db_session: Session, actor_id: uuid.UUID) -> None:
    """§9 soft-delete-visibility pin: a deleted item disappears from the list and its total
    (PRD §4.1, §5.2)."""
    kept = content_service.create_draft(db_session, title="Kept", actor_id=actor_id)
    deleted = content_service.create_draft(db_session, title="Deleted", actor_id=actor_id)
    content_service.delete_content(
        db_session, deleted.id, actor_id=actor_id, pipeline=FakeChunkPipeline()
    )

    items, total = content_service.list_content(db_session)

    ids = {item.id for item in items}
    assert kept.id in ids
    assert deleted.id not in ids
    assert total == 1


# ---- delete_content: §4 lifecycle rule (tombstone + chunk removal, status untouched) ----


def test_delete_content_on_published_removes_chunks_and_preserves_status(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """§4 lifecycle rule: deleting a published item removes its chunks in the same transaction
    and sets `is_deleted=True`, but leaves `status='published'` and `published_at` untouched —
    only `is_deleted` governs visibility."""
    draft = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = FakeChunkPipeline()
    published = content_service.publish_content(
        db_session, draft.id, actor_id=actor_id, pipeline=pipeline
    )
    published_at_before = published.published_at

    content_service.delete_content(db_session, published.id, actor_id=actor_id, pipeline=pipeline)
    db_session.refresh(published)

    assert pipeline.remove_calls == [published.id]
    assert published.is_deleted is True
    assert published.status == "published"
    assert published.published_at == published_at_before


# ---- publish_content / archive_content: the ChunkPipeline seam ----


def test_publish_content_sets_status_published_at_and_calls_rebuild_once(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Publishing sets `status='published'` + `published_at`, and calls
    `pipeline.rebuild_chunks` exactly once (PRD §4)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = FakeChunkPipeline()

    published = content_service.publish_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )

    assert published.status == "published"
    assert published.published_at is not None
    assert pipeline.rebuild_calls == [content.id]


def test_archive_content_sets_status_and_calls_remove_chunks(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Archiving a published item sets `status='archived'` and removes its chunks (PRD §4)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = FakeChunkPipeline()
    content_service.publish_content(db_session, content.id, actor_id=actor_id, pipeline=pipeline)

    archived = content_service.archive_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )

    assert archived.status == "archived"
    assert pipeline.remove_calls == [content.id]


def test_update_content_rechunks_when_published(db_session: Session, actor_id: uuid.UUID) -> None:
    """Updating a published item re-chunks: `pipeline.rebuild_chunks` runs again on top of the
    publish-time call (PRD §4 "edit of a published item: re-chunk and re-embed")."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = FakeChunkPipeline()
    content_service.publish_content(db_session, content.id, actor_id=actor_id, pipeline=pipeline)

    content_service.update_content(
        db_session, content.id, body_md="revised body", actor_id=actor_id, pipeline=pipeline
    )

    assert pipeline.rebuild_calls == [content.id, content.id]


def test_update_content_does_not_chunk_when_draft(db_session: Session, actor_id: uuid.UUID) -> None:
    """Updating a draft item never touches the pipeline — re-chunking only happens for
    published items (PRD §4)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = FakeChunkPipeline()

    content_service.update_content(
        db_session, content.id, body_md="revised body", actor_id=actor_id, pipeline=pipeline
    )

    assert pipeline.rebuild_calls == []
    assert pipeline.remove_calls == []


def test_noop_chunk_pipeline_returns_zero_and_does_not_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`NoopChunkPipeline` is the phase-2 default wiring (`app.state.chunk_pipeline`) — it never
    errors and both methods return `0` (brief, Interfaces block); phase-3 task-02 swaps the
    wiring without touching `publish_content`'s signature."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = NoopChunkPipeline()

    published = content_service.publish_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )

    assert published.status == "published"
    assert pipeline.rebuild_chunks(db_session, published) == 0
    assert pipeline.remove_chunks(db_session, published.id) == 0


# ---- list_content: §5.2 filters + pagination ----


def test_list_content_filters_by_status(db_session: Session, actor_id: uuid.UUID) -> None:
    """`status` filters the list to matching rows only (PRD §5.2)."""
    draft = content_service.create_draft(db_session, title="Draft Item", actor_id=actor_id)
    to_publish = content_service.create_draft(db_session, title="Published Item", actor_id=actor_id)
    content_service.publish_content(
        db_session, to_publish.id, actor_id=actor_id, pipeline=FakeChunkPipeline()
    )

    items, total = content_service.list_content(db_session, status="draft")

    assert [item.id for item in items] == [draft.id]
    assert total == 1


def test_list_content_filters_by_tag(db_session: Session, actor_id: uuid.UUID) -> None:
    """`tag` filters the list to content tagged with that tag name (PRD §5.2)."""
    tagged = content_service.create_draft(
        db_session, title="Tagged", tags=("tax-planning",), actor_id=actor_id
    )
    content_service.create_draft(db_session, title="Untagged", actor_id=actor_id)

    items, total = content_service.list_content(db_session, tag="tax-planning")

    assert [item.id for item in items] == [tagged.id]
    assert total == 1


def test_list_content_filters_by_title_search_q(db_session: Session, actor_id: uuid.UUID) -> None:
    """`q` searches by title (PRD §5.2)."""
    match = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.create_draft(db_session, title="529 Plans for Education", actor_id=actor_id)

    items, total = content_service.list_content(db_session, q="Roth")

    assert [item.id for item in items] == [match.id]
    assert total == 1


def test_list_content_pagination_totals(db_session: Session, actor_id: uuid.UUID) -> None:
    """`page`/`page_size` slice the results and `total` reflects the full filtered count,
    independent of the current page (PRD §5.2)."""
    created = [
        content_service.create_draft(db_session, title=f"Item {i}", actor_id=actor_id)
        for i in range(5)
    ]

    page1, total1 = content_service.list_content(db_session, page=1, page_size=2)
    page2, total2 = content_service.list_content(db_session, page=2, page_size=2)
    page3, total3 = content_service.list_content(db_session, page=3, page_size=2)

    assert total1 == 5
    assert total2 == 5
    assert total3 == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    seen_ids = {c.id for c in page1} | {c.id for c in page2} | {c.id for c in page3}
    assert seen_ids == {c.id for c in created}
