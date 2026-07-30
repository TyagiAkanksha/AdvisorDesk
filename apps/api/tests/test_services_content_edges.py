"""Review-round regression tests for `app.services.content` + `app.services.tags`.

Phase-2 task-02 review round 1 (`.superpowers/sdd/phase-2/p2-t02-implementer-report.md`,
"Fix round 1"). `tests/test_services_content.py` and `tests/test_services_tags_stats.py`
are sha256-pinned by the test-author agent and must not change — every new test the
review round required lives here instead, one file per the fix brief's hard rule.

Covers, one section per finding:

- F1: `list_content` pagination is stable across `created_at` ties.
- F2: `create_draft`/`update_content` actor stamping (`author_id` set once,
  `updated_by` on every write).
- F3: `update_content`'s `tags=<list>` / `tags=()` / `tags=None` semantics.
- F4: `app.services.tags.tags_for_contents` batch lookup.
- F5: `list_content`'s `q` escapes LIKE/ILIKE metacharacters.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when
`TEST_DATABASE_URL` is set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContentTag, Tag, User
from app.services import content as content_service
from app.services import tags as tags_service
from app.services.lifecycle import NoopChunkPipeline


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` content-service writes stamp (PRD §4.1)."""
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


@pytest.fixture
def other_actor_id(db_session: Session) -> uuid.UUID:
    """A second seeded `User` id, distinct from `actor_id` — for "the actor changed" tests."""
    user = User(email="other-admin@example.com", name="Other Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


def _tag_names_for(session: Session, content_id: uuid.UUID) -> set[str]:
    """Read back the live tag names associated with `content_id`, straight from the ORM."""
    rows = session.execute(
        select(Tag.name)
        .join(ContentTag, ContentTag.tag_id == Tag.id)
        .where(ContentTag.content_id == content_id)
    ).all()
    return {row[0] for row in rows}


# ---- F1: list_content pagination is stable across created_at ties ----


def test_list_content_pagination_no_drops_or_duplicates_on_created_at_ties(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Rows created in one transaction share the same `created_at` (Postgres `now()`
    == `transaction_timestamp()`, constant per transaction) — `order_by` must include
    `Content.id.desc()` as a tiebreaker so paging over ties is well-defined: the union
    of every page is exactly the full set, with no drops and no duplicates.

    120 rows (not the brief's ballpark ~25) because that is the scale the review
    finding itself reproduced at ("120 same-transaction rows paging with 4 dropped
    + 4 duplicated") — confirmed locally: at ~25 rows this Postgres instance's sort
    happens to stay stable across the 3 OFFSET/LIMIT queries even pre-fix (false
    negative), but at 120 rows it reliably drops rows without the `Content.id.desc()`
    tiebreaker, exactly matching the reviewer's report."""
    created = [
        content_service.create_draft(db_session, title=f"Tie Item {i}", actor_id=actor_id)
        for i in range(120)
    ]

    seen_ids: list[uuid.UUID] = []
    total = None
    for page in range(1, 13):
        items, page_total = content_service.list_content(db_session, page=page, page_size=10)
        total = page_total
        seen_ids.extend(item.id for item in items)

    assert total == 120
    assert len(seen_ids) == 120  # no duplicates across pages
    assert set(seen_ids) == {c.id for c in created}  # no drops across pages


# ---- F2: actor stamping at creation and on update ----


def test_create_draft_stamps_both_author_id_and_updated_by_to_actor(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`create_draft` stamps BOTH `author_id` and `updated_by` to `actor_id` (PRD §4.1:
    `author_id` is set once at creation; the creating actor is, as of creation, also
    the last writer)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    assert content.author_id == actor_id
    assert content.updated_by == actor_id


def test_update_content_changes_updated_by_but_never_author_id(
    db_session: Session, actor_id: uuid.UUID, other_actor_id: uuid.UUID
) -> None:
    """`update_content` stamps `updated_by` to the NEW acting actor but never touches
    `author_id` — `author_id` is set once at creation and never changed (PRD §4.1)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)

    updated = content_service.update_content(
        db_session,
        content.id,
        body_md="revised body",
        actor_id=other_actor_id,
        pipeline=NoopChunkPipeline(),
    )

    assert updated.updated_by == other_actor_id
    assert updated.author_id == actor_id


# ---- F3: update_content tag semantics — list replaces, () clears, None untouched ----


def test_update_content_tags_list_fully_replaces_associations(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`tags=<list>` is a FULL replace: the old association set is gone, only the new
    set remains."""
    content = content_service.create_draft(
        db_session, title="Roth IRA Basics", tags=("tax-planning",), actor_id=actor_id
    )

    updated = content_service.update_content(
        db_session,
        content.id,
        tags=["retirement", "estate-planning"],
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    assert _tag_names_for(db_session, updated.id) == {"retirement", "estate-planning"}


def test_update_content_tags_empty_tuple_clears_associations_but_keeps_tag_rows(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`tags=()` clears ALL associations but leaves the `Tag` row itself alive (not
    deleted) — only the `ContentTag` join rows are removed."""
    content = content_service.create_draft(
        db_session, title="Roth IRA Basics", tags=("tax-planning",), actor_id=actor_id
    )
    tag_id = db_session.execute(select(Tag.id).where(Tag.name == "tax-planning")).scalar_one()

    updated = content_service.update_content(
        db_session, content.id, tags=(), actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    assert _tag_names_for(db_session, updated.id) == set()
    tag_row = db_session.execute(select(Tag).where(Tag.id == tag_id)).scalar_one()
    assert tag_row.is_deleted is False


def test_update_content_tags_none_leaves_associations_untouched(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`tags=None` (the default) leaves existing tag associations completely
    untouched."""
    content = content_service.create_draft(
        db_session, title="Roth IRA Basics", tags=("tax-planning",), actor_id=actor_id
    )

    updated = content_service.update_content(
        db_session, content.id, body_md="revised", actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    assert _tag_names_for(db_session, updated.id) == {"tax-planning"}


# ---- F4: tags_for_contents batch lookup ----


def test_tags_for_contents_batch_lookup_matrix(db_session: Session, actor_id: uuid.UUID) -> None:
    """Batch-loads tags for several content ids in one query on a seeded matrix: a
    content with multiple tags, one with zero tags, and one whose only tag is
    soft-deleted (excluded)."""
    tagged = content_service.create_draft(
        db_session, title="Tagged", tags=("retirement", "tax-planning"), actor_id=actor_id
    )
    untagged = content_service.create_draft(db_session, title="Untagged", actor_id=actor_id)
    with_deleted_tag = content_service.create_draft(
        db_session, title="With Deleted Tag", tags=("legacy",), actor_id=actor_id
    )
    legacy_tag = db_session.execute(select(Tag).where(Tag.name == "legacy")).scalar_one()
    legacy_tag.is_deleted = True
    db_session.flush()

    result = tags_service.tags_for_contents(
        db_session, [tagged.id, untagged.id, with_deleted_tag.id]
    )

    assert result[tagged.id] == ["retirement", "tax-planning"]  # sorted alphabetically
    assert result[untagged.id] == []
    assert result[with_deleted_tag.id] == []


def test_tags_for_contents_empty_input_returns_empty_dict(db_session: Session) -> None:
    """An empty `content_ids` sequence short-circuits to `{}` with no query."""
    assert tags_service.tags_for_contents(db_session, []) == {}


# ---- F5: list_content's q escapes LIKE/ILIKE metacharacters ----


def test_list_content_q_escapes_percent_metacharacter(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`%` in `q` is a literal character, not an ILIKE any-string wildcard — `q="50%"`
    matches only the title containing that literal substring."""
    percent_item = content_service.create_draft(
        db_session, title="Save 50% today", actor_id=actor_id
    )
    content_service.create_draft(db_session, title="Save 50 percent", actor_id=actor_id)

    items, total = content_service.list_content(db_session, q="50%")

    assert [item.id for item in items] == [percent_item.id]
    assert total == 1


def test_list_content_q_underscore_does_not_act_as_wildcard(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`_` in `q` is a literal single character, not an ILIKE any-single-char
    wildcard."""
    exact_item = content_service.create_draft(db_session, title="A_B Exact", actor_id=actor_id)
    content_service.create_draft(db_session, title="AxB Other", actor_id=actor_id)

    items, total = content_service.list_content(db_session, q="A_B")

    assert [item.id for item in items] == [exact_item.id]
    assert total == 1
