"""Content DTOs — the `GET/POST/PATCH/DELETE /content*` wire shapes (PRD §5.2, task-03 brief)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.schemas.common import PaginatedResponse


class ContentCreate(BaseModel):
    """`POST /content`'s request body: a new draft (PRD §5.2, §4 slug rules)."""

    title: str
    body_md: str = ""
    tags: list[str] = Field(default_factory=list)


class ContentUpdate(BaseModel):
    """`PATCH /content/{id}`'s request body: partial update, slug never included (PRD §4.1).

    Every field is optional so a caller can send only what changed; `None`
    means "leave untouched" for `title`/`body_md`, and for `tags` means
    "leave the existing tag associations untouched" (mirrors
    `app.services.content.update_content`'s own `None`-means-unchanged
    contract for `tags`).
    """

    title: str | None = None
    body_md: str | None = None
    tags: list[str] | None = None


class ContentResponse(BaseModel):
    """`Content` as returned by every by-id and list route (PRD §5.2).

    `tags` is populated by the route layer via
    `app.services.tags.tags_for_contents` — this schema carries no ORM
    knowledge of its own (CONVENTIONS.md §2: `app.models` is a pure leaf).
    """

    id: uuid.UUID
    title: str
    slug: str
    body_md: str
    status: str
    tags: list[str]
    author_id: uuid.UUID | None
    updated_by: uuid.UUID | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ContentListResponse(PaginatedResponse[ContentResponse]):
    """`GET /content`'s list envelope: one page of `ContentResponse` items (PRD §5.2)."""
