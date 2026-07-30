"""Stats DTO — `GET /stats`'s wire shape (PRD §5.2)."""

from __future__ import annotations

from pydantic import BaseModel


class StatsResponse(BaseModel):
    """Content counts by status and by tag, excluding soft-deleted content (PRD §5.2)."""

    by_status: dict[str, int]
    by_tag: dict[str, int]
