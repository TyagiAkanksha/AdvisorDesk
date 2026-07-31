"""Public content REST routes: the unauthenticated client-app read surface (PRD §5.3).

CONVENTIONS.md §4: routes contain no `try/except` —
`content_service.get_published_by_slug`'s `NotFoundError` flows to
`app.routes.errors::register_error_handlers`, which builds the PRD §9
envelope. Thin: call service -> DTO. Neither route below depends on
`require_admin` (contrast every route in `app.routes.content_routes`) —
PRD §5.3: "client routes are public", no session/cookie of any kind.

`tags_for_contents` is the only tag lookup these routes perform (task-03
brief Interfaces block, same rule `app.routes.content_routes` follows) —
the list route batches it into one call for the whole result set (no
N+1); the detail route calls it once for its single id.

Review round 1, finding M3: a slash-bearing or otherwise unroutable slug
(e.g. `.../content/a/b`) never reaches `public_content_get` at all — it
404s at the ROUTER, before any handler runs, with code `http_404` (via
`app.routes.errors::_http_exception_handler`), distinct from a routable-
but-unknown slug's `not_found` code from `get_published_by_slug`; both are
"this slug doesn't resolve to content" and task-04's error handling should
treat them the same way.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import Content
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.public import PublicContentDetail, PublicContentSummary
from app.routes.deps import get_session
from app.services import content as content_service
from app.services.tags import tags_for_contents

# No 401 (unlike `app.routes.content_routes.router`): these routes are
# unauthenticated by design. 422 is over-declared on the whole router for
# simplicity, mirroring `content_routes.py`'s same trade-off, even though
# `public_content_list` takes no request fields that could ever 422.
router = APIRouter(responses={422: {"model": ErrorEnvelope}})

# Only the by-slug route can raise `NotFoundError` — merged onto that route
# alone via FastAPI's router-then-route `responses` merge.
_DETAIL_RESPONSES: dict[int | str, dict[str, object]] = {404: {"model": ErrorEnvelope}}


def _to_summary(content: Content, tags: list[str]) -> PublicContentSummary:
    """Build a `PublicContentSummary` from a published `Content` row plus its resolved tags."""
    return PublicContentSummary(
        title=content.title,
        slug=content.slug,
        tags=tags,
        # `Content.published_at` is `Mapped[datetime | None]` in general, but
        # every row this route ever sees has `status == 'published'`
        # (`content_service.list_published_content`'s own filter) — and
        # `publish_content` always sets `status` and `published_at`
        # together (`app/services/content.py`) — so it is never `None`
        # here. Mirrors `content_routes.py::_to_content_response`'s
        # `cast(ContentStatus, content.status)`: a DB-shape runtime
        # guarantee made static once, at the one place it matters.
        published_at=cast(datetime, content.published_at),
    )


@router.get(
    "/public/content",
    operation_id="public_content_list",
    response_model=list[PublicContentSummary],
)
def public_content_list(session: Session = Depends(get_session)) -> list[PublicContentSummary]:
    """PRD §5.3: published-and-non-deleted content, newest-published first, tags included.

    Bare list, no pagination envelope — test-author-resolved,
    controller-approved (mirrors `GET /tags`'s bare `list[TagWithCount]`
    shape; task-03 test-author report ambiguity #1).
    """
    items = content_service.list_published_content(session)
    tag_names_by_id = tags_for_contents(session, [item.id for item in items])
    return [_to_summary(item, tag_names_by_id[item.id]) for item in items]


@router.get(
    "/public/content/{slug}",
    operation_id="public_content_get",
    response_model=PublicContentDetail,
    responses=_DETAIL_RESPONSES,
)
def public_content_get(slug: str, session: Session = Depends(get_session)) -> PublicContentDetail:
    """PRD §5.3: by-slug detail for a published-and-non-deleted item (404 otherwise).

    A draft/archived item's slug, a soft-deleted (still `status='published'`)
    item's slug, and a slug that never existed all 404 the same way — see
    `content_service.get_published_by_slug`'s §9 pin.
    """
    content = content_service.get_published_by_slug(session, slug)
    tags = tags_for_contents(session, [content.id])[content.id]
    return PublicContentDetail(
        title=content.title,
        slug=content.slug,
        body_md=content.body_md,
        tags=tags,
        published_at=cast(datetime, content.published_at),
    )
