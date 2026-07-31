"""Public content DTOs — the unauthenticated `GET /public/content*` wire shapes (PRD §5.3).

Deliberately narrower than `app.models.schemas.content.ContentResponse` (the
admin-only shape): no `id`, no `status`, no `author_id`/`updated_by` — the
client links by slug, not id, and none of the admin-only fields are meant
to leave the server (task-03 brief Interfaces block).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PublicContentSummary(BaseModel):
    """One entry in `GET /public/content`'s bare list (PRD §5.3, exact field set)."""

    title: str
    slug: str
    tags: list[str]
    published_at: datetime


class PublicContentDetail(BaseModel):
    """`GET /public/content/{slug}`'s response body (PRD §5.3, exact field set).

    Same fields as `PublicContentSummary` plus `body_md` — the only
    difference between the list and detail shapes.
    """

    title: str
    slug: str
    body_md: str
    tags: list[str]
    published_at: datetime
