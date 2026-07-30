"""Shared, domain-agnostic DTO shapes reused across `app/models/schemas/*` (CONVENTIONS.md §2)."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

_ItemT = TypeVar("_ItemT")


class ErrorDetail(BaseModel):
    """The `{"code", "message"}` object nested under `"error"` in the PRD §9 envelope."""

    code: str
    message: str


class ErrorEnvelope(BaseModel):
    """The PRD §9 error envelope: `{"error": {"code", "message"}}`.

    Review round 1, finding F2: `app.routes.errors::register_error_handlers`
    has always *rendered* this shape at runtime, but no route declared it in
    OpenAPI — every operation's committed `openapi.json` baseline instead
    carried FastAPI's own default `{detail}` validation-error schema for
    422, and no 401/404 appeared anywhere. Declaring `responses={...:
    {"model": ErrorEnvelope}}` on routes (`app.routes.content_routes`,
    `app.routes.auth_routes`) makes the baseline — and both frontends'
    `openapi-typescript` codegen consuming it — match what the server
    actually answers, and replaces that default schema outright (verified
    by `tests/test_routes_errors.py`'s baseline-schema test: it is absent
    from the generated `openapi.json` component list). Modeled as nested
    models (not a bare `dict[str, Any]`) so codegen emits real, navigable
    types for `error.code`/`error.message` rather than an opaque blob.
    """

    error: ErrorDetail


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
