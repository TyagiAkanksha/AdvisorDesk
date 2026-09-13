"""Read tools: `report_content_gaps` + `report_weak_queries` (PRD §6, §9.1; phase-7 task-01,
phase-9 task-15).

Wraps `app.services.chat.content_gaps`/`weak_queries` exactly the way `tools_read.py`'s
`search_content`/`count_content` wrap `app.services.content`: one `ToolSpec` pairing a Pydantic
args model with a thin `(args, *, session, actor_id) -> dict` handler that calls straight into
the service — no business logic here, the §6 pairing/window/ordering/classification semantics
all live in `app.services.chat` itself, once.

CONTROLLER RULING D (registration seam): collected into `app.mcp.runtime._ALL_TOOLS` alongside
`READ_TOOLS`/`WRITE_TOOLS`, not registered in `app.mcp.server` (that line in the task-01 brief
predates this seam — see `app.mcp.runtime`'s own module docstring).

CONTROLLER RULING G (tool `count` semantic): `count` below is `len(gaps)` — the returned page
size after `limit` is applied, not a separate total-before-limit query. `content_gaps` has no
such "total before limit" concept to report (it stops building rows once `limit` is reached,
mirroring a `LIMIT`-bounded SQL query rather than a paginated listing with a distinct total).
Phase-9 task 15's `report_weak_queries` mirrors this: `count` is `len(groups)`, the number of
GROUPS returned after `limit`, not a row count.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import Settings
from app.mcp.tool_spec import ToolSpec
from app.services.chat import content_gaps, weak_queries

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


class ReportWeakQueriesArgs(BaseModel):
    """`report_weak_queries`'s arguments (phase-9 DESIGN §D): `days`/`limit`, both optional.

    Deliberately NO `threshold` argument: the band boundaries are only meaningful against the
    threshold the answers were actually SERVED under, which is deployment config
    (`Settings.similarity_threshold`), not a caller's choice. Exposing it would let the agent
    (or a curious connector) re-score history against a threshold that never ran.
    """

    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=_DEFAULT_DAYS, ge=1)
    limit: int = Field(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)


def _report_weak_queries(
    args: ReportWeakQueriesArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{threshold, count, weak_queries:[{normalized_question, count, kinds,
    worst_top_similarity, examples:[{question, kind, top_similarity, asked_at}]}]}`.

    `Settings()` is constructed here, per call: this is the only layer in the tool path that may
    own config, and a handler cannot read `app.state` (the in-process agent-loop caller has no
    request, and `call_tool`'s `spec.handler(args, *, session, actor_id)` shape is pinned by
    `tests/test_mcp_runtime_guards.py` and cannot grow a `settings` argument). `Settings()`
    constructs with zero env (CONVENTIONS.md §5), so this is always safe, and reading it fresh
    per call mirrors `app.mcp.server`'s own live-settings philosophy.

    `asked_at` is an ISO-8601 string and similarities are plain floats — the HTTP transport
    `json.dumps`es this dict directly (same precedent as `_report_content_gaps`).
    """
    threshold = Settings().similarity_threshold
    groups = weak_queries(session, days=args.days, limit=args.limit, threshold=threshold)
    return {
        "threshold": threshold,
        "count": len(groups),
        "weak_queries": [
            {
                "normalized_question": group.normalized,
                "count": group.count,
                "kinds": group.kinds,
                "worst_top_similarity": group.worst_top_similarity,
                "examples": [
                    {
                        "question": example.question,
                        "kind": example.kind,
                        "top_similarity": example.top_similarity,
                        "asked_at": example.created_at.isoformat(),
                    }
                    for example in group.examples
                ],
            }
            for group in groups
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
    ToolSpec(
        name="report_weak_queries",
        description=(
            "Report client questions the system answered BADLY, grouped and classified: "
            "negative_feedback (a client pressed thumbs-down), refused (nothing in the corpus "
            "was close), near_miss (a source was just under the retrieval threshold, or "
            "retrieval succeeded and the answer still declined — either way the corpus nearly "
            "had it), low_confidence (answered, but only just above the threshold). Newest "
            "`days` days, most-asked first. Use this to decide what content to write or expand "
            "next."
        ),
        args_model=ReportWeakQueriesArgs,
        handler=_report_weak_queries,
    ),
)
