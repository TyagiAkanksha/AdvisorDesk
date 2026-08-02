"""content_stats — the §5.2 dashboard aggregate.

Final-review fix (F4b, t01 M1): this module previously claimed to also back the phase-5
`count_content` MCP tool — false since task-01. `count_content` needs a COMBINED status-AND-tag
count `content_stats`'s marginal (by-status, by-tag separately) breakdowns can't answer, so it
calls `app.services.content.list_content`'s own filtered `total` directly instead (see
`app.mcp.tools_read._count_content`'s docstring for the full reasoning). This module backs only
`GET /stats` (`app.routes.content_routes.stats_get`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models import Content, ContentTag, Tag
from app.services.queries import active_select


@dataclass(frozen=True)
class StatsData:
    """Content counts by status and by tag (PRD §5.2), attribute access (`result.by_status`).

    A frozen dataclass rather than a `TypedDict`: `content_stats` computes a
    derived, internal result (not an external-boundary payload echoed
    verbatim, the one case this codebase uses `TypedDict` for), so it
    follows the attribute-access convention used everywhere else.
    """

    by_status: dict[str, int]
    by_tag: dict[str, int]


def content_stats(session: Session) -> StatsData:
    """Return content counts grouped by status and by tag, excluding soft-deleted content.

    PRD §5.2 (`GET /stats`): "counts by status, by tag, excluding
    soft-deleted content". Both breakdowns are built from an
    `active_select(Content)` subquery so a soft-deleted content row is
    excluded from either grouping — never an ad-hoc `is_deleted` filter
    (CONVENTIONS.md §3). The by-tag breakdown further restricts to
    non-deleted tags via `active_select(Tag)`, for the same reason
    `list_tags_with_counts` does.

    Args:
        session: the caller's `Session`.

    Returns:
        `StatsData` with `by_status`/`by_tag` populated only for statuses/
        tags that actually have at least one matching (non-deleted) row —
        no zero-filled entries for absent statuses/tags.
    """
    active_content = active_select(Content).subquery()
    active_tags = active_select(Tag).subquery()

    by_status_rows = (
        session.execute(
            select(active_content.c.status, func.count()).group_by(active_content.c.status)
        )
        .tuples()
        .all()
    )

    by_tag_rows = (
        session.execute(
            select(active_tags.c.name, func.count())
            .select_from(active_content)
            .join(ContentTag, ContentTag.content_id == active_content.c.id)
            .join(active_tags, active_tags.c.id == ContentTag.tag_id)
            .group_by(active_tags.c.name)
        )
        .tuples()
        .all()
    )

    return StatsData(
        by_status=dict(by_status_rows),
        by_tag=dict(by_tag_rows),
    )
