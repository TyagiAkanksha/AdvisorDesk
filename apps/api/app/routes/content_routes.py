"""Admin CMS REST routes: content CRUD + transitions, tags, stats (PRD §5.2, task-03 brief).

CONVENTIONS.md §4: routes contain no `try/except` — typed errors raised by
`app.services.*` (`NotFoundError`, etc.) flow to
`app.routes.errors::register_error_handlers`, which builds the PRD §9
envelope. Thin: parse -> call service -> DTO.

`ContentResponse.tags` is populated via `app.services.tags.tags_for_contents`
— the ONLY tag lookup these routes perform; `Tag`/`ContentTag` are never
queried directly here (task-03 brief Interfaces block, task-02 review
amendment). List responses batch this into one call for the whole page
(no N+1); by-id responses call it once for their single id.
"""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.deps import AdminPrincipal, require_admin
from app.models import Content
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.content import (
    ContentCreate,
    ContentListResponse,
    ContentResponse,
    ContentStatus,
    ContentUpdate,
)
from app.models.schemas.stats import StatsResponse
from app.models.schemas.tags import TagWithCount
from app.routes.deps import get_chunk_pipeline, get_session
from app.services import content as content_service
from app.services.lifecycle import ChunkPipeline
from app.services.stats import content_stats
from app.services.tags import list_tags_with_counts, tags_for_contents

# Review round 1, finding F2: every route below sits behind `require_admin`
# (401), and all but `tags_list`/`stats_get` (no request fields) can 422 —
# declared once here rather than repeated on each decorator, a simplicity
# trade that knowingly over-declares 422 on those two. `ErrorEnvelope` (not FastAPI's default
# `HTTPValidationError{detail}`) replaces the 422 schema too, so the
# committed `openapi.json` baseline — and both frontends' codegen — reflect
# the `{"error": {"code","message"}}` shape `register_error_handlers`
# actually renders (CONVENTIONS.md §8).
router = APIRouter(
    responses={401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)

# PRD §5.2: page_size is bounded so a caller can't force an unbounded scan;
# 100 is a generous ceiling for an admin CMS list, not asserted by any test.
_MAX_PAGE_SIZE = 100

# The five by-id routes additionally 404 (soft-deleted/unknown id, PRD §5) —
# merged with `router.responses` (401/422 above) by FastAPI's own
# router-then-route `responses` merge, not repeated per decorator.
_BY_ID_RESPONSES: dict[int | str, dict[str, object]] = {404: {"model": ErrorEnvelope}}

# `content_archive` alone also 409s (task-00 pinned transition matrix:
# archive is illegal from `draft`/`archived`) — `content_publish` has no
# illegal transition (it's idempotent from every reachable status), so it
# stays on the plain `_BY_ID_RESPONSES` above.
_ARCHIVE_RESPONSES: dict[int | str, dict[str, object]] = {
    **_BY_ID_RESPONSES,
    409: {"model": ErrorEnvelope},
}


def _to_content_response(content: Content, tags: list[str]) -> ContentResponse:
    """Build a `ContentResponse` from an ORM `Content` row plus its resolved tag names."""
    return ContentResponse(
        id=content.id,
        title=content.title,
        slug=content.slug,
        body_md=content.body_md,
        # `Content.status` (the ORM row) is a plain `Mapped[str]` —
        # `app/models/content.py` deliberately does not import the
        # schemas-layer `ContentStatus` Literal (schemas depend on the ORM
        # layer, not the reverse). The DB `status_valid` CheckConstraint
        # guarantees the value is always one of the three, so the cast here
        # is the one place that runtime guarantee becomes a static one.
        status=cast(ContentStatus, content.status),
        tags=tags,
        author_id=content.author_id,
        updated_by=content.updated_by,
        published_at=content.published_at,
        created_at=content.created_at,
        updated_at=content.updated_at,
    )


@router.get("/content", operation_id="content_list", response_model=ContentListResponse)
def content_list(
    status: ContentStatus | None = Query(default=None),
    tag: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=_MAX_PAGE_SIZE),
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ContentListResponse:
    """PRD §5.2: list content, filtered by `status`/`tag`/`q`, paginated.

    `q=""` (present but empty) is treated identically to `q` omitted — no
    title filter — per the task-03 brief's explicit pin.
    """
    items, total = content_service.list_content(
        session,
        status=status,
        tag=tag,
        q=q or None,
        page=page,
        page_size=page_size,
    )
    tag_names_by_id = tags_for_contents(session, [item.id for item in items])
    return ContentListResponse(
        items=[_to_content_response(item, tag_names_by_id[item.id]) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/content",
    operation_id="content_create",
    response_model=ContentResponse,
    status_code=201,
)
def content_create(
    body: ContentCreate,
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ContentResponse:
    """PRD §5.2: create a draft `Content` row (slug generated per §4 rules)."""
    content = content_service.create_draft(
        session,
        title=body.title,
        body_md=body.body_md,
        tags=body.tags,
        actor_id=principal.user_id,
    )
    tags = tags_for_contents(session, [content.id])[content.id]
    return _to_content_response(content, tags)


@router.get(
    "/content/{content_id}",
    operation_id="content_get",
    response_model=ContentResponse,
    responses=_BY_ID_RESPONSES,
)
def content_get(
    content_id: uuid.UUID,
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ContentResponse:
    """PRD §5.2: fetch one active `Content` row by id (soft-deleted/unknown -> 404, §5)."""
    content = content_service.get_content(session, content_id)
    tags = tags_for_contents(session, [content.id])[content.id]
    return _to_content_response(content, tags)


@router.patch(
    "/content/{content_id}",
    operation_id="content_update",
    response_model=ContentResponse,
    responses=_BY_ID_RESPONSES,
)
def content_update(
    content_id: uuid.UUID,
    body: ContentUpdate,
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
    pipeline: ChunkPipeline = Depends(get_chunk_pipeline),
) -> ContentResponse:
    """PRD §5.2: update title/body/tags (slug unchanged); re-chunks iff already published."""
    content = content_service.update_content(
        session,
        content_id,
        title=body.title,
        body_md=body.body_md,
        tags=body.tags,
        actor_id=principal.user_id,
        pipeline=pipeline,
    )
    tags = tags_for_contents(session, [content.id])[content.id]
    return _to_content_response(content, tags)


@router.delete(
    "/content/{content_id}",
    operation_id="content_delete",
    status_code=204,
    responses=_BY_ID_RESPONSES,
)
def content_delete(
    content_id: uuid.UUID,
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
    pipeline: ChunkPipeline = Depends(get_chunk_pipeline),
) -> Response:
    """PRD §5.2: soft-delete (tombstone + chunk removal in one transaction); no restore."""
    content_service.delete_content(
        session, content_id, actor_id=principal.user_id, pipeline=pipeline
    )
    return Response(status_code=204)


@router.post(
    "/content/{content_id}/publish",
    operation_id="content_publish",
    response_model=ContentResponse,
    responses=_BY_ID_RESPONSES,
)
def content_publish(
    content_id: uuid.UUID,
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
    pipeline: ChunkPipeline = Depends(get_chunk_pipeline),
) -> ContentResponse:
    """PRD §5.2/§4: publish — status -> published, (re)chunks.

    Legal from every status (task-00 pinned transition matrix,
    `app.services.content.publish_content`): `draft`/`archived` -> `published`
    rebuilds chunks (an `archived` starting point still rebuilds, since
    archiving already removed its chunks); `published` -> `published` is an
    idempotent no-op re-publish — no error, no re-chunk. `published_at` is
    stamped only on the first successful publish and preserved, unchanged,
    on every later re-publish.
    """
    content = content_service.publish_content(
        session, content_id, actor_id=principal.user_id, pipeline=pipeline
    )
    tags = tags_for_contents(session, [content.id])[content.id]
    return _to_content_response(content, tags)


@router.post(
    "/content/{content_id}/archive",
    operation_id="content_archive",
    response_model=ContentResponse,
    responses=_ARCHIVE_RESPONSES,
)
def content_archive(
    content_id: uuid.UUID,
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
    pipeline: ChunkPipeline = Depends(get_chunk_pipeline),
) -> ContentResponse:
    """PRD §5.2/§4: archive — status -> archived, chunks removed.

    Legal from `published` only; `draft`/`archived` -> archive both 409
    (task-00 pinned transition matrix, `app.services.content.archive_content`).
    """
    content = content_service.archive_content(
        session, content_id, actor_id=principal.user_id, pipeline=pipeline
    )
    tags = tags_for_contents(session, [content.id])[content.id]
    return _to_content_response(content, tags)


@router.get("/tags", operation_id="tags_list", response_model=list[TagWithCount])
def tags_list(
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[TagWithCount]:
    """PRD §5.2: non-deleted tags with usage counts over non-deleted content only."""
    return [
        TagWithCount(id=tag.id, name=tag.name, count=count)
        for tag, count in list_tags_with_counts(session)
    ]


@router.get("/stats", operation_id="stats_get", response_model=StatsResponse)
def stats_get(
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> StatsResponse:
    """PRD §5.2: content counts by status and by tag, excluding soft-deleted content."""
    data = content_stats(session)
    return StatsResponse(by_status=data.by_status, by_tag=data.by_tag)
