"""Admin weak-queries REST route — `GET /api/v1/weak-queries` (phase-9 task-19).

DESIGN §D's `weak_queries` already exists as a service (`app.services.chat.weak_queries`) and as
the MCP tool `report_weak_queries` (`app.mcp.tools_gaps`); this route is the REST/admin-dashboard
reader for the same report. Read-only, admin-session-gated, no filters beyond `days`/`limit` —
same sibling-router pattern as `app.routes.oauth_admin_routes` (router-level
`dependencies=[Depends(require_admin)]`, `responses={401: ErrorEnvelope}`, `operation_id`).

CONVENTIONS.md §4: this router contains no `try/except` — an out-of-range `days`/`limit` is
rejected by FastAPI's own `Query(..., ge=..., le=...)` validation before this function body ever
runs, and reaches the caller as the standard 422 `ErrorEnvelope`
(`app.routes.errors._validation_error_handler`) — nothing to add here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.config import Settings
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.weak_queries import (
    WeakQueriesResponse,
    WeakQueryExampleOut,
    WeakQueryGroupOut,
)
from app.routes.deps import get_session, get_settings
from app.services.chat import WeakQueryGroup, weak_queries

router = APIRouter(
    prefix="/weak-queries",
    tags=["weak-queries"],
    dependencies=[Depends(require_admin)],
    responses={401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)

_DEFAULT_DAYS = 7  # the dashboard's window ("last 7 days")
_MAX_DAYS = 90
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100  # same ceiling as `app.mcp.tools_gaps._MAX_LIMIT`


def _to_group_out(group: WeakQueryGroup) -> WeakQueryGroupOut:
    """Field-for-field mapping from the service's frozen `WeakQueryGroup` to the wire shape.

    No `from_attributes`: the dataclass field names differ from the wire shape (`normalized` ->
    `normalized_question`, `created_at` -> `asked_at`) — see `app.models.schemas.weak_queries`'s
    own module docstring.
    """
    return WeakQueryGroupOut(
        normalized_question=group.normalized,
        count=group.count,
        kinds=group.kinds,
        worst_top_similarity=group.worst_top_similarity,
        examples=[
            WeakQueryExampleOut(
                question=example.question,
                kind=example.kind,
                top_similarity=example.top_similarity,
                asked_at=example.created_at,
            )
            for example in group.examples
        ],
    )


@router.get("", operation_id="weak_queries_get", response_model=WeakQueriesResponse)
def weak_queries_get(
    days: int = Query(_DEFAULT_DAYS, ge=1, le=_MAX_DAYS),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WeakQueriesResponse:
    """Client questions the system answered badly, grouped and classified (DESIGN §D).

    No `threshold` query parameter — same reasoning as `ReportWeakQueriesArgs`' docstring
    (`app.mcp.tools_gaps`): the band boundaries only mean something against the threshold the
    answers were actually SERVED under (`settings.similarity_threshold`), not a caller's choice.
    """
    groups = weak_queries(session, days=days, limit=limit, threshold=settings.similarity_threshold)
    return WeakQueriesResponse(
        threshold=settings.similarity_threshold,
        days=days,
        count=len(groups),
        items=[_to_group_out(group) for group in groups],
    )
