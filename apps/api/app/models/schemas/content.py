"""Content DTOs — the `GET/POST/PATCH/DELETE /content*` wire shapes (PRD §5.2, task-03 brief)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.schemas.common import PaginatedResponse

ContentStatus = Literal["draft", "published", "archived"]
"""The three `Content.status` values (mirrors the DB `status_valid`
`CheckConstraint` on `app.models.content.Content`, PRD §4) — defined once
here, in the schemas layer (`app.models` exports no Python-level constant
for these; the DB constraint is the only other place they're spelled out),
so `ContentResponse.status` and the `?status=` list filter
(`app.routes.content_routes.content_list`) share one union instead of each
typing `str` and letting FastAPI/pydantic emit an unconstrained `string`
schema for both the response field and the query param (review round 1,
finding F3). `openapi-typescript` codegen turns this into a real
`"draft" | "published" | "archived"` union — no separate TS-style enum."""


class ContentCreate(BaseModel):
    """`POST /content`'s request body: a new draft (PRD §5.2, §4 slug rules).

    `title` is `min_length=1` (review round 1, finding F4): an empty title
    now 422s instead of creating a degenerate row. Plain length check only —
    a whitespace-only title (`"   "`) still passes; strip-then-check is
    ledgered separately alongside task-02's slug fallback, not this round.
    """

    title: str = Field(min_length=1)
    body_md: str = ""
    tags: list[str] = Field(default_factory=list)


class ContentUpdate(BaseModel):
    """`PATCH /content/{id}`'s request body: partial update, slug never included (PRD §4.1).

    Every field is optional so a caller can send only what changed; `None`
    means "leave untouched" for `title`/`body_md`, and for `tags` means
    "leave the existing tag associations untouched" (mirrors
    `app.services.content.update_content`'s own `None`-means-unchanged
    contract for `tags`).

    `title`, if given, is `min_length=1` (review round 1, finding F4, same
    scope note as `ContentCreate.title`) — `None` (omitted) still means
    "leave untouched" and is unaffected by the constraint.
    """

    title: str | None = Field(default=None, min_length=1)
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
    status: ContentStatus
    tags: list[str]
    author_id: uuid.UUID | None
    updated_by: uuid.UUID | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ContentListResponse(PaginatedResponse[ContentResponse]):
    """`GET /content`'s list envelope: one page of `ContentResponse` items (PRD §5.2)."""
