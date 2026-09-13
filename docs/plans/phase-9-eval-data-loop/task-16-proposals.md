---
id: p9-t16
phase: phase-9-eval-data-loop
depends_on: [p9-t15]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 16 — The proposal record: a fix the data has to approve

## Goal

The loop closes. `app/services/proposals.py` turns a weak-query report into a `ContentProposal`
row with a real draft attached (`propose_content_fix`), lists proposals (`list_proposals`), and —
the point of the whole phase — **refuses to accept a fix the eval data does not support**:
`accept_proposal` raises `ConflictError` unless a before-run and an after-run both exist, the
after-run measured a *different corpus*, `pct_fully_supported` did not drop, and
`compare_runs(...).regressions` is empty. `reject_proposal` records why and archives the published
draft, so the rehearsed bad fix (DESIGN §D6 beat 4's variant — "the harness said no, so the system
rejected its own fix") is a real code path, not a slide.

Four MCP tools (`propose_content_fix`, `list_proposals`, `accept_proposal`, `reject_proposal`) put
that sequence in the agent's hands: **propose → publish the draft → re-run the harness → accept**.
"Validated before acceptance" is a *data precondition*, never a synchronous harness run — a run
takes minutes and no MCP step budget allows it (DESIGN §D).

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Part D" (the whole section: `content_proposals`'
  columns, the four tools, the four acceptance gates, "the best demo beat available"), D6 beat 4,
  §"Execution order" step 7, §"Verification" (the Loop bullet).
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` §"Global Constraints" + the plan-time ruling
  "`content_proposals` is created in 01 and left inert until 16".
- `docs/plans/phase-9-eval-data-loop/task-15-weak-queries.md` §Interfaces — `WeakQueryGroup`'s
  fields and the `report_weak_queries` payload (`normalized_question`/`kinds`/
  `worst_top_similarity`/`examples`) this task's `evidence` blob snapshots, and its
  shared-constants ruling (task 15 owns `app/services/eval_policy.py` and the taxonomy re-export;
  this task only imports from the leaf).
- `apps/api/app/models/eval.py:129-167` — `ContentProposal`: the two `CheckConstraint`s (`kind`,
  `status`), `evidence` as a **non-nullable JSONB dict**, the nullable `target_content_id`/
  `draft_content_id`/`eval_run_before_id`/`eval_run_after_id`/`created_by` FKs, `UpdatedAtMixin`.
  Also 51-91 (`EvalRun.corpus_digest`, `pct_fully_supported`, `kind`).
- `apps/api/app/services/eval_runs.py` — `latest_runs` (254-278), `compare_runs` (281-349, note it
  raises `ConflictError` across differing `kind`s and `NotFoundError` for a missing id), `RunDiff`
  (94-105).
- `apps/api/app/services/content.py` — `create_draft` (113-154: keyword-only `title`/`body_md`/
  `tags`/`actor_id`, flushes, server-generated slug), `get_content` (155-179), **`archive_content`
  (542-575): legal from `published` ONLY — a `draft` or already-`archived` row raises
  `ConflictError`**, and it takes a required `pipeline: ChunkPipeline`.
- `apps/api/app/services/errors.py:36-45` — `NotFoundError` (404) / `ConflictError` (409);
  `:175-186` — `ToolInputError` (422).
- `apps/api/app/services/lifecycle.py:23-77` — `ChunkPipeline`/`NoopChunkPipeline`.
- `apps/api/app/services/eval_policy.py` (created by task 15) — `PROPOSAL_KIND_BY_CAUSE`,
  `PROPOSAL_KINDS`, `PROPOSAL_STATUSES`: this task's only source for all three. Read it; do not
  edit it.
- `apps/api/app/mcp/tools_write.py:1-51` (module docstring: the pipeline-threading judgment call),
  `:53-80` (`_pipeline_from_session` — this task moves it), `:88-124` (`CreateDraftArgs`/
  `_create_draft`: `extra="forbid"`, `json_schema_extra={"default": []}`, the
  `field_validator` title rule), `:251-300` (`WRITE_TOOLS`' `ToolSpec` entries).
- `apps/api/app/mcp/tool_spec.py` — the whole file (`SESSION_INFO_PIPELINE_KEY`'s docstring argues
  exactly where the reader belongs; `ToolSpec`).
- `apps/api/app/mcp/runtime.py:42-54` — the imports + `_ALL_TOOLS`/`_REGISTRY` (this task adds one
  module to the tuple).
- `apps/api/app/agent/loop.py:53-89` — `SYSTEM_PROMPT` and its numbered intent comment (task 15
  added bullet 6); the publish rule at lines 82-84 that this task must NOT weaken.
- `apps/api/tests/test_eval_models.py:111-126` — the already-pinned `ContentProposal` default
  `status` + `kind` CHECK, and the `evidence={"weak_queries": []}` envelope shape this task adopts.
- `apps/api/tests/test_eval_runs_service.py` — its `FakeRow`/`FakeReport`/`_record` helpers (the
  shape this task's tests copy to build real `eval_runs` rows without the harness).
- `apps/api/tests/test_mcp_write_tools_guards.py:50-78` — the `RuntimeError`-naming-`ChunkPipeline`
  pin that must stay green when the pipeline reader moves.

## Files

**Create**
- `apps/api/app/services/proposals.py`
- `apps/api/app/mcp/tools_proposals.py`
- `apps/api/tests/test_proposals.py`
- `apps/api/tests/test_proposal_tools.py`

**Do NOT modify** — `apps/api/app/services/eval_policy.py` and `apps/api/app/eval/taxonomy.py`.
Task 15 already moved `PROPOSAL_KIND_BY_CAUSE`/`PROPOSAL_KINDS`/`PROPOSAL_STATUSES` into
`eval_policy` and wired the taxonomy's re-export (controller ruling, 2026-09-12). This task **only
imports** from `app.services.eval_policy`; if either file still needs editing when you get here,
task 15 is incomplete — stop and report instead of finishing its move.

**Modify**
- `apps/api/app/mcp/tool_spec.py` (add `pipeline_from_session`)
- `apps/api/app/mcp/tools_write.py` (use it; drop the local copy + two now-unused imports)
- `apps/api/app/mcp/runtime.py` (register `PROPOSAL_TOOLS`)
- `apps/api/app/agent/loop.py` (one awareness paragraph in `SYSTEM_PROMPT`)

**Regenerate (same commit)**
- `apps/api/mcp-tools.json` — `cd apps/api && uv run python scripts/export_mcp_tools.py`

**Pre-authorized pre-existing-test updates (controller)** — registry-inventory pins again, the
only exception to the stop rule for this task. Task 15 took the count 9 → 10; this task takes it
**10 → 14**:

| File | Change |
|---|---|
| `apps/api/tests/test_mcp_bearer_auth.py` | add `"propose_content_fix"`, `"list_proposals"`, `"accept_proposal"`, `"reject_proposal"` to `_EXPECTED_TOOL_NAMES` + `+ phase-9 task-16 (the four proposal tools)` in the comment above it |
| `apps/api/tests/test_oauth_e2e_flow.py` | the same four names + the same comment extension |
| `apps/api/tests/test_agent_loop_step_bound.py` | `== 10` → `== 14`; comment `(14 registered tools — phase-9 task-16 added the four proposal tools)` |

## Interfaces

### Ruling A — the cause→kind mapping is imported, not moved (task 15 already moved it)

`app.services.proposals` needs `PROPOSAL_KIND_BY_CAUSE`, and the import-linter contract
"app.services imports only app.models and app.config" lists `app.eval` in `forbidden_modules`, so
`from app.eval.taxonomy import PROPOSAL_KIND_BY_CAUSE` is a hard gate failure. **Task 15 already
resolved this** (controller ruling, 2026-09-12): the mapping, `PROPOSAL_KINDS` and
`PROPOSAL_STATUSES` all live in `apps/api/app/services/eval_policy.py`, and `app.eval.taxonomy`
imports + re-exports the mapping via its `__all__`.

So this task simply does:

```python
from app.services.eval_policy import PROPOSAL_KIND_BY_CAUSE, PROPOSAL_KINDS, PROPOSAL_STATUSES
```

and **touches neither `eval_policy.py` nor `taxonomy.py`**. Two consequences for the implementer:

- `kind_for_cause` (below) reads the mapping straight from the leaf; it must NOT re-type the
  five cause names or the three kinds anywhere.
- The drift pin already exists and is not this task's to add:
  `tests/test_failure_taxonomy.py:104` asserts `set(PROPOSAL_KIND_BY_CAUSE) == set(FAILURE_CAUSES)`
  across the new layer boundary, and task 15's `tests/test_weak_queries.py` asserts the identity of
  the re-exported object. Both must still pass, unedited.

### Ruling B — where the MCP pipeline reader lives

`reject_proposal` archives the proposal's published draft, and `archive_content` takes a required
`pipeline: ChunkPipeline` — so `tools_proposals.py` needs the same `session.info` pipeline as
`tools_write.py`'s handlers. Three options: import the private
`app.mcp.tools_write._pipeline_from_session` (a private name reached across modules), duplicate it,
or move it. **Decision: move it to `app/mcp/tool_spec.py` as a public `pipeline_from_session`.**
That module already owns `SESSION_INFO_PIPELINE_KEY` and its docstring already argues this exact
placement ("both `app.mcp.runtime` (which sets it) and `app.mcp.tools_write` (which reads it)
already import this module… this module imports nothing from `app.mcp` itself, so the placement is
non-circular"). The reader belongs with the key it reads.

Exact edits:

1. `app/mcp/tool_spec.py`: add `from app.services.lifecycle import ChunkPipeline`, `from typing
   import Any, cast`, `from sqlalchemy.orm import Session`, and move the function body **verbatim**
   from `tools_write.py:53-80`, renamed `pipeline_from_session`, with the message's module prefix
   changed from `app.mcp.tools_write:` to `app.mcp.tool_spec:` and the phrase "this write-tool
   handler" generalised to "this tool handler". **Keep the word `ChunkPipeline` in the message** —
   `tests/test_mcp_write_tools_guards.py` matches on it.
2. `app/mcp/tools_write.py`: delete the local def; `from app.mcp.tool_spec import
   SESSION_INFO_PIPELINE_KEY, ToolSpec` becomes `from app.mcp.tool_spec import ToolSpec,
   pipeline_from_session` (drop `SESSION_INFO_PIPELINE_KEY` only if nothing else there uses it —
   check); drop `cast` from the `typing` import and drop
   `from app.services.lifecycle import ChunkPipeline` if they become unused (ruff `F401` will say);
   update the four call sites (`:162`, `:191`, `:204`, `:216`) and the module docstring's line 22
   reference.
3. `app.mcp` → `app.services.lifecycle` is already a legal import direction (`app.mcp`'s contract
   forbids only `app.routes`/`app.agent`/`app.db`), and `tools_write.py` imports it today — verify
   with `lint-imports`, do not edit any contract.

### Ruling C — rejecting a proposal whose draft was never published

DESIGN §D says a rejected proposal's draft is archived. `archive_content` is legal **from
`published` only** (`content.py:542-575`: a `draft` raises `ConflictError`, per the task-00 pinned
transition matrix). Both states are reachable: the demo's bad fix *was* published (that is why the
after-run regressed), but a proposal can also be rejected before anyone published its draft.

**Decision: `reject_proposal` archives the linked row iff its status is `published`; for a `draft`,
an already-`archived`, or a missing/soft-deleted row it archives nothing and records what it found.**
Rationale: the *purpose* of the archive step is to take a bad fix out of the corpus — archiving
removes its chunks, which is what undoes the regression. A draft has no chunks and is already
invisible to retrieval and to the public feed, so there is nothing to undo; deleting it instead
would destroy a human-reviewable artifact nobody asked us to destroy, and publishing-then-archiving
to satisfy the matrix would put a bad fix live on purpose. The outcome is recorded in the evidence
blob (`rejection.draft_status_after`) so the decision is auditable rather than silent, and both
branches are pinned by tests.

### `app/services/proposals.py`

```python
"""Content proposals: the record that closes the eval loop (phase-9 DESIGN §D).

Session-first plain functions (CONVENTIONS.md §3) — flush, never commit. The one thing this module
exists to enforce is `accept_proposal`'s gate: "validated before acceptance" is a DATA
PRECONDITION, not a synchronous harness run (a run takes minutes; no MCP step budget allows one).
A proposal may only become `accepted` when two persisted eval runs say so.
"""


@dataclass(frozen=True)
class AcceptanceCheck:
    """Why `accept_proposal` would (not) accept — the gate's own explanation, for reports/slides."""

    before_id: uuid.UUID | None
    after_id: uuid.UUID | None
    corpus_changed: bool
    pct_before: float | None
    pct_after: float | None
    regressions: list[str]
    blocked_by: str | None   # None == acceptable; else the first failing gate's name


def kind_for_cause(failure_cause: str) -> str:
    """Map a taxonomy failure cause onto the `content_proposals.kind` that fixes it.

    DESIGN "Diagnosis" row ("maps 1:1 onto proposal kinds"), via
    `app.services.eval_policy.PROPOSAL_KIND_BY_CAUSE`.

    Raises:
        ValueError: `failure_cause` is unknown, or is `judge_disagreement` — which maps to no
            proposal at all: a judge that disagrees with a human is fixed by calibration
            (task 08), and writing an article would be treating the symptom.
    """


def propose_content_fix(
    session: Session,
    *,
    kind: str,
    title: str,
    rationale: str,
    evidence: Sequence[Mapping[str, object]],
    actor_id: uuid.UUID | None,
    target_content_id: uuid.UUID | None = None,
) -> ContentProposal:
    """Record a proposed fix AND create the draft that carries it (DESIGN §D).

    Steps, in order:

    1. validate `kind` against `PROPOSAL_KINDS` (`ValueError` otherwise — the DB CHECK is the
       backstop, not the error message a caller should get);
    2. `create_draft(session, title=title, body_md=<stub>, tags=(), actor_id=actor_id)` — the
       EXISTING service function, so the draft is an ordinary CMS draft with a server-generated
       slug, actor stamping and lifecycle rules, indistinguishable from a hand-made one;
    3. write the `ContentProposal` row with `draft_content_id` = that draft,
       `eval_run_before_id` = `latest_runs(session, kind="answer", limit=1)`'s id **or `None`**
       (no baseline yet is not an error here — `accept_proposal` is where it becomes one), and
       `evidence` = the snapshot envelope below;
    4. `flush()` and return the proposal.

    A draft is created for EVERY kind, including `retune` (where the fix is a threshold, not prose):
    it keeps one code path, gives every proposal a reviewable artifact, and gives `reject_proposal`
    something to archive. For `retune` the stub records the proposed change as text.

    `evidence` is the caller's weak-query rows (e.g. `report_weak_queries`' `weak_queries` list).
    They are stored as a SNAPSHOT wrapped in one envelope —
    `{"weak_queries": [...], "captured_at": "<iso>"}` — not as FKs: chat rows are prunable and the
    blob itself is the artifact (DESIGN §D), and the column is typed `dict[str, object]`
    (`app.models.eval`), matching `tests/test_eval_models.py`'s existing shape. Build a NEW dict;
    never mutate one the caller still holds (plain JSONB, no `MutableDict`).

    Args:
        session: the caller's `Session`.
        kind: `new_article` | `expand_article` | `retune` — use `kind_for_cause` to derive it from
            a failure cause.
        title: the proposed article title (also the draft's title).
        rationale: why, in prose — what the weak queries showed.
        evidence: the weak-query rows that motivated this, snapshotted.
        actor_id: the admin (or connector user) proposing — stamped as `created_by` and as the
            draft's author.
        target_content_id: the existing article an `expand_article`/`retune` fix would change.

    Returns:
        The newly created (and flushed) `ContentProposal`.

    Raises:
        ValueError: `kind` is not one of `PROPOSAL_KINDS`.
    """


def list_proposals(
    session: Session, *, status: str | None = None, limit: int = 50
) -> list[ContentProposal]:
    """Proposals newest-first (`created_at DESC, id DESC`), optionally filtered by `status`.

    Raises:
        ValueError: `status` is not one of `app.services.eval_policy.PROPOSAL_STATUSES` — a typo'd
            filter would otherwise return an empty list that reads like "no proposals", which is
            exactly the wrong answer to show on a stage.
    """


def check_acceptance(session: Session, proposal: ContentProposal, after_id: uuid.UUID) -> AcceptanceCheck:
    """Evaluate the four gates without mutating anything (so a caller can explain a refusal)."""


def accept_proposal(
    session: Session, proposal_id: uuid.UUID, *, eval_run_after_id: uuid.UUID
) -> ContentProposal:
    """Accept a proposal the DATA supports — the evidence behind "validated before acceptance".

    Gates, in this order; the FIRST failure raises:

    | # | Gate | Raises |
    |---|---|---|
    | 0 | the proposal exists | `NotFoundError` |
    | 1 | its `status` is still `proposed` | `ConflictError` (already decided — idempotent re-accept is NOT silently allowed: a second accept against a different after-run would rewrite history) |
    | 2 | `eval_run_before_id` is set, and that run row exists | `ConflictError` / `NotFoundError` |
    | 3 | `eval_run_after_id` names a run, of `kind="answer"` | `NotFoundError` / `ConflictError` |
    | 4 | `after.corpus_digest != before.corpus_digest` | `ConflictError` — the corpus did not change between the runs, so the after-run measured nothing new; a fix nobody published cannot be validated |
    | 5 | `after.pct_fully_supported >= before.pct_fully_supported` | `ConflictError` |
    | 6 | `compare_runs(before, after).regressions == []` | `ConflictError`, naming up to the first three regressed questions |

    On success: `status = "accepted"`, `eval_run_after_id` stamped, `flush()`, return.

    Every message is written to be read OUT LOUD at a talk: it names the gate, the two run ids, and
    the numbers. Gate 6 is the demo beat — "the harness said no, so the system rejected its own fix".
    """


def reject_proposal(
    session: Session,
    proposal_id: uuid.UUID,
    *,
    reason: str,
    actor_id: uuid.UUID | None,
    pipeline: ChunkPipeline,
) -> ContentProposal:
    """Reject a proposal and take its fix out of the corpus (DESIGN §D, Ruling C above).

    `status = "rejected"`; the reason is recorded in the evidence envelope as
    `{"rejection": {"reason": ..., "at": "<iso>", "draft_status_after": "<status>|missing"}}`
    (a NEW dict assigned to the column — `content_proposals` has no `reason` column and DESIGN's
    single-migration rule means it is not getting one; the evidence blob is already "the thing that
    goes on the slide"). The linked draft is archived via the existing `archive_content` **iff it is
    `published`** — see Ruling C for the three other cases and why they archive nothing.

    Raises:
        NotFoundError: no such proposal.
        ConflictError: its `status` is not `proposed`.
    """
```

Behaviour pins the implementer must honour exactly (the tests below are the contract):

- The draft body stub is deterministic and names the gap. Exactly:

  ```python
  _DRAFT_BODY_TEMPLATE = (
      "# {title}\n\n"
      "> Proposed content fix — drafted by AdvisorDesk's eval loop, not yet written.\n\n"
      "{rationale}\n\n"
      "## Weak queries this should answer\n\n"
      "{questions}\n"
  )
  ```

  where `{questions}` is one `- "<normalized_question>" (asked <count>x, <kinds>, closest
  similarity <worst_top_similarity or "none">)` line per evidence row, using `.get()` for every key
  (an evidence row is caller-supplied JSON, not a typed object), and the literal
  `- (no weak-query rows supplied)` when `evidence` is empty.
- `check_acceptance` returns `blocked_by` ∈ `{"no_before_run", "missing_before_run",
  "missing_after_run", "after_run_wrong_kind", "corpus_unchanged", "pct_dropped", "regressions"}`
  or `None`; `accept_proposal` is a thin wrapper that raises on a non-`None` `blocked_by`. One
  place owns the rules.
- `propose_content_fix` never commits; `create_draft`'s own flush plus one final flush is all.

### `app/mcp/tools_proposals.py`

Registration: `PROPOSAL_TOOLS: tuple[ToolSpec, ...]` appended last in
`runtime.py::_ALL_TOOLS = (*READ_TOOLS, *WRITE_TOOLS, *GAPS_TOOLS, *PROPOSAL_TOOLS)` — appending
keeps the `mcp-tools.json` diff purely additive (entries are emitted in `_ALL_TOOLS` order).

```python
class ProposeContentFixArgs(BaseModel):
    """`propose_content_fix`'s arguments (phase-9 DESIGN §D)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    kind: Literal["new_article", "expand_article", "retune"] | None = None
    failure_cause: Literal[
        "retrieval_miss", "corpus_gap", "threshold_refusal", "generation_unfaithful",
        "judge_disagreement",
    ] | None = None
    evidence: list[dict[str, object]] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    target_content_id: uuid.UUID | None = None

    @field_validator("title", "rationale")
    @classmethod
    def _not_whitespace_only(cls, value: str) -> str: ...

    @model_validator(mode="after")
    def _exactly_one_kind_source(self) -> ProposeContentFixArgs:
        """Exactly one of `kind` / `failure_cause` — neither (we will not guess) nor both
        (which one wins would be invisible). `ValueError` here surfaces as `ToolInputError`."""


class ListProposalsArgs(BaseModel):
    """`list_proposals`'s arguments. `limit` defaults to 20, not the service's own 50: a tool
    result lands in a model's context window, so the MCP default mirrors
    `tools_gaps._DEFAULT_LIMIT`/`_MAX_LIMIT` (20/100) rather than the service default. Deliberate,
    not a drift."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["proposed", "accepted", "rejected"] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class AcceptProposalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: uuid.UUID
    eval_run_after_id: uuid.UUID


class RejectProposalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: uuid.UUID
    reason: str = Field(min_length=1)
```

Handlers (thin, same `(args, *, session, actor_id) -> dict[str, Any]` shape; every `uuid`/
`datetime` stringified, same rule as `tools_gaps`):

| Tool | Returns |
|---|---|
| `propose_content_fix` | `{"id", "kind", "title", "status", "draft_content_id", "draft_slug", "eval_run_before_id"}` |
| `list_proposals` | `{"count", "proposals": [{"id", "kind", "title", "status", "draft_content_id", "target_content_id", "eval_run_before_id", "eval_run_after_id", "created_at"}]}` |
| `accept_proposal` | `{"id", "status", "eval_run_before_id", "eval_run_after_id", "pct_before", "pct_after", "improvements", "regressions"}` (the last two are counts) |
| `reject_proposal` | `{"id", "status", "reason", "draft_content_id", "draft_status_after"}` |

- `propose_content_fix`'s handler resolves `kind` via `kind_for_cause(args.failure_cause)` when the
  caller passed a cause, and re-raises its `ValueError` as
  `ToolInputError("failure_cause: judge_disagreement is a judge-calibration problem, not a content
  gap — no proposal kind fixes it.")` for the `judge_disagreement` case. `ToolInputError` is the
  right type: it is the caller's argument that is wrong, and `call_tool` already maps it to 422.
- `reject_proposal`'s handler passes `pipeline=pipeline_from_session(session)` (Ruling B).
- `accept_proposal`'s handler lets `ConflictError`/`NotFoundError` propagate — the §9 envelope and
  the agent's self-correction pass both want the gate's message verbatim; no `try/except`.

Tool descriptions (verbatim — they ship in `mcp-tools.json` and teach the sequence):

```
propose_content_fix:
"Record a proposed content fix for detected weak queries and create its draft. Pass either kind "
"(new_article/expand_article/retune) or failure_cause (from the eval failure taxonomy) and the "
"weak-query rows as evidence. Creates a DRAFT only — publishing is a separate, explicitly "
"requested step."

list_proposals:
"List content-fix proposals, newest first, optionally filtered by status "
"(proposed/accepted/rejected)."

accept_proposal:
"Accept a proposal — allowed ONLY when the eval data supports it: a baseline run and the "
"eval_run_after_id run must both exist, the after-run must have measured a changed corpus, "
"pct_fully_supported must not have dropped, and no question may have regressed. Otherwise this "
"fails with a conflict explaining which check said no."

reject_proposal:
"Reject a proposal with a reason; if its draft was published, it is archived so the change leaves "
"the corpus."
```

### `app/agent/loop.py` — awareness (one paragraph)

Append to `SYSTEM_PROMPT`:

```python
"When report_weak_queries shows a real content gap, you can propose a fix: call "
"propose_content_fix (which records the proposal and creates a draft), then — only if the admin "
"asks you to publish — publish that draft, then the eval harness is re-run OUTSIDE this "
"conversation, and accept_proposal is called with the new run's id. accept_proposal will refuse "
"unless the new run shows no regressions and no drop, so never claim a fix is validated before "
"it returns successfully; reject_proposal records a rejected one and archives its draft."
```

Add bullet 7 to the intent comment above `SYSTEM_PROMPT` recording the one risk this paragraph
carries: it must not read as permission to publish. The publish rule at lines 82-84 stays verbatim,
and the clause above says "only if the admin asks you to publish" for exactly that reason —
`tests/test_agent_loop.py:485-497`'s publish pin must still pass unchanged.

## Steps (TDD)

- [ ] **RED — test-author, 1/2.** Create `apps/api/tests/test_proposals.py`:

```python
"""`app.services.proposals` pins (phase-9 task-16, DESIGN §D).

The acceptance gate is the point of this file: five refusal branches and one clean accept, all on
real `eval_runs`/`eval_results` rows written through `record_run` (no harness, no network) with a
real published-content change between them so the corpus digest genuinely moves.

`ContentProposal.kind`'s CHECK is already pinned by `tests/test_eval_models.py:111-126` (task 01);
this file pins the `status` CHECK, the half task 01 left uncovered, rather than duplicating it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Chunk, Content, ContentProposal, EvalRun, User
from app.services.errors import ConflictError, NotFoundError
from app.services.eval_policy import PROPOSAL_KIND_BY_CAUSE
from app.services.eval_runs import record_run
from app.services.lifecycle import NoopChunkPipeline
from app.services.proposals import (
    accept_proposal,
    check_acceptance,
    kind_for_cause,
    list_proposals,
    propose_content_fix,
    reject_proposal,
)

_EVIDENCE = [
    {
        "normalized_question": "do rsus work differently outside the us",
        "count": 4,
        "kinds": ["near_miss"],
        "worst_top_similarity": 0.41,
    },
    {
        "normalized_question": "what about qsbs",
        "count": 2,
        "kinds": ["refused"],
        "worst_top_similarity": None,
    },
]


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


@dataclass(frozen=True)
class FakeRow:
    question: str
    answerable: bool = True
    expected_slugs: list[str] = field(default_factory=list)
    cited_slugs: list[str] = field(default_factory=list)
    slugs_hit: bool = True
    fully_supported: bool | None = True
    refused: bool = False
    verdict: str = "PASS"
    top_similarity: float | None = 0.8
    answer_text: str = "an answer"
    question_class: str | None = None
    persona: str | None = None
    metrics: dict[str, object] | None = None


@dataclass(frozen=True)
class FakeReport:
    rows: list[FakeRow]
    pct_fully_supported: float = 100.0
    refusal_correct: int = 0
    refusal_total: int = 0


def _record(session: Session, report: FakeReport, *, label: str, kind: str = "answer"):
    """One real `eval_runs` row (+ its results) — `record_run` computes the corpus fingerprint."""
    return record_run(
        session,
        report,
        label=label,
        kind=kind,
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        judge_model="gpt-4o",
        similarity_threshold=0.5,
        retrieval_k=6,
        git_sha="deadbeef",
    )


def _publish(session: Session, slug: str) -> Content:
    """Publish one content row WITH a chunk, so the corpus fingerprint/digest actually moves."""
    content = Content(
        title=f"Title {slug}",
        slug=slug,
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    session.add(Chunk(content_id=content.id, chunk_index=0, text="chunk"))
    session.flush()
    return content


def _report(*questions_and_verdicts: tuple[str, str], pct: float) -> FakeReport:
    return FakeReport(
        rows=[
            FakeRow(question=question, verdict=verdict, fully_supported=verdict == "PASS")
            for question, verdict in questions_and_verdicts
        ],
        pct_fully_supported=pct,
    )


# ---------------------------------------------------------------------------
# The CHECK constraint task 01 left unpinned
# ---------------------------------------------------------------------------


def test_status_check_rejects_a_value_outside_the_three_states(db_session: Session) -> None:
    db_session.add(
        ContentProposal(
            kind="new_article", title="t", rationale="r", evidence={}, status="half-accepted"
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_kind_check_rejects_a_value_outside_the_three_kinds(db_session: Session) -> None:
    """The task-01 ruling asks for both CHECKs to be pinned behaviourally. `kind` is also pinned
    at `tests/test_eval_models.py:123-126`; it is re-asserted here so this task's own file is
    self-contained evidence for the reviewer (one line, no fixture, no overlap to maintain)."""
    db_session.add(ContentProposal(kind="rewrite_everything", title="t", rationale="r", evidence={}))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ---------------------------------------------------------------------------
# kind_for_cause
# ---------------------------------------------------------------------------


def test_kind_for_cause_maps_every_actionable_cause() -> None:
    assert kind_for_cause("corpus_gap") == "new_article"
    assert kind_for_cause("generation_unfaithful") == "expand_article"
    assert kind_for_cause("retrieval_miss") == "retune"
    assert kind_for_cause("threshold_refusal") == "retune"


def test_kind_for_cause_refuses_judge_disagreement_and_unknown_causes() -> None:
    """`judge_disagreement` maps to no proposal: the fix is judge calibration, not content."""
    assert PROPOSAL_KIND_BY_CAUSE["judge_disagreement"] is None
    with pytest.raises(ValueError, match="judge_disagreement"):
        kind_for_cause("judge_disagreement")
    with pytest.raises(ValueError, match="bogus_cause"):
        kind_for_cause("bogus_cause")


# ---------------------------------------------------------------------------
# propose_content_fix
# ---------------------------------------------------------------------------


def test_propose_creates_a_linked_draft_and_snapshots_the_evidence(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    baseline = _record(db_session, _report(("q1", "PASS"), pct=50.0), label="baseline")

    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="RSUs for employees outside the US",
        rationale="Four near-miss questions in 30 days, closest source at 0.41.",
        evidence=_EVIDENCE,
        actor_id=actor_id,
    )

    assert proposal.status == "proposed"
    assert proposal.kind == "new_article"
    assert proposal.eval_run_before_id == baseline.id
    assert proposal.created_by == actor_id
    assert proposal.draft_content_id is not None

    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None
    assert draft.status == "draft"
    assert draft.title == "RSUs for employees outside the US"
    assert draft.author_id == actor_id
    # The stub names the gap it exists to close — a human/agent finishes the body before publishing.
    assert "do rsus work differently outside the us" in draft.body_md
    assert "0.41" in draft.body_md

    assert proposal.evidence["weak_queries"] == _EVIDENCE
    assert isinstance(proposal.evidence["captured_at"], str)


def test_propose_with_no_baseline_run_still_records_the_proposal(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """No eval run yet is not an error HERE — it becomes one at `accept_proposal`."""
    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="Crypto compensation basics",
        rationale="Two refusals.",
        evidence=[],
        actor_id=actor_id,
    )

    assert proposal.eval_run_before_id is None
    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None and "no weak-query rows supplied" in draft.body_md


def test_propose_stamps_the_latest_answer_run_not_an_agent_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    answer_run = _record(db_session, _report(("q1", "PASS"), pct=60.0), label="answers")
    _record(db_session, _report(("task-1", "PASS"), pct=90.0), label="agents", kind="agent")

    proposal = propose_content_fix(
        db_session,
        kind="expand_article",
        title="ESPP dispositions, expanded",
        rationale="Low-confidence answers.",
        evidence=_EVIDENCE,
        actor_id=actor_id,
    )

    assert proposal.eval_run_before_id == answer_run.id


def test_propose_rejects_an_unknown_kind_before_touching_the_database(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(ValueError, match="kind"):
        propose_content_fix(
            db_session,
            kind="rewrite_everything",
            title="T",
            rationale="R",
            evidence=[],
            actor_id=actor_id,
        )

    assert db_session.scalars(select(ContentProposal)).all() == []
    assert db_session.scalars(select(Content)).all() == []


def test_propose_does_not_alias_the_callers_evidence(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    rows = [{"normalized_question": "q", "count": 1}]
    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="Aliasing check",
        rationale="R",
        evidence=rows,
        actor_id=actor_id,
    )

    rows[0]["count"] = 999

    assert proposal.evidence["weak_queries"][0]["count"] == 1


# ---------------------------------------------------------------------------
# list_proposals
# ---------------------------------------------------------------------------


def test_list_proposals_is_newest_first_and_filters_by_status(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    first = propose_content_fix(
        db_session, kind="new_article", title="First", rationale="R", evidence=[], actor_id=actor_id
    )
    second = propose_content_fix(
        db_session, kind="retune", title="Second", rationale="R", evidence=[], actor_id=actor_id
    )
    first.status = "rejected"
    db_session.flush()

    assert [p.id for p in list_proposals(db_session)][0] == second.id
    assert [p.id for p in list_proposals(db_session, status="proposed")] == [second.id]
    assert [p.id for p in list_proposals(db_session, status="rejected")] == [first.id]
    assert len(list_proposals(db_session, limit=1)) == 1
    # A typo'd filter must not read as "no proposals".
    with pytest.raises(ValueError, match="status"):
        list_proposals(db_session, status="propsed")


# ---------------------------------------------------------------------------
# accept_proposal — one test per gate
# ---------------------------------------------------------------------------


def test_accept_raises_not_found_for_an_unknown_proposal(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        accept_proposal(db_session, uuid.uuid4(), eval_run_after_id=uuid.uuid4())


def test_accept_refuses_when_there_is_no_baseline_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")

    with pytest.raises(ConflictError, match="before"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    db_session.refresh(proposal)
    assert proposal.status == "proposed"
    assert proposal.eval_run_after_id is None


def test_accept_raises_not_found_for_an_unknown_after_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )

    with pytest.raises(NotFoundError):
        accept_proposal(db_session, proposal.id, eval_run_after_id=uuid.uuid4())


def test_accept_refuses_an_agent_run_as_the_after_run(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "the-fix")
    agent_run = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="a", kind="agent")

    with pytest.raises(ConflictError, match="kind"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=agent_run.id)


def test_accept_refuses_when_the_corpus_never_changed(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Gate 4: identical `corpus_digest` means the after-run measured the SAME corpus — nobody
    published the fix, so there is nothing validated."""
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")

    assert proposal.eval_run_before_id is not None
    before = db_session.get(EvalRun, proposal.eval_run_before_id)
    assert before is not None and before.corpus_digest == after.corpus_digest

    with pytest.raises(ConflictError, match="corpus"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)


def test_accept_refuses_when_the_headline_metric_dropped(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "PASS"), ("q2", "PASS"), pct=100.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "the-fix")
    after = _record(db_session, _report(("q1", "PASS"), ("q2", "PASS"), pct=90.0), label="after")

    with pytest.raises(ConflictError, match="pct_fully_supported"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)


def test_accept_refuses_a_fix_that_regressed_other_questions(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Gate 6 — the demo beat: the new article hijacked two questions' retrieval. Even though the
    headline percentage did not drop, two questions went PASS -> FAIL, so the system rejects its
    own fix."""
    _record(
        db_session,
        _report(("planted", "FAIL"), ("a", "PASS"), ("b", "PASS"), ("c", "PASS"), pct=75.0),
        label="baseline",
    )
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "the-bad-fix")
    after = _record(
        db_session,
        _report(("planted", "PASS"), ("a", "FAIL"), ("b", "FAIL"), ("c", "PASS"), pct=75.0),
        label="after",
    )

    with pytest.raises(ConflictError) as excinfo:
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    message = str(excinfo.value)
    assert "regress" in message.lower()
    assert "a" in message and "b" in message

    db_session.refresh(proposal)
    assert proposal.status == "proposed"


def test_a_clean_fix_is_accepted_and_stamped(db_session: Session, actor_id: uuid.UUID) -> None:
    before = _record(
        db_session, _report(("planted", "FAIL"), ("a", "PASS"), pct=50.0), label="baseline"
    )
    proposal = propose_content_fix(
        db_session,
        kind="new_article",
        title="RSUs for employees outside the US",
        rationale="R",
        evidence=_EVIDENCE,
        actor_id=actor_id,
    )
    _publish(db_session, "rsus-outside-the-us")
    after = _record(
        db_session, _report(("planted", "PASS"), ("a", "PASS"), pct=100.0), label="after"
    )

    check = check_acceptance(db_session, proposal, after.id)
    assert check.blocked_by is None
    assert check.corpus_changed is True
    assert check.regressions == []
    assert check.pct_before == pytest.approx(50.0)
    assert check.pct_after == pytest.approx(100.0)

    accepted = accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    assert accepted.status == "accepted"
    assert accepted.eval_run_before_id == before.id
    assert accepted.eval_run_after_id == after.id


def test_a_decided_proposal_cannot_be_accepted_again(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "the-fix")
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")
    accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    with pytest.raises(ConflictError, match="accepted"):
        accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)


# ---------------------------------------------------------------------------
# reject_proposal
# ---------------------------------------------------------------------------


def test_reject_archives_a_published_draft_and_records_the_reason(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    from app.services.content import publish_content

    proposal = propose_content_fix(
        db_session, kind="new_article", title="Bad fix", rationale="R", evidence=[], actor_id=actor_id
    )
    assert proposal.draft_content_id is not None
    publish_content(
        db_session, proposal.draft_content_id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    rejected = reject_proposal(
        db_session,
        proposal.id,
        reason="Regressed two questions in run after-2026-09-22.",
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    assert rejected.status == "rejected"
    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None and draft.status == "archived"
    rejection = rejected.evidence["rejection"]
    assert rejection["reason"] == "Regressed two questions in run after-2026-09-22."
    assert rejection["draft_status_after"] == "archived"
    assert isinstance(rejection["at"], str)


def test_reject_leaves_an_unpublished_draft_alone(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """A draft has no chunks and is invisible to retrieval, and `archive_content` is legal from
    `published` only (the task-00 transition matrix) — so there is nothing to undo and nothing is
    destroyed. The outcome is recorded, not silent."""
    proposal = propose_content_fix(
        db_session, kind="retune", title="Never published", rationale="R", evidence=[], actor_id=actor_id
    )

    rejected = reject_proposal(
        db_session,
        proposal.id,
        reason="Threshold change not worth it.",
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    draft = db_session.get(Content, proposal.draft_content_id)
    assert draft is not None and draft.status == "draft"
    assert rejected.evidence["rejection"]["draft_status_after"] == "draft"


def test_reject_is_only_legal_from_proposed(db_session: Session, actor_id: uuid.UUID) -> None:
    _record(db_session, _report(("q1", "FAIL"), pct=0.0), label="baseline")
    proposal = propose_content_fix(
        db_session, kind="new_article", title="T", rationale="R", evidence=[], actor_id=actor_id
    )
    _publish(db_session, "the-fix")
    after = _record(db_session, _report(("q1", "PASS"), pct=100.0), label="after")
    accept_proposal(db_session, proposal.id, eval_run_after_id=after.id)

    with pytest.raises(ConflictError, match="accepted"):
        reject_proposal(
            db_session, proposal.id, reason="Too late.", actor_id=actor_id, pipeline=NoopChunkPipeline()
        )


def test_reject_raises_not_found_for_an_unknown_proposal(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        reject_proposal(
            db_session, uuid.uuid4(), reason="R", actor_id=None, pipeline=NoopChunkPipeline()
        )
```

- [ ] **RED — test-author, 2/2.** Create `apps/api/tests/test_proposal_tools.py`:

```python
"""The four proposal MCP tools (phase-9 task-16, DESIGN §D) through the real `call_tool` seam."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.agent.loop import SYSTEM_PROMPT
from app.mcp.runtime import call_tool, list_tool_schemas
from app.models import Chunk, Content, User
from app.services.errors import ConflictError, ToolInputError
from app.services.eval_runs import record_run
from app.services.lifecycle import NoopChunkPipeline

_PROPOSAL_TOOL_NAMES = {
    "propose_content_fix",
    "list_proposals",
    "accept_proposal",
    "reject_proposal",
}


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


@dataclass(frozen=True)
class FakeRow:
    question: str
    answerable: bool = True
    expected_slugs: list[str] = field(default_factory=list)
    cited_slugs: list[str] = field(default_factory=list)
    slugs_hit: bool = True
    fully_supported: bool | None = True
    refused: bool = False
    verdict: str = "PASS"
    top_similarity: float | None = 0.8
    answer_text: str = "an answer"
    question_class: str | None = None
    persona: str | None = None
    metrics: dict[str, object] | None = None


@dataclass(frozen=True)
class FakeReport:
    rows: list[FakeRow]
    pct_fully_supported: float = 100.0
    refusal_correct: int = 0
    refusal_total: int = 0


def _record(session: Session, *, label: str, pct: float, verdict: str):
    return record_run(
        session,
        FakeReport(
            rows=[FakeRow(question="q1", verdict=verdict, fully_supported=verdict == "PASS")],
            pct_fully_supported=pct,
        ),
        label=label,
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        judge_model="gpt-4o",
        similarity_threshold=0.5,
        retrieval_k=6,
    )


def _publish_something(session: Session, slug: str) -> None:
    content = Content(
        title=f"Title {slug}",
        slug=slug,
        body_md="body",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    session.add(Chunk(content_id=content.id, chunk_index=0, text="chunk"))
    session.flush()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_the_four_proposal_tools_are_registered_with_descriptions() -> None:
    by_name = {entry["name"]: entry for entry in list_tool_schemas()}

    assert _PROPOSAL_TOOL_NAMES <= set(by_name)
    assert len(by_name) == 14
    for name in _PROPOSAL_TOOL_NAMES:
        assert by_name[name]["description"].strip()
    assert "no regressions" in by_name["accept_proposal"]["description"]


# ---------------------------------------------------------------------------
# propose_content_fix
# ---------------------------------------------------------------------------


def test_propose_tool_creates_the_proposal_and_its_draft(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, label="baseline", pct=50.0, verdict="FAIL")

    result = call_tool(
        "propose_content_fix",
        {
            "title": "RSUs for employees outside the US",
            "rationale": "Four near-miss questions in 30 days.",
            "kind": "new_article",
            "evidence": [
                {"normalized_question": "do rsus work outside the us", "count": 4,
                 "kinds": ["near_miss"], "worst_top_similarity": 0.41}
            ],
        },
        session=db_session,
        actor_id=actor_id,
    )

    assert result["status"] == "proposed"
    assert result["kind"] == "new_article"
    assert isinstance(result["id"], str)
    uuid.UUID(result["id"])
    assert isinstance(result["draft_content_id"], str)
    assert result["draft_slug"] == "rsus-for-employees-outside-the-us"
    assert isinstance(result["eval_run_before_id"], str)


def test_propose_tool_derives_the_kind_from_a_failure_cause(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    result = call_tool(
        "propose_content_fix",
        {"title": "Crypto compensation", "rationale": "Refusals.", "failure_cause": "corpus_gap"},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["kind"] == "new_article"


def test_propose_tool_rejects_judge_disagreement_as_a_content_fix(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(ToolInputError, match="judge"):
        call_tool(
            "propose_content_fix",
            {"title": "T", "rationale": "R", "failure_cause": "judge_disagreement"},
            session=db_session,
            actor_id=actor_id,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"title": "T", "rationale": "R"},
        {"title": "T", "rationale": "R", "kind": "new_article", "failure_cause": "corpus_gap"},
        {"title": "   ", "rationale": "R", "kind": "new_article"},
        {"title": "T", "rationale": "R", "kind": "rewrite_all"},
        {"title": "T", "rationale": "R", "kind": "new_article", "bogus": 1},
    ],
)
def test_propose_tool_rejects_bad_arguments(
    db_session: Session, actor_id: uuid.UUID, arguments: dict[str, object]
) -> None:
    """Neither-nor-both `kind`/`failure_cause`, a blank title, an unknown kind, an unknown
    argument — all `ToolInputError` before the service is reached."""
    with pytest.raises(ToolInputError):
        call_tool("propose_content_fix", arguments, session=db_session, actor_id=actor_id)


# ---------------------------------------------------------------------------
# list / accept / reject
# ---------------------------------------------------------------------------


def test_list_tool_returns_json_able_rows_filtered_by_status(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    call_tool(
        "propose_content_fix",
        {"title": "First", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )

    result = call_tool("list_proposals", {"status": "proposed"}, session=db_session, actor_id=actor_id)

    assert result["count"] == 1
    row = result["proposals"][0]
    assert row["title"] == "First"
    assert row["status"] == "proposed"
    assert isinstance(row["created_at"], str)
    datetime.fromisoformat(row["created_at"])
    assert result == call_tool("list_proposals", {}, session=db_session, actor_id=actor_id)


def test_accept_tool_accepts_a_clean_fix_and_reports_the_numbers(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _record(db_session, label="baseline", pct=50.0, verdict="FAIL")
    proposed = call_tool(
        "propose_content_fix",
        {"title": "The fix", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )
    _publish_something(db_session, "the-fix")
    after = _record(db_session, label="after", pct=100.0, verdict="PASS")

    result = call_tool(
        "accept_proposal",
        {"proposal_id": proposed["id"], "eval_run_after_id": str(after.id)},
        session=db_session,
        actor_id=actor_id,
    )

    assert result["status"] == "accepted"
    assert result["eval_run_after_id"] == str(after.id)
    assert result["pct_before"] == pytest.approx(50.0)
    assert result["pct_after"] == pytest.approx(100.0)
    assert result["regressions"] == 0
    assert result["improvements"] == 1


def test_accept_tool_surfaces_the_gate_refusal_as_a_conflict(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """No `try/except` anywhere in the tool path: the gate's message reaches the caller verbatim
    (the §9 409 envelope over HTTP, the self-correction feedback in the agent loop)."""
    _record(db_session, label="baseline", pct=50.0, verdict="FAIL")
    proposed = call_tool(
        "propose_content_fix",
        {"title": "Unpublished fix", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )
    after = _record(db_session, label="after", pct=100.0, verdict="PASS")

    with pytest.raises(ConflictError, match="corpus"):
        call_tool(
            "accept_proposal",
            {"proposal_id": proposed["id"], "eval_run_after_id": str(after.id)},
            session=db_session,
            actor_id=actor_id,
        )


def test_reject_tool_archives_the_published_draft_through_the_call_tool_pipeline(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Also proves Ruling B's moved pipeline reader works from this module: `call_tool` stashes
    the pipeline, the handler reads it back, `archive_content` gets a real one."""
    proposed = call_tool(
        "propose_content_fix",
        {"title": "Bad fix", "rationale": "R", "kind": "new_article"},
        session=db_session,
        actor_id=actor_id,
    )
    call_tool(
        "publish",
        {"content_id": proposed["draft_content_id"]},
        session=db_session,
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    result = call_tool(
        "reject_proposal",
        {"proposal_id": proposed["id"], "reason": "Regressed two questions."},
        session=db_session,
        actor_id=actor_id,
        pipeline=NoopChunkPipeline(),
    )

    assert result["status"] == "rejected"
    assert result["draft_status_after"] == "archived"
    draft = db_session.get(Content, uuid.UUID(proposed["draft_content_id"]))
    assert draft is not None and draft.status == "archived"


# ---------------------------------------------------------------------------
# Agent awareness
# ---------------------------------------------------------------------------


def test_system_prompt_teaches_the_propose_publish_rerun_accept_sequence() -> None:
    lower = SYSTEM_PROMPT.lower()

    assert "propose_content_fix" in lower
    assert "accept_proposal" in lower
    assert "reject_proposal" in lower
    # It must NOT read as permission to publish on its own initiative (the existing pin at
    # tests/test_agent_loop.py:485 stays green; this is the same rule stated from this side).
    assert "only if the admin asks" in lower or "unless the admin asks" in lower
```

- [ ] **Run RED:**
  ```sh
  export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r')"
  cd apps/api && uv run pytest tests/test_proposals.py tests/test_proposal_tools.py -q
  ```
  Both files fail at collection (`ModuleNotFoundError: app.services.proposals`, and
  `ImportError: cannot import name 'propose_content_fix'` / the four tool names missing from the
  registry). `app.services.eval_policy` already exists (task 15), so its import must NOT be part of
  the RED evidence — if it is, task 15 did not land. Paste the evidence.

- [ ] **GREEN — implementer, 1/4 (pipeline reader).** Ruling B: move `_pipeline_from_session` to
  `app/mcp/tool_spec.py::pipeline_from_session`; update `tools_write.py` and its imports. Run
  `uv run pytest tests/test_mcp_write_tools_guards.py tests/test_mcp_write_tools.py -q` — both must
  pass untouched.

- [ ] **GREEN — implementer, 2/4 (service).** Write `app/services/proposals.py` per Interfaces, with
  `check_acceptance` owning the gate rules and `accept_proposal` as its thin raiser.

- [ ] **GREEN — implementer, 3/4 (tools).** Write `app/mcp/tools_proposals.py`; register
  `PROPOSAL_TOOLS` last in `runtime.py::_ALL_TOOLS`; add the `SYSTEM_PROMPT` paragraph + intent
  bullet 7.

- [ ] **GREEN — implementer, 4/4 (baselines + pins).** Regenerate and apply the three
  registry-inventory edits:
  ```sh
  cd apps/api && uv run python scripts/export_mcp_tools.py && git diff --stat -- mcp-tools.json
  ```
  The diff must be exactly four appended entries.

- [ ] **Run GREEN:** `uv run pytest tests/test_proposals.py tests/test_proposal_tools.py
  tests/test_failure_taxonomy.py tests/test_mcp_write_tools.py tests/test_mcp_write_tools_guards.py
  tests/test_agent_loop.py -q`, then the whole suite `uv run pytest -q`.

- [ ] **Gates:** `pnpm gates:api` (incl. **lint-imports** — this task moves code across two layer
  boundaries and is the one most able to break them).

- [ ] **Commit:**
  `git add apps/api/app apps/api/tests apps/api/mcp-tools.json`
  `git commit -m "feat(api): content proposals + data-gated acceptance + four MCP tools (p9 t16)"`

## Verify

```sh
export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r')"
cd apps/api
uv run pytest tests/test_proposals.py tests/test_proposal_tools.py tests/test_failure_taxonomy.py -q
uv run lint-imports
uv run python scripts/export_mcp_tools.py && git diff --exit-code -- mcp-tools.json   # clean AFTER the commit
# Ruling A: this task imports the shared constants, it does not move them
git diff --stat main...HEAD -- app/services/eval_policy.py app/eval/taxonomy.py   # only task 15's commit may appear
pnpm gates:api
```

## Acceptance

- All six `accept_proposal` gates behave exactly as the per-gate tests pin, in that order, with the
  first failure raising and **nothing mutated** on a refusal; the regression message names the
  regressed questions.
- A clean accept stamps `status="accepted"` + `eval_run_after_id`; a decided proposal can be
  neither accepted nor rejected again.
- `propose_content_fix` creates a real draft through the existing `create_draft` (server slug,
  actor stamping, `status="draft"`), links it, stamps the latest **answer** run as `before` (or
  `None`), and snapshots evidence as `{"weak_queries": [...], "captured_at": ...}` with no aliasing
  of the caller's list.
- `reject_proposal` records the reason in the evidence blob and archives the draft **iff it was
  published**, per Ruling C, with the outcome recorded in both branches.
- `content_proposals.status`' CHECK is pinned behaviourally (`kind`'s already is, in
  `tests/test_eval_models.py` — the implementer report says so rather than duplicating it).
- `app/services/proposals.py` reads `PROPOSAL_KIND_BY_CAUSE`/`PROPOSAL_KINDS` from
  `app.services.eval_policy` and re-types neither the five cause names nor the three kinds;
  `app/services/eval_policy.py` and `app/eval/taxonomy.py` are **unchanged by this task**
  (`git diff --stat` over both is empty); `tests/test_failure_taxonomy.py` still passes untouched;
  `lint-imports` green with no contract edited.
- The pipeline reader lives in `app/mcp/tool_spec.py` with no duplicate left behind, and
  `tests/test_mcp_write_tools_guards.py` passes untouched.
- 14 tools registered; `mcp-tools.json` regenerated in the same commit with exactly four appended
  entries; the three registry-inventory pins updated and no other pre-existing test touched.
- `SYSTEM_PROMPT` teaches propose → publish → re-run → accept **without** weakening the
  never-publish-unasked rule.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-16-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-16-implementer.md` — must
  restate Rulings B and C verbatim (each is a decision the reviewer must confirm, not an omission),
  confirm Ruling A's "imported, not moved" (neither `eval_policy.py` nor `taxonomy.py` in the diff),
  and record the `mcp-tools.json` diff stat.
