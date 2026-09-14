"""Weak-queries DTOs — `GET /weak-queries`'s wire shape (phase-9 task-19).

Mirrors `app.mcp.tools_gaps._report_weak_queries`'s field NAMES exactly (`normalized_question`,
`worst_top_similarity`, `examples[].asked_at`) so the two surfaces agree — the one deliberate
difference is the list key: REST list envelopes use `items` (`ContentListResponse`,
`ConnectedAppsResponse`), while the MCP tool's dict key is `weak_queries` (see
`WeakQueriesResponse.items`'s own docstring).

Plain constructors, no `from_attributes`: `app.services.chat.WeakQueryGroup`/`WeakQueryExample`
are frozen dataclasses whose field names differ from the wire shape (`normalized` ->
`normalized_question`, `created_at` -> `asked_at`), so `app.routes.weak_queries_routes` builds
each model field-by-field rather than validating straight off the dataclass.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WeakQueryExampleOut(BaseModel):
    """One concrete turn behind a `WeakQueryGroupOut` (`app.services.chat.WeakQueryExample`)."""

    question: str
    kind: str  # one of `app.services.chat.WEAK_QUERY_KINDS`
    top_similarity: float | None
    asked_at: datetime  # `WeakQueryExample.created_at`


class WeakQueryGroupOut(BaseModel):
    """One normalised question and every weak turn that asked it (`WeakQueryGroup`)."""

    normalized_question: str  # `WeakQueryGroup.normalized`
    count: int
    kinds: list[str]  # `WEAK_QUERY_KINDS` order, as the service returns them
    worst_top_similarity: float | None
    examples: list[WeakQueryExampleOut]  # at most 3, newest first (service contract)


class WeakQueriesResponse(BaseModel):
    """`GET /weak-queries`'s top-level wire shape (phase-9 DESIGN §D).

    `items` (not the MCP tool's `weak_queries` key): REST list envelopes use `items`
    (`ContentListResponse`, `ConnectedAppsResponse`) — the MCP tool `report_weak_queries` answers
    the same data under the key `weak_queries` instead; this schema's docstring is the one place
    that difference is spelled out.
    """

    threshold: float  # `settings.similarity_threshold` the bands were judged against
    days: int  # the window actually applied
    count: int  # `len(items)` — same semantic as the MCP tool's `count`
    items: list[WeakQueryGroupOut]
