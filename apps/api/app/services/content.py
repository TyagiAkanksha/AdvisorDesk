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
from app.services.errors import ConflictError, NotFoundError
from app.services.lifecycle import ChunkPipeline
from app.services.queries import active_select
from app.services.tags import get_or_create_tags

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")
_LIKE_SPECIAL_RE = re.compile(r"[\\%_]")


def _slugify(title: str) -> str:
    """Lowercase-hyphenate `title` into a bare slug candidate (no collision suffix)."""
    return _SLUG_INVALID_RE.sub("-", title.strip().lower()).strip("-")


def _escape_like(value: str) -> str:
    """Backslash-escape LIKE/ILIKE metacharacters (`\\`, `%`, `_`) in `value`.

    Without this, a `q` containing `%` or `_` is silently reinterpreted as a
    wildcard rather than searched for literally (review finding F5) — e.g.
    `q="50%"` would match any title containing "50" followed by anything,
    not just a literal "50%". Callers must pair this with `escape="\\"` on
    the `ilike()` call so the doubled backslash this emits is honored as the
    escape character rather than matched literally.
    """
    return _LIKE_SPECIAL_RE.sub(lambda m: "\\" + m.group(0), value)


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

    Final review, finding F6 (t02 #5): `_slugify` strips every character
    outside `[a-z0-9]`, so a symbols-only, whitespace-only, or unicode-only
    title (e.g. `"!!!"`, `"   "`, `"日本語"`) slugifies to `""` — a public
    slug of `""` would break PRD §5.3's by-slug lookup. Falls back to the
    literal base `"untitled"` in that case, still subject to the same `-2`,
    `-3`, ... collision suffixing as any other slug.

    Args:
        session: the caller's `Session`.
        title: the content title to slugify.

    Returns:
        A slug not already used by any `Content` row, active or deleted.
    """
    base = _slugify(title) or "untitled"
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
        stmt = stmt.where(Content.title.ilike(f"%{_escape_like(q)}%", escape="\\"))

    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

    # `created_at` ties are routine, not exotic: rows created in one transaction
    # share the exact same value (Postgres `now()` == `transaction_timestamp()`,
    # constant for the whole transaction), so `ORDER BY created_at DESC` alone
    # leaves the relative order of tied rows undefined across separate
    # OFFSET/LIMIT queries — paging can silently drop or duplicate rows.
    # `Content.id.desc()` is a stable, unique tiebreaker (review finding F1).
    paged_stmt = (
        stmt.order_by(Content.created_at.desc(), Content.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(session.execute(paged_stmt).scalars().all())

    return items, total


def list_published_content(session: Session) -> list[Content]:
    """Return every published, non-deleted `Content` row, newest-published first (PRD §5.3).

    Distinct from `list_content` (PRD §5.2's paginated admin list) rather
    than a parameter bolted onto it: `GET /public/content` is a bare,
    unpaginated feed (test-author-resolved, controller-approved — mirrors
    `app.services.tags.list_tags_with_counts` / `GET /tags`'s own bare
    `list[TagWithCount]` shape, task-03 test-author report ambiguity #1),
    so reusing `list_content`'s `(items, total)`/`page`/`page_size` contract
    would mean faking an unbounded `page_size` to avoid truncating the feed
    at its default of 20 — messier, and riskier for `list_content`'s
    existing callers/tests, than one small dedicated read. This leaves
    `list_content`'s signature completely untouched.

    Built on `active_select(Content)` so a soft-deleted row never appears
    (§9 pin) even though its `status` stays `'published'` — `delete_content`
    deliberately leaves `status`/`published_at` untouched (PRD §4.1) — plus
    an explicit `status == 'published'` filter, since `active_select` alone
    only excludes soft-deleted rows, not drafts/archived ones.

    Ordered `published_at` DESC (test-author ambiguity #2, controller-
    approved: newest first) with `Content.id.desc()` as a stable tiebreaker
    for rows sharing the same `published_at`, mirroring `list_content`'s own
    `created_at`-tie rationale (review finding F1).

    Args:
        session: the caller's `Session`.

    Returns:
        Every published, non-deleted `Content` row, newest-published first.
    """
    stmt = (
        active_select(Content)
        .where(Content.status == "published")
        .order_by(Content.published_at.desc(), Content.id.desc())
    )
    return list(session.execute(stmt).scalars().all())


def get_published_by_slug(session: Session, slug: str) -> Content:
    """Return the published, non-deleted `Content` row for `slug` (PRD §5.3).

    §9 public soft-delete-visibility pin: a soft-deleted row keeps
    `status='published'` (PRD §4.1's delete leaves lifecycle fields
    untouched), so `active_select` plus an explicit `status` filter is
    required together — either alone would wrongly surface a
    soft-deleted-but-still-`published` row, or a draft/archived one.
    Mirrors `get_content`'s active-row discipline for the admin by-id
    route. A slug belonging to a draft/archived item, or one that never
    existed, 404s the same way (PRD §4.1: a deleted item's slug is never
    reassigned, so this 404 is permanent, not until some other item claims
    the slug).

    Review round 1, finding I1: `slug` is an unvalidated path parameter on
    this app's only unauthenticated, DB-touching route
    (`GET /public/content/{slug}`) — a caller can send a NUL byte
    (`.../content/abc%00def`), which a real `_slugify`-generated slug
    (`[a-z0-9-]` only, see that function's docstring) can never contain. A
    NUL byte survives FastAPI's path decoding and reaches Postgres, whose
    text comparison rejects it (psycopg raises `DataError`), which would
    otherwise bubble past every typed handler to the generic 500 — a free,
    anonymous, error-log-flood vector. Short-circuiting to "no match" here
    (skipping the query entirely) instead routes it through the exact same
    `NotFoundError` and `f"content slug {slug!r} not found"` message
    construction as any other not-found slug, so the response is
    byte-for-byte indistinguishable from an unknown slug's 404 — no new
    branch's worth of distinguishing information leaks to the caller.

    Args:
        session: the caller's `Session`.
        slug: the `Content.slug` to look up.

    Returns:
        The published, non-deleted `Content` row.

    Raises:
        NotFoundError: no published, non-deleted row exists for `slug`,
            including a `slug` containing a NUL byte (`"\x00"`), which is
            never queried against the DB (finding I1).
    """
    content = (
        session.execute(
            active_select(Content).where(Content.slug == slug, Content.status == "published")
        ).scalar_one_or_none()
        if "\x00" not in slug
        else None
    )
    if content is None:
        raise NotFoundError(f"content slug {slug!r} not found")
    return content


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
    """Publish `content_id` (task-00 pinned transition matrix, PRD §4 lifecycle rule).

    `draft`/`archived` -> `published` in both cases; `published` ->
    `published` is a no-op transition, not an error (idempotent re-POST).
    `published_at` is stamped iff it is currently `NULL` — the first
    successful publish — and never overwritten afterwards, so the public
    feed's `published_at DESC` order (`list_published_content`) stays stable
    across any later re-publish.

    Chunk pipeline call depends on the starting status:

    - `draft`: `rebuild_chunks` (first publish — nothing to preserve).
    - `archived`: `rebuild_chunks` — `archive_content` already removed this
      item's chunks, so skipping here would publish an unretrievable item.
    - `published`: no pipeline call at all. This is safe without comparing
      the stored chunks to the current `body_md`: `update_content`
      re-chunks atomically on every edit of an already-published item (PRD
      §4), so a published row's chunks always already reflect its current
      body — "body unchanged since last embed" is the only state reachable
      through the API/MCP surface here, so no diffing mechanism or schema
      change is needed to know it's safe to skip.

    Args:
        session: the caller's `Session`.
        content_id: the `Content.id` to publish.
        actor_id: the authenticated admin performing this write.
        pipeline: the `ChunkPipeline` whose `rebuild_chunks` is called
            (except on the `published` -> `published` no-op above).

    Returns:
        The published `Content` row.

    Raises:
        NotFoundError: no active row exists for `content_id`.
    """
    content = get_content(session, content_id)
    already_published = content.status == "published"
    content.status = "published"
    if content.published_at is None:
        content.published_at = datetime.now(UTC)
    _touch(content, actor_id)
    session.flush()
    if not already_published:
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

    Legal from `published` only (task-00 pinned transition matrix): `draft`
    -> `archive` and `archived` -> `archive` both raise `ConflictError`
    before touching the row or the pipeline, naming both the current status
    and the attempted action in the message.

    Args:
        session: the caller's `Session`.
        content_id: the `Content.id` to archive.
        actor_id: the authenticated admin performing this write.
        pipeline: the `ChunkPipeline` whose `remove_chunks` is called.

    Returns:
        The archived `Content` row.

    Raises:
        NotFoundError: no active row exists for `content_id`.
        ConflictError: `content_id`'s current status is not `published`.
    """
    content = get_content(session, content_id)
    if content.status != "published":
        raise ConflictError(f"Cannot archive content with status {content.status!r}.")
    content.status = "archived"
    _touch(content, actor_id)
    session.flush()
    pipeline.remove_chunks(session, content.id)
    return content
