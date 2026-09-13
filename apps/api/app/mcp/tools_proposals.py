"""The four proposal MCP tools: `propose_content_fix`/`list_proposals`/`accept_proposal`/
`reject_proposal` (phase-9 DESIGN §D, task-16).

Same thin-wrapper pattern as `tools_read.py`/`tools_write.py`/`tools_gaps.py`: one `ToolSpec`
pairing a Pydantic args model with a `(args, *, session, actor_id) -> dict` handler that calls
straight into `app.services.proposals` — no business logic here. `accept_proposal`'s handler in
particular has NO `try/except`: the gate's `ConflictError`/`NotFoundError` message must reach the
caller verbatim, for both the PRD §9 HTTP envelope and the agent loop's self-correction feedback.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.mcp.tool_spec import ToolSpec, pipeline_from_session
from app.models import Content, EvalRun
from app.services.errors import ToolInputError
from app.services.eval_runs import compare_runs
from app.services.proposals import (
    accept_proposal,
    kind_for_cause,
    list_proposals,
    propose_content_fix,
    reject_proposal,
)

# ---------------------------------------------------------------------------
# propose_content_fix
# ---------------------------------------------------------------------------


class ProposeContentFixArgs(BaseModel):
    """`propose_content_fix`'s arguments (phase-9 DESIGN §D)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    kind: Literal["new_article", "expand_article", "retune"] | None = None
    failure_cause: (
        Literal[
            "retrieval_miss",
            "corpus_gap",
            "threshold_refusal",
            "generation_unfaithful",
            "judge_disagreement",
        ]
        | None
    ) = None
    evidence: list[dict[str, object]] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    target_content_id: uuid.UUID | None = None

    @field_validator("title", "rationale")
    @classmethod
    def _not_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty or whitespace-only")
        return value

    @model_validator(mode="after")
    def _exactly_one_kind_source(self) -> ProposeContentFixArgs:
        """Exactly one of `kind` / `failure_cause` — neither (we will not guess) nor both (which
        one wins would be invisible). `ValueError` here surfaces as `ToolInputError`."""
        if (self.kind is None) == (self.failure_cause is None):
            raise ValueError(
                "Exactly one of kind or failure_cause must be given (not neither, not both)."
            )
        return self


def _propose_content_fix(
    args: ProposeContentFixArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{id, kind, title, status, draft_content_id, draft_slug, eval_run_before_id}`.

    Resolves `kind` via `kind_for_cause(args.failure_cause)` when the caller passed a cause
    instead of a kind; `kind_for_cause` only raises for `judge_disagreement` (the model's
    `Literal` already restricts `failure_cause` to the five known causes, and the other four all
    map to a real kind), so the fixed message below is accurate whenever this branch fires.
    """
    kind: str
    if args.kind is not None:
        kind = args.kind
    else:
        assert args.failure_cause is not None  # the model_validator above guarantees this
        try:
            kind = kind_for_cause(args.failure_cause)
        except ValueError as exc:
            raise ToolInputError(
                "failure_cause: judge_disagreement is a judge-calibration problem, not a "
                "content gap — no proposal kind fixes it."
            ) from exc

    proposal = propose_content_fix(
        session,
        kind=kind,
        title=args.title,
        rationale=args.rationale,
        evidence=args.evidence,
        actor_id=actor_id,
        target_content_id=args.target_content_id,
    )

    draft = session.get(Content, proposal.draft_content_id)
    assert draft is not None  # propose_content_fix always creates a draft (see its docstring)

    return {
        "id": str(proposal.id),
        "kind": proposal.kind,
        "title": proposal.title,
        "status": proposal.status,
        "draft_content_id": str(proposal.draft_content_id),
        "draft_slug": draft.slug,
        "eval_run_before_id": (
            str(proposal.eval_run_before_id) if proposal.eval_run_before_id is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# list_proposals
# ---------------------------------------------------------------------------


class ListProposalsArgs(BaseModel):
    """`list_proposals`'s arguments. `limit` defaults to 20, not the service's own 50: a tool
    result lands in a model's context window, so the MCP default mirrors
    `tools_gaps._DEFAULT_LIMIT`/`_MAX_LIMIT` (20/100) rather than the service default. Deliberate,
    not a drift."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["proposed", "accepted", "rejected"] | None = None
    limit: int = Field(default=20, ge=1, le=100)


def _list_proposals(
    args: ListProposalsArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{count, proposals:[{id, kind, title, status, draft_content_id, target_content_id,
    eval_run_before_id, eval_run_after_id, created_at}]}`, newest first."""
    proposals = list_proposals(session, status=args.status, limit=args.limit)
    return {
        "count": len(proposals),
        "proposals": [
            {
                "id": str(proposal.id),
                "kind": proposal.kind,
                "title": proposal.title,
                "status": proposal.status,
                "draft_content_id": (
                    str(proposal.draft_content_id)
                    if proposal.draft_content_id is not None
                    else None
                ),
                "target_content_id": (
                    str(proposal.target_content_id)
                    if proposal.target_content_id is not None
                    else None
                ),
                "eval_run_before_id": (
                    str(proposal.eval_run_before_id)
                    if proposal.eval_run_before_id is not None
                    else None
                ),
                "eval_run_after_id": (
                    str(proposal.eval_run_after_id)
                    if proposal.eval_run_after_id is not None
                    else None
                ),
                "created_at": proposal.created_at.isoformat(),
            }
            for proposal in proposals
        ],
    }


# ---------------------------------------------------------------------------
# accept_proposal
# ---------------------------------------------------------------------------


class AcceptProposalArgs(BaseModel):
    """`accept_proposal`'s arguments (phase-9 DESIGN §D)."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: uuid.UUID
    eval_run_after_id: uuid.UUID


def _accept_proposal(
    args: AcceptProposalArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{id, status, eval_run_before_id, eval_run_after_id, pct_before, pct_after, improvements,
    regressions}` (the last two are counts).

    No `try/except`: a gate refusal's `ConflictError`/`NotFoundError` propagates verbatim (the
    §9 409 envelope over HTTP, the agent loop's self-correction feedback) — see the module
    docstring. `improvements`/`regressions` are not on `AcceptanceCheck` (it carries only the
    regressed question names, for the refusal message), so a successful accept re-derives the
    counts here via `compare_runs`, the same function the gate itself used.
    """
    proposal = accept_proposal(session, args.proposal_id, eval_run_after_id=args.eval_run_after_id)

    before_id = proposal.eval_run_before_id
    after_id = proposal.eval_run_after_id
    assert before_id is not None and after_id is not None  # accept_proposal just stamped both

    before = session.get(EvalRun, before_id)
    after = session.get(EvalRun, after_id)
    assert before is not None and after is not None  # accept_proposal's gates already proved this

    diff = compare_runs(session, before_id, after_id)

    return {
        "id": str(proposal.id),
        "status": proposal.status,
        "eval_run_before_id": str(before_id),
        "eval_run_after_id": str(after_id),
        "pct_before": before.pct_fully_supported,
        "pct_after": after.pct_fully_supported,
        "improvements": len(diff.improvements),
        "regressions": len(diff.regressions),
    }


# ---------------------------------------------------------------------------
# reject_proposal
# ---------------------------------------------------------------------------


class RejectProposalArgs(BaseModel):
    """`reject_proposal`'s arguments (phase-9 DESIGN §D)."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: uuid.UUID
    reason: str = Field(min_length=1)


def _reject_proposal(
    args: RejectProposalArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{id, status, reason, draft_content_id, draft_status_after}` (Ruling B: reads the
    `ChunkPipeline` `call_tool` stashed on `session.info` back via `pipeline_from_session`)."""
    proposal = reject_proposal(
        session,
        args.proposal_id,
        reason=args.reason,
        actor_id=actor_id,
        pipeline=pipeline_from_session(session),
    )
    # `evidence` is plain `dict[str, object]` JSONB — `reject_proposal` always writes this exact
    # shape (its own docstring), so this narrows a known internal invariant, mirroring
    # `app.mcp.tool_spec.pipeline_from_session`'s own use of `cast` for the same reason.
    rejection = cast(dict[str, object], proposal.evidence["rejection"])
    return {
        "id": str(proposal.id),
        "status": proposal.status,
        "reason": rejection["reason"],
        "draft_content_id": (
            str(proposal.draft_content_id) if proposal.draft_content_id is not None else None
        ),
        "draft_status_after": rejection["draft_status_after"],
    }


# ---------------------------------------------------------------------------
# Registration — appended LAST in `app.mcp.runtime._ALL_TOOLS` so the `mcp-tools.json` diff
# stays purely additive (entries are emitted in `_ALL_TOOLS` order).
# ---------------------------------------------------------------------------

PROPOSAL_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="propose_content_fix",
        description=(
            "Record a proposed content fix for detected weak queries and create its draft. Pass "
            "either kind (new_article/expand_article/retune) or failure_cause (from the eval "
            "failure taxonomy) and the weak-query rows as evidence. Creates a DRAFT only — "
            "publishing is a separate, explicitly requested step."
        ),
        args_model=ProposeContentFixArgs,
        handler=_propose_content_fix,
    ),
    ToolSpec(
        name="list_proposals",
        description=(
            "List content-fix proposals, newest first, optionally filtered by status "
            "(proposed/accepted/rejected)."
        ),
        args_model=ListProposalsArgs,
        handler=_list_proposals,
    ),
    ToolSpec(
        name="accept_proposal",
        description=(
            "Accept a proposal — allowed ONLY when the eval data supports it: a baseline run "
            "and the eval_run_after_id run must both exist, the after-run must have measured a "
            "changed corpus, pct_fully_supported must not have dropped, and the run must show "
            "no regressions. When eval_run_after_id belongs to a run family (multiple runs "
            "sharing a label and corpus, e.g. from --runs N), every run in that family must "
            "individually qualify (same corpus, newer than the baseline, full coverage), and "
            "pct_fully_supported and regressions are judged by majority across the family — a "
            "single flaky run can neither force nor block acceptance, but a regression that "
            "reproduces in a majority of N runs still refuses. Otherwise this fails with a "
            "conflict explaining which check said no."
        ),
        args_model=AcceptProposalArgs,
        handler=_accept_proposal,
    ),
    ToolSpec(
        name="reject_proposal",
        description=(
            "Reject a proposal with a reason; if its draft was published, it is archived so "
            "the change leaves the corpus."
        ),
        args_model=RejectProposalArgs,
        handler=_reject_proposal,
    ),
)
