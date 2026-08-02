"""Read tools: `search_content` / `count_content` — wrap the content services (PRD §6).

Neither tool re-implements filtering: both call straight into
`app.services.content.list_content`, which already builds the combined
status+tag(+title-substring) query over `active_select` (soft-deleted rows
excluded, §6 footer) — `count_content` just discards `list_content`'s
`items` and keeps its `total`, since the marginal by-status/by-tag counts
`app.services.stats.content_stats` returns can't answer a *combined*
status-AND-tag count on their own (see `_count_content`'s docstring for the
full reasoning). This is the registration pattern task-02's write tools
follow: one `ToolSpec` per tool, each pairing a Pydantic args model with a
`session`+`actor_id`-taking handler that calls straight into
`app.services.*`.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.mcp.tool_spec import ToolSpec
from app.services import content as content_service
from app.services.tags import normalize_tag_name, tags_for_contents

# PRD §6: `search_content(q?, status?, tag?, limit=10)`.
_DEFAULT_SEARCH_LIMIT = 10
# Fix round 1, finding I4: `limit` had no domain bounds — `limit=-1` escaped Pydantic validation
# and crashed as an unhandled `sqlalchemy.exc.DataError` (`LIMIT must not be negative`) rather
# than a `ToolInputError`; `limit=0` silently returned an empty page; an unbounded upper value let
# a caller request an unbounded result set into its own (or the model's) context window. 100 is a
# disclosed, deliberately generous cap — ten times the default — chosen to comfortably cover any
# legitimate `search_content` call while still bounding worst-case response size; a caller that
# needs more should paginate via repeated calls rather than one unbounded one.
_MAX_SEARCH_LIMIT = 100


class SearchContentArgs(BaseModel):
    """`search_content`'s arguments (PRD §6): metadata search — title/tag/status, not vector."""

    # Fix round 1, finding I5: `extra="forbid"` so a misspelled/unknown argument (e.g. `limitt`,
    # `query`) raises `ToolInputError` naming the field, instead of Pydantic v2's default
    # `extra="ignore"` silently dropping it — for a human REST caller that's a shrug, but for an
    # LLM caller (the entire point of this tool) a silently-ignored filter is a wrong-answer
    # generator with no signal to self-correct on. Also emits `additionalProperties: false` into
    # the exported `mcp-tools.json` schema, so the model's own tool definition tells it the truth.
    model_config = ConfigDict(extra="forbid")

    q: str | None = None
    status: str | None = None
    tag: str | None = None
    limit: int = Field(default=_DEFAULT_SEARCH_LIMIT, ge=1, le=_MAX_SEARCH_LIMIT)


def _search_content(
    args: SearchContentArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{items:[{id,title,slug,status,tags}], count}` (PRD §6) via `content_service.list_content`.

    `limit` bounds `list_content`'s `page_size` directly (`page=1`) — task-01 brief Step 1's
    ambiguity note: whether `count` reflects the truncated item count or the untruncated total
    match count is left open by the brief/PRD §6, so `count` here is `list_content`'s own
    `total` (the untruncated match count) — the value `list_content` already computes for
    exactly this purpose, needing no second query.

    Checkpoint fix (finding L-2): `args.tag` is run through `normalize_tag_name` (the exact
    normalizer `get_or_create_tags`/creation already applies) before reaching `list_content`,
    which itself does an exact `Tag.name` match — without this, a conversational tag name from
    the model (e.g. `"Tax Planning"`, or `"tax planning"`) never matches the stored
    lowercase-hyphenated form (`tax-planning`, PRD §4.1) and silently returns zero rows instead
    of erroring, the confidently-wrong-answer failure mode this fix closes.
    """
    items, total = content_service.list_content(
        session,
        status=args.status,
        tag=normalize_tag_name(args.tag) if args.tag is not None else None,
        q=args.q,
        page=1,
        page_size=args.limit,
    )
    tags_by_id = tags_for_contents(session, [item.id for item in items])
    return {
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "slug": item.slug,
                "status": item.status,
                "tags": tags_by_id[item.id],
            }
            for item in items
        ],
        "count": total,
    }


class CountContentArgs(BaseModel):
    """`count_content`'s arguments (PRD §6): `status`/`tag`, both optional."""

    # Fix round 1, finding I5 (see `SearchContentArgs.model_config` for the full reasoning).
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    tag: str | None = None


def _count_content(
    args: CountContentArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{count}` (PRD §6) via `content_service.list_content`'s own filtered `total`.

    `app.services.stats.content_stats` returns *marginal* counts (by status, by tag,
    separately) — it has no way to answer "how many rows match status=X AND tag=Y together",
    which this tool's own pinned test (`status`+`tag` given at once) requires. `list_content`
    already builds that combined query (`active_select` + the `status`/`tag` `.where()`/
    `.join()` clauses) to compute its own `total`; calling it with `page_size=1` (the smallest
    legal page, since only `total` is used) reuses that filtering rather than re-implementing
    a second status+tag query here.

    Checkpoint fix (finding L-2): `args.tag` is normalized the same way `_search_content` now
    does — see that docstring for the full reasoning.
    """
    _, total = content_service.list_content(
        session,
        status=args.status,
        tag=normalize_tag_name(args.tag) if args.tag is not None else None,
        page=1,
        page_size=1,
    )
    return {"count": total}


READ_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_content",
        description=(
            "Metadata search over CMS content (title/tag/status — not vector search). "
            "Returns matching items and the total match count."
        ),
        args_model=SearchContentArgs,
        handler=_search_content,
    ),
    ToolSpec(
        name="count_content",
        description="Count non-deleted content, optionally filtered by status and/or tag.",
        args_model=CountContentArgs,
        handler=_count_content,
    ),
)
