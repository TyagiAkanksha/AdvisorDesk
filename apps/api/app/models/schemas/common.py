"""Shared, domain-agnostic DTO shapes reused across `app/models/schemas/*` (CONVENTIONS.md §2)."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

_ItemT = TypeVar("_ItemT")


class PaginatedResponse(BaseModel, Generic[_ItemT]):
    """A generic one-page-of-results envelope: `items`, `total`, `page`, `page_size`.

    Task-03 brief (Interfaces block): "pagination envelope field names
    chosen here; record in README" — this is that choice, made once and
    reusable by generics rather than one bespoke shape per list endpoint.
    `ContentListResponse` (`app.models.schemas.content`) is the first
    consumer; any later paginated admin/public list endpoint (e.g. PRD
    §5.3's `GET /public/content`) should specialize this generic rather
    than inventing new field names.
    """

    items: list[_ItemT]
    total: int
    page: int
    page_size: int
