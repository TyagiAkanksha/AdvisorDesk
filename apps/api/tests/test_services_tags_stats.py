"""Failing (RED) service-level tests for `app.services.tags` + `app.services.stats`.

Task brief: docs/plans/phase-2-auth-cms-crud/task-02-content-tag-services.md,
Step 5. Setup builds `Content`/`Tag`/`ContentTag` rows directly through the
ORM (not via `app.services.content`) so these tests exercise `tags.py`/
`stats.py` in isolation and never fail because of an unrelated bug in
`content.py` — CONVENTIONS.md §10: DB tests run against a throwaway Postgres
schema when `TEST_DATABASE_URL` is set, and are skipped by fixture name
otherwise (see `tests/conftest.py::pytest_collection_modifyitems`).

`app.services.tags` and `app.services.stats` do not exist yet: every test
here is expected to fail at collection (`ModuleNotFoundError`) until the
implementer (a separate agent) creates them — that failure IS the RED
evidence this file exists to produce.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Content, ContentTag, Tag
from app.services import stats as stats_service
from app.services import tags as tags_service

# ---- get_or_create_tags: normalization + §9 reactivation pin ----


def test_get_or_create_tags_normalizes_to_lowercase_hyphenated(db_session: Session) -> None:
    """`"Tax Planning"` normalizes to `"tax-planning"` (PRD §4.1)."""
    (created,) = tags_service.get_or_create_tags(db_session, ["Tax Planning"])

    assert created.name == "tax-planning"


def test_get_or_create_tags_reuses_existing_active_row(db_session: Session) -> None:
    """Re-requesting a name that already has an active row returns that same row, not a
    duplicate."""
    existing = Tag(name="tax-planning")
    db_session.add(existing)
    db_session.flush()

    (found,) = tags_service.get_or_create_tags(db_session, ["Tax Planning"])

    assert found.id == existing.id
    assert found.is_deleted is False


def test_get_or_create_tags_reactivates_soft_deleted_row_same_id(db_session: Session) -> None:
    """§9 tag-reactivation pin: recreating a tag whose name matches a soft-deleted row
    reactivates that SAME row (`is_deleted` flips back to `False`, same `id`) rather than
    inserting a duplicate (PRD §4.1)."""
    existing = Tag(name="tax-planning", is_deleted=True)
    db_session.add(existing)
    db_session.flush()
    original_id = existing.id

    (reactivated,) = tags_service.get_or_create_tags(db_session, ["Tax Planning"])

    assert reactivated.id == original_id
    assert reactivated.is_deleted is False


# ---- list_tags_with_counts: exclude deleted tags; count non-deleted content only ----


def test_list_tags_with_counts_counts_only_non_deleted_content(db_session: Session) -> None:
    """Usage counts include non-deleted content only (PRD §5.2, §9 tag-reactivation test
    group: "usage counts ignore soft-deleted content")."""
    tag = Tag(name="tax-planning")
    db_session.add(tag)
    db_session.flush()

    active_a = Content(title="A", slug="a")
    active_b = Content(title="B", slug="b")
    deleted_c = Content(title="C", slug="c", is_deleted=True)
    db_session.add_all([active_a, active_b, deleted_c])
    db_session.flush()

    db_session.add_all(
        [
            ContentTag(content_id=active_a.id, tag_id=tag.id),
            ContentTag(content_id=active_b.id, tag_id=tag.id),
            ContentTag(content_id=deleted_c.id, tag_id=tag.id),
        ]
    )
    db_session.flush()

    pairs = tags_service.list_tags_with_counts(db_session)

    counts = {t.name: count for t, count in pairs}
    assert counts["tax-planning"] == 2


def test_list_tags_with_counts_excludes_soft_deleted_tags(db_session: Session) -> None:
    """A soft-deleted tag never appears in the list, regardless of its usage count (PRD §4.1)."""
    active_tag = Tag(name="active-tag")
    deleted_tag = Tag(name="deleted-tag", is_deleted=True)
    db_session.add_all([active_tag, deleted_tag])
    db_session.flush()

    pairs = tags_service.list_tags_with_counts(db_session)

    names = {t.name for t, _ in pairs}
    assert "active-tag" in names
    assert "deleted-tag" not in names


def test_list_tags_with_counts_zero_for_untagged_tag(db_session: Session) -> None:
    """A tag with no content associations still lists, with a count of `0` (PRD §5.2: "list
    non-deleted tags with usage counts")."""
    tag = Tag(name="unused-tag")
    db_session.add(tag)
    db_session.flush()

    pairs = tags_service.list_tags_with_counts(db_session)

    counts = {t.name: count for t, count in pairs}
    assert counts["unused-tag"] == 0


# ---- content_stats: by_status / by_tag on a seeded matrix, soft-deleted excluded ----


def test_content_stats_by_status_and_by_tag_excludes_soft_deleted(db_session: Session) -> None:
    """`content_stats` reports counts by status and by tag over a seeded matrix, excluding
    soft-deleted content entirely from both breakdowns (PRD §5.2, §9)."""
    tax_tag = Tag(name="tax-planning")
    retirement_tag = Tag(name="retirement")
    db_session.add_all([tax_tag, retirement_tag])
    db_session.flush()

    draft1 = Content(title="Draft 1", slug="draft-1", status="draft")
    draft2 = Content(title="Draft 2", slug="draft-2", status="draft")
    published1 = Content(title="Published 1", slug="published-1", status="published")
    archived1 = Content(title="Archived 1", slug="archived-1", status="archived")
    deleted_published = Content(
        title="Deleted Published",
        slug="deleted-published",
        status="published",
        is_deleted=True,
    )
    db_session.add_all([draft1, draft2, published1, archived1, deleted_published])
    db_session.flush()

    db_session.add_all(
        [
            ContentTag(content_id=draft1.id, tag_id=tax_tag.id),
            ContentTag(content_id=published1.id, tag_id=tax_tag.id),
            ContentTag(content_id=archived1.id, tag_id=retirement_tag.id),
            ContentTag(content_id=deleted_published.id, tag_id=tax_tag.id),
        ]
    )
    db_session.flush()

    result = stats_service.content_stats(db_session)

    assert result.by_status == {"draft": 2, "published": 1, "archived": 1}
    assert result.by_tag == {"tax-planning": 2, "retirement": 1}
