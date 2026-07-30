"""Content services: draft/list/update/lifecycle transitions (PRD §4, §4.1, §5.2).

Every write function stamps `actor_id` into `Content.updated_by` and bumps
`Content.updated_at` (CONVENTIONS.md §3: "`updated_at` is maintained by the
service layer on every write. No DB triggers."). `create_draft` additionally
stamps `author_id` (PRD §4.1: "doubles as the created-by column, set once at
creation, never changed").
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import Content, ContentTag, Tag
from app.services.errors import NotFoundError
from app.services.lifecycle import ChunkPipeline
from app.services.queries import active_select
from app.services.tags import get_or_create_tags

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    """Lowercase-hyphenate `title` into a bare slug candidate (no collision suffix)."""
    return _SLUG_INVALID_RE.sub("-", title.strip().lower()).strip("-")


def generate_slug(session: Session, title: str) -> str:
    """Return the next available slug for `title` (PRD §4 slug rules).

    Slugifies `title`, then appends `-2`, `-3`, ... on collision with any
    existing slug. Deliberately queries `Content.slug` with no
    `active_select` filter (PRD §4.1: "slug uniqueness is global and
    includes soft-deleted rows... a deleted item's slug is never reused") —
    unlike every other read of `Content` in this module, this one must see
    soft-deleted rows so their slugs stay permanently reserved, mirroring
    `app.services.tags.get_or_create_tags`'s documented exception to the
    same active-read convention.

    Args:
        session: the caller's `Session`.
        title: the content title to slugify.

    Returns:
        A slug not already used by any `Content` row, active or deleted.
    """
    base = _slugify(title)
    existing = set(
        session.execute(
            select(Content.slug).where(or_(Content.slug == base, Content.slug.like(f"{base}-%")))
        ).scalars()
    )
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"


def _replace_tags(session: Session, content: Content, tag_names: Sequence[str]) -> None:
    """Replace `content`'s tag associations with the resolved set of `tag_names`.

    Deletes every existing `ContentTag` row for `content.id`, then inserts
    one per name resolved through `get_or_create_tags` (normalizing and
    reactivating soft-deleted tags per PRD §4.1). Duplicate resolved tag ids
    (e.g. two input names normalizing to the same tag) are collapsed to one
    `ContentTag` row, since `(content_id, tag_id)` is the composite primary
    key.
    """
    session.execute(delete(ContentTag).where(ContentTag.content_id == content.id))
    seen: set[uuid.UUID] = set()
    for tag in get_or_create_tags(session, tag_names):
        if tag.id in seen:
            continue
        seen.add(tag.id)
        session.add(ContentTag(content_id=content.id, tag_id=tag.id))


def _touch(content: Content, actor_id: uuid.UUID | None) -> None:
    """Stamp `updated_by=actor_id` and bump `updated_at` (CONVENTIONS.md §3, every write)."""
    content.updated_by = actor_id
    content.updated_at = datetime.now(UTC)


def create_draft(
    session: Session,
    *,
    title: str,
    body_md: str = "",
    tags: Sequence[str] = (),
    actor_id: uuid.UUID | None,
) -> Content:
    """Create a new draft `Content` row with a server-generated slug (PRD §4).

    Stamps `author_id=actor_id` (set once, never changed) and
    `updated_by=actor_id` (the actor performed this write). Flushes (never
    commits, CONVENTIONS.md §3) so the returned row has a real `id`/slug and
    any constraint violation surfaces immediately to the caller.

    Args:
        session: the caller's `Session`.
        title: the content title; slugified into `Content.slug` (§4 rules).
        body_md: the initial Markdown body; defaults to empty.
        tags: raw tag names to associate (normalized + reactivated via
            `app.services.tags.get_or_create_tags`).
        actor_id: the authenticated admin creating this draft, or `None`
            for the seed script (PRD §4.1).

    Returns:
        The newly created `Content` row, `status='draft'`.
    """
    content = Content(
        title=title,
        slug=generate_slug(session, title),
        body_md=body_md,
        author_id=actor_id,
        updated_by=actor_id,
    )
    session.add(content)
    session.flush()
    if tags:
        _replace_tags(session, content, tags)
        session.flush()
    return content


def get_content(session: Session, content_id: uuid.UUID) -> Content:
    """Return the active `Content` row for `content_id`.

    PRD §4.1 / §9 soft-delete-visibility pin: a soft-deleted row (or an id
    that never existed) reads as not-found, via `active_select` — never an
    ad-hoc `is_deleted` filter (CONVENTIONS.md §3).

    Args:
        session: the caller's `Session`.
        content_id: the `Content.id` to look up.

    Returns:
        The active `Content` row.

    Raises:
        NotFoundError: no active row exists for `content_id`.
    """
    content = session.execute(
        active_select(Content).where(Content.id == content_id)
    ).scalar_one_or_none()
    if content is None:
        raise NotFoundError(f"content {content_id} not found")
    return content


def list_content(
    session: Session,
    *,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Content], int]:
    """List active `Content` rows, optionally filtered, with pagination (PRD §5.2).

    Built on `active_select(Content)` so soft-deleted rows never appear in
    either the page or the total (§9 soft-delete-visibility pin). The `tag`
    filter matches by tag name (already-normalized, as it arrives from the
    `?tag=` query string) via a join restricted to `active_select(Tag)`, so
    a soft-deleted tag's name never matches.

    Args:
        session: the caller's `Session`.
        status: exact `Content.status` match, if given.
        tag: exact tag-name match, if given.
        q: case-insensitive title substring search, if given.
        page: 1-indexed page number.
        page_size: rows per page.

    Returns:
        `(items, total)` — `items` is the requested page; `total` is the
        full filtered count, independent of pagination.
    """
    stmt = active_select(Content)
    if status is not None:
        stmt = stmt.where(Content.status == status)
    if tag is not None:
        active_tag = active_select(Tag).where(Tag.name == tag).subquery()
        stmt = stmt.join(ContentTag, ContentTag.content_id == Content.id).join(
            active_tag, active_tag.c.id == ContentTag.tag_id
        )
    if q is not None:
        stmt = stmt.where(Content.title.ilike(f"%{q}%"))

    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

    paged_stmt = (
        stmt.order_by(Content.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = list(session.execute(paged_stmt).scalars().all())

    return items, total


def update_content(
    session: Session,
    content_id: uuid.UUID,
    *,
    title: str | None = None,
    body_md: str | None = None,
    tags: Sequence[str] | None = None,
    actor_id: uuid.UUID | None,
    pipeline: ChunkPipeline,
) -> Content:
    """Update an active `Content` row's title/body/tags; the slug never changes (PRD §4.1).

    Re-chunks through `pipeline.rebuild_chunks` iff the item is currently
    published (PRD §4: "edit of a published item: re-chunk and re-embed");
    a draft's update never touches the pipeline.

    Args:
        session: the caller's `Session`.
        content_id: the `Content.id` to update.
        title: new title, if given (slug is unaffected either way).
        body_md: new Markdown body, if given.
        tags: the full replacement set of raw tag names, if given (`None`
            leaves existing tag associations untouched).
        actor_id: the authenticated admin performing this write.
        pipeline: the `ChunkPipeline` to re-chunk through when published.

    Returns:
        The updated `Content` row.

    Raises:
        NotFoundError: no active row exists for `content_id`.
    """
    content = get_content(session, content_id)
    if title is not None:
        content.title = title
    if body_md is not None:
        content.body_md = body_md
    if tags is not None:
        _replace_tags(session, content, tags)
    _touch(content, actor_id)
    session.flush()

    if content.status == "published":
        pipeline.rebuild_chunks(session, content)

    return content


def delete_content(
    session: Session,
    content_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None,
    pipeline: ChunkPipeline,
) -> None:
    """Soft-delete `content_id`: tombstone + chunk removal in one transaction (PRD §4).

    Sets `is_deleted=True` and calls `pipeline.remove_chunks`, but leaves
    `status`/`published_at` untouched — `is_deleted` alone governs
    visibility, so a deleted item's lifecycle history is preserved. There is
    no restore path (PRD §4.1, §12).

    Args:
        session: the caller's `Session` — flush only; the caller commits
            (CONVENTIONS.md §3), keeping the tombstone and chunk removal in
            one transaction as PRD §4 requires.
        content_id: the `Content.id` to soft-delete.
        actor_id: the authenticated admin performing this write.
        pipeline: the `ChunkPipeline` whose `remove_chunks` is called.

    Raises:
        NotFoundError: no active row exists for `content_id`.
    """
    content = get_content(session, content_id)
    content.is_deleted = True
    _touch(content, actor_id)
    session.flush()
    pipeline.remove_chunks(session, content.id)


def publish_content(
    session: Session,
    content_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None,
    pipeline: ChunkPipeline,
) -> Content:
    """Publish `content_id`: set `status='published'` + `published_at`, then chunk (PRD §4).

    Args:
        session: the caller's `Session`.
        content_id: the `Content.id` to publish.
        actor_id: the authenticated admin performing this write.
        pipeline: the `ChunkPipeline` whose `rebuild_chunks` is called
            exactly once.

    Returns:
        The published `Content` row.

    Raises:
        NotFoundError: no active row exists for `content_id`.
    """
    content = get_content(session, content_id)
    content.status = "published"
    content.published_at = datetime.now(UTC)
    _touch(content, actor_id)
    session.flush()
    pipeline.rebuild_chunks(session, content)
    return content


def archive_content(
    session: Session,
    content_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None,
    pipeline: ChunkPipeline,
) -> Content:
    """Archive `content_id`: set `status='archived'` and remove its chunks (PRD §4).

    Args:
        session: the caller's `Session`.
        content_id: the `Content.id` to archive.
        actor_id: the authenticated admin performing this write.
        pipeline: the `ChunkPipeline` whose `remove_chunks` is called.

    Returns:
        The archived `Content` row.

    Raises:
        NotFoundError: no active row exists for `content_id`.
    """
    content = get_content(session, content_id)
    content.status = "archived"
    _touch(content, actor_id)
    session.flush()
    pipeline.remove_chunks(session, content.id)
    return content
