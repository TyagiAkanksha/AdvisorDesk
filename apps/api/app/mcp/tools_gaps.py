"""Read tool: `report_content_gaps` — the ninth MCP tool (PRD §6, §9.1; phase-7 task-01).

Wraps `app.services.chat.content_gaps` exactly the way `tools_read.py`'s `search_content`/
`count_content` wrap `app.services.content`: one `ToolSpec` pairing a Pydantic args model with
a thin `(args, *, session, actor_id) -> dict` handler that calls straight into the service —
no business logic here, the §6 pairing/window/ordering semantics all live in `content_gaps`
itself, once.

CONTROLLER RULING D (registration seam): collected into `app.mcp.runtime._ALL_TOOLS` alongside
`READ_TOOLS`/`WRITE_TOOLS`, not registered in `app.mcp.server` (that line in the task-01 brief
predates this seam — see `app.mcp.runtime`'s own module docstring).

CONTROLLER RULING G (tool `count` semantic): `count` below is `len(gaps)` — the returned page
size after `limit` is applied, not a separate total-before-limit query. `content_gaps` has no
such "total before limit" concept to report (it stops building rows once `limit` is reached,
mirroring a `LIMIT`-bounded SQL query rather than a paginated listing with a distinct total).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.mcp.tool_spec import ToolSpec
from app.services.chat import content_gaps

# PRD §6: `report_content_gaps(days=30, limit=20)`.
_DEFAULT_DAYS = 30
_DEFAULT_LIMIT = 20
# Same domain-bounding rationale as `tools_read.SearchContentArgs.limit` (finding I4 there):
# `limit`/`days` both need a floor so a negative/zero value fails fast as a `ToolInputError`
# instead of reaching `content_gaps`' `datetime.now(UTC) - timedelta(days=...)`/SQL `LIMIT`
# unchecked. `_MAX_LIMIT` mirrors that same tool's disclosed generous-but-bounded cap, so one
# unbounded call can't pull an unbounded result set into the caller's context window.
_MAX_LIMIT = 100


class ReportContentGapsArgs(BaseModel):
    """`report_content_gaps`'s arguments (PRD §6): `days`/`limit`, both optional."""

    # Same reasoning as `tools_read.SearchContentArgs.model_config` (finding I5): an unknown
    # argument fails loudly as a named `ToolInputError` rather than being silently ignored.
    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=_DEFAULT_DAYS, ge=1)
    limit: int = Field(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)


def _report_content_gaps(
    args: ReportContentGapsArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{count, gaps:[{question, asked_at, session_id}]}` (PRD §6) via `content_gaps`.

    `asked_at`/`session_id` are returned as ISO-8601 string / `str` respectively — the HTTP
    transport (`app.mcp.server._execute_tool_call`) `json.dumps`s this dict directly, which
    cannot serialize a raw `datetime`/`uuid.UUID` on its own (same precedent as
    `tools_write._publish`'s `published_at`).
    """
    gaps = content_gaps(session, days=args.days, limit=args.limit)
    return {
        "count": len(gaps),
        "gaps": [
            {
                "question": gap.question,
                "asked_at": gap.asked_at.isoformat(),
                "session_id": str(gap.session_id),
            }
            for gap in gaps
        ],
    }


GAPS_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="report_content_gaps",
        description=(
            "Report client questions the content didn't cover: user messages whose next "
            "assistant reply found no matching content (retrieval_found=false), asked within "
            "the last `days` days, newest first."
        ),
        args_model=ReportContentGapsArgs,
        handler=_report_content_gaps,
    ),
)
