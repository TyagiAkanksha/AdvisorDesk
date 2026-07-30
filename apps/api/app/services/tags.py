"""Tag services: normalize-and-reactivate creation, and usage-count listing (PRD §4.1, §5.2)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Content, ContentTag, Tag
from app.services.queries import active_select

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_tag_name(name: str) -> str:
    """Lowercase-hyphenate a raw tag name.

    PRD §4.1: `tags.name` is stored "lowercase, hyphenated, e.g.
    'tax-planning'". Any run of characters outside `[a-z0-9]` (after
    lowercasing) collapses to a single hyphen; leading/trailing hyphens are
    stripped, so `"Tax Planning"` -> `"tax-planning"`.
    """
    return _NORMALIZE_RE.sub("-", name.strip().lower()).strip("-")


def get_or_create_tags(session: Session, names: Sequence[str]) -> list[Tag]:
    """Resolve `names` to `Tag` rows, normalizing and reactivating soft-deleted matches.

    PRD §4.1: `tags.name` uniqueness spans soft-deleted rows — recreating a
    tag whose normalized name matches a soft-deleted row reactivates that
    SAME row (`is_deleted` flips back to `False`, same `id`) instead of
    inserting a duplicate. Deliberately queries `Tag` with no
    `active_select` filter (unlike every other read of `Tag` in this
    module) — this lookup must see a soft-deleted row so it can reactivate
    it, mirroring `app.services.users.upsert_from_google`'s documented
    exception to the same rule.

    Flushes once after resolving every name so every returned `Tag` (new,
    reactivated, or reused) has a real `id` a caller can use immediately
    (e.g. to insert `ContentTag` rows) — never commits (CONVENTIONS.md §3).

    Args:
        session: the caller's `Session`.
        names: raw tag names, in the caller's original casing/spacing.

    Returns:
        One `Tag` per entry in `names`, in the same order, normalized.
    """
    tags: list[Tag] = []
    for raw_name in names:
        normalized = _normalize_tag_name(raw_name)
        tag = session.execute(select(Tag).where(Tag.name == normalized)).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=normalized)
            session.add(tag)
        elif tag.is_deleted:
            tag.is_deleted = False
        tags.append(tag)
    session.flush()
    return tags


def tags_for_contents(
    session: Session, content_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Batch-load each content id's active tag names in one query (no N+1).

    Plan amendment (phase-2 task-02 review round 1, F4): task-03's
    `ContentResponse`/list responses need each item's tags, and `services/`
    is the only layer that touches the ORM (CONVENTIONS.md §2) — so this
    lookup lives here rather than the routes layer looping a per-row query.

    Built on `active_select(Tag)` (joined in as a subquery) rather than an
    ad-hoc `Tag.is_deleted` filter, so a soft-deleted tag's name is excluded
    the same way every other read of `Tag` in this module is (CONVENTIONS.md
    §3).

    Args:
        session: the caller's `Session`.
        content_ids: the `Content.id`s to look up — typically one page of
            `app.services.content.list_content`'s results.

    Returns:
        One entry per id in `content_ids`, even ids with no (non-deleted)
        tags — those map to `[]` rather than being omitted. Each list is
        sorted alphabetically for determinism.
    """
    result: dict[uuid.UUID, list[str]] = {content_id: [] for content_id in content_ids}
    if not content_ids:
        return result

    active_tag = active_select(Tag).subquery()
    stmt = (
        select(ContentTag.content_id, active_tag.c.name)
        .join(active_tag, active_tag.c.id == ContentTag.tag_id)
        .where(ContentTag.content_id.in_(content_ids))
    )
    for content_id, name in session.execute(stmt).tuples().all():
        result[content_id].append(name)

    for names in result.values():
        names.sort()

    return result


def list_tags_with_counts(session: Session) -> list[tuple[Tag, int]]:
    """Return every non-deleted `Tag` with its usage count over non-deleted content.

    PRD §5.2 (`GET /tags`): "list non-deleted tags with usage counts; counts
    include non-deleted content only". Built on `active_select` for both
    `Tag` (the base select, so a soft-deleted tag never appears) and
    `Content` (a subquery left-joined in, so a soft-deleted content row
    never contributes to the count) rather than any ad-hoc `is_deleted`
    filter (CONVENTIONS.md §3).

    Args:
        session: the caller's `Session`.

    Returns:
        `(Tag, count)` pairs, one per non-deleted tag, ordered by name.
        `count` is `0` for a tag with no (non-deleted) content associated.
    """
    active_content = active_select(Content).subquery()

    stmt = (
        active_select(Tag)
        .add_columns(func.count(active_content.c.id))
        .outerjoin(ContentTag, ContentTag.tag_id == Tag.id)
        .outerjoin(active_content, active_content.c.id == ContentTag.content_id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    return list(session.execute(stmt).tuples().all())
