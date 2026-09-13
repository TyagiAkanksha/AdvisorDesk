---
id: p9-t15
phase: phase-9-eval-data-loop
depends_on: [p9-t06, p9-t09]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 15 — `weak_queries()`: a refusal is not the only way an answer can be weak

## Goal

"Weak query" stops meaning "refusal". `app/services/chat.py` gains
`weak_queries(session, *, days, limit, threshold)` — a **second consumer of the already-tested
user↔reply pairing**: the pairing moves into one private helper, `content_gaps` becomes a thin
wrapper over it (its 12 pinned tests in `tests/test_content_gaps.py`, the `report_content_gaps`
entry in `mcp-tools.json`, and PRD §6 all stay byte-frozen), and the new function classifies every
paired turn in Python, first match wins: `negative_feedback` → `refused` → `near_miss` →
`low_confidence`. Rows are grouped by normalised question text into `WeakQueryGroup`s, ordered by
`count` desc then `worst_top_similarity` asc, and exposed as a tenth MCP tool
`report_weak_queries` the agent is told about.

This is demo beat 3 (DESIGN §D6): a planted-gap question refuses, and the weak-query report shows
it as `near_miss` with the closest source's similarity — the number the room can argue with.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Part D" (the classification ladder, the grouping
  rule, `WeakQueryGroup`), §A (the `feedback` signal), D6 beat 3, §"Execution order" step 7.
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` §"Global Constraints" (import-linter, wire-surface
  baselines, the `TEST_DATABASE_URL`-only gate command).
- `apps/api/app/services/chat.py` — the whole file. In particular `GapRow` (198-205) and
  `content_gaps` (207-278): the correlated-`MIN(created_at)` pairing (242-251), the
  `retrieval_found.is_(False)` choice and its NULL reasoning (223-229), and the "`days` applies to
  the USER row's `created_at`" rule (230-232). `set_message_feedback` (174-195) is what writes the
  `feedback` column this task reads.
- `apps/api/app/models/chat.py:34-63` — `ChatMessage`: `retrieval_found` (nullable), `top_similarity`
  (`REAL`, nullable), `feedback` (`SmallInteger`, nullable, CHECK −1/1), `created_at` from
  `TimestampMixin`.
- `apps/api/app/eval/taxonomy.py` — the whole file. In particular `FAILURE_CAUSES` + the five cause
  constants (18-30), `NEAR_MISS_BAND = 0.15` (32-34, with the comment saying it is "defined once
  here so the two never drift apart"), `PROPOSAL_KIND_BY_CAUSE` (36-44), and `classify_failure`'s
  use of the band (99-102). This task moves **both** shared constants out (see the ruling below) —
  the cause constants themselves stay.
- `apps/api/tests/test_failure_taxonomy.py:9-21` — the import list (it imports `NEAR_MISS_BAND`
  **and** `PROPOSAL_KIND_BY_CAUSE` from `app.eval.taxonomy`) and line 104's
  `set(PROPOSAL_KIND_BY_CAUSE) == set(FAILURE_CAUSES)` pin. Every test in this file must stay green
  **untouched** after the move.
- `apps/api/pyproject.toml` `[tool.importlinter]` — contract **"app.services imports only
  app.models and app.config"**, whose `forbidden_modules` now names `app.eval` (added in task 03,
  with the explaining comment above the contract). This is the contract that bites here.
- `apps/api/app/mcp/tools_gaps.py` — the whole file: the `ToolSpec` + Pydantic-args + thin-handler
  pattern, `_DEFAULT_DAYS`/`_DEFAULT_LIMIT`/`_MAX_LIMIT`, `extra="forbid"`, and the
  ISO-string/`str(uuid)` serialization rule (52-73).
- `apps/api/app/mcp/runtime.py:51-54` — `_ALL_TOOLS`/`_REGISTRY` (the registration seam; this task
  needs **no** change here, because `GAPS_TOOLS` is already collected).
- `apps/api/app/agent/loop.py:53-89` — `SYSTEM_PROMPT` and the numbered intent comment above it,
  including the final-review note (71-74) that a gaps clause was once REMOVED because the tool was
  not registered. It is registered now; so is this task's.
- `apps/api/tests/test_content_gaps.py` — the 12 frozen tests, and its `_add_session`/`_add_message`
  seeding helpers (65-91) this task's tests mirror.
- `apps/api/tests/test_agent_loop.py:485-513` — the keyword-based `SYSTEM_PROMPT` pin style.
- `apps/api/app/config.py:181` — `similarity_threshold: float = 0.5`.

## Files

**Create**
- `apps/api/app/services/eval_policy.py`
- `apps/api/tests/test_weak_queries.py`

**Modify**
- `apps/api/app/services/chat.py` (extract the pairing; add `weak_queries` + its dataclasses)
- `apps/api/app/eval/taxonomy.py` (import `NEAR_MISS_BAND` + `PROPOSAL_KIND_BY_CAUSE` instead of
  defining them; add `__all__` so both re-exports are intentional) — **the only task in this phase
  that edits this file**; task 16 imports from `app.services.eval_policy` and leaves it alone
- `apps/api/app/mcp/tools_gaps.py` (add `report_weak_queries` to `GAPS_TOOLS`)
- `apps/api/app/agent/loop.py` (one awareness clause in `SYSTEM_PROMPT`)

**Regenerate (same commit)**
- `apps/api/mcp-tools.json` — `cd apps/api && uv run python scripts/export_mcp_tools.py`

**Pre-authorized pre-existing-test updates (controller).** These three are *registry inventory*
pins: they enumerate every registered tool, so a new tool MUST move them. This is the only
exception to the stop rule in §Global Constraints for this task — change exactly these lines and
nothing else:

| File | Line (drifts) | Change |
|---|---|---|
| `apps/api/tests/test_mcp_bearer_auth.py` | 86-96 | add `"report_weak_queries"` to `_EXPECTED_TOOL_NAMES`; extend the comment above it with `+ phase-9 task-15 (report_weak_queries)` |
| `apps/api/tests/test_mcp_bearer_auth.py` | 203-207 | rename `test_bearer_token_initialize_succeeds_and_tools_list_returns_nine_tools` → `..._returns_the_full_registry` and drop "9-tool" from its docstring (the count is already asserted by the set; a number in the name guarantees this churns again next task) |
| `apps/api/tests/test_oauth_e2e_flow.py` | 95-106 | add `"report_weak_queries"` to `_EXPECTED_TOOL_NAMES` + the same comment extension |
| `apps/api/tests/test_oauth_e2e_flow.py` | 298-299 | "exactly the 9 registered tools" → "exactly the registered tool set" |
| `apps/api/tests/test_agent_loop_step_bound.py` | 99, 103 | `== 9` → `== 10`; update the comment to `(10 registered tools — phase-9 task-15 added report_weak_queries)` |

`tests/test_mcp_read_tools.py:315-330` uses `_TOOL_NAMES <= set(by_name)` (a subset check) and needs
no change — confirm this rather than assuming it.

## Interfaces

### Ruling — where the shared loop constants live (decide-and-justify; the contract forbids the obvious import)

DESIGN §D says `weak_queries` splits `refused` from `near_miss` at `threshold − 0.15`, and
`app/eval/taxonomy.py` already owns that constant with an explicit "defined once here so the two
never drift apart" comment. But `weak_queries` lives in `app.services`, and the import-linter
contract "app.services imports only app.models and app.config" lists `app.eval` in
`forbidden_modules` — so `from app.eval.taxonomy import NEAR_MISS_BAND` inside `app/services/chat.py`
is a hard gate failure (`uv run lint-imports`), not a style preference. Task 16's
`app/services/proposals.py` hits the identical wall for `PROPOSAL_KIND_BY_CAUSE`.

**Decision (controller ruling, 2026-09-12): move BOTH constants down into one new dependency-free
leaf inside `app.services` — `apps/api/app/services/eval_policy.py` — in this task, and have
`app.eval.taxonomy` import them from there.** Task 15 therefore owns the whole move and is the only
task that edits `taxonomy.py`; task 16 purely imports from `eval_policy`. One move, one reviewer,
no half-done module.

`PROPOSAL_KIND_BY_CAUSE` is moved here even though nothing in THIS task reads it: the alternative
was a second edit to the same module one task later, which would leave task 15's reviewer looking
at a module whose sibling constant stayed behind for no stated reason.

Why this and not the alternatives:

- **`app.eval` → `app.services` is the legal direction**, declared by DESIGN §B1 ("the harness may
  import `app.rag` and `app.services`") and already exercised by `app.eval.groundedness` →
  `app.services.eval_runs`. No contract forbids it; no contract edit is needed. A new top-level
  `app/eval_constants.py` would instead sit outside every layered package: no contract names it, so
  nothing would stop a later module from importing `app.routes` through it, and it would put an
  eval concept outside the one package the gates actually guard.
- **Re-typing `0.15` in `app/services/chat.py` is forbidden by the authoring notes** and is exactly
  the drift the taxonomy's comment warns about.
- **`Settings` is the wrong home**: these are policy constants of the improvement loop, not
  deployment knobs. CONVENTIONS §5 wants every setting env-overridable with a default; an operator
  retuning the near-miss band per environment would silently change what "near miss" means between
  a recorded eval run and the weak-query report read off the same rows.
- **The re-exports keep task 06's tests untouched.** `tests/test_failure_taxonomy.py:9-21` imports
  `NEAR_MISS_BAND` **and** `PROPOSAL_KIND_BY_CAUSE` from `app.eval.taxonomy`, and line 104 pins
  `set(PROPOSAL_KIND_BY_CAUSE) == set(FAILURE_CAUSES)` — which becomes the cross-layer drift pin
  once the mapping's keys are literals in the leaf. `classify_failure` (taxonomy.py:100) still
  *uses* the band, but nothing in taxonomy.py uses the mapping, so an `__all__` (below) is what
  makes that second re-export intentional and ruff-clean. Both modules then read the same objects —
  pinned below by identity assertions.
- Task 16 **only imports** from this module (`kind_for_cause`) and adds its own new
  `PROPOSAL_KINDS`/`PROPOSAL_STATUSES` nowhere else — they are defined here too, in this task, so
  the proposal vocabulary has one home from the start. Do not create a second constants module.

### `app/services/eval_policy.py` (new, leaf — stdlib only, no imports at all)

```python
"""Shared policy constants of the evaluation / improvement loop (phase-9 DESIGN §D).

A dependency-free leaf: it imports nothing, so BOTH layers that need these values may have them.
That is the whole reason it exists. `app.services.chat.weak_queries` classifies live chat rows with
the bands and `app.services.proposals` turns a diagnosed cause into a proposal kind, while
`app.eval.taxonomy.classify_failure` classifies eval rows with the same band and the same mapping —
and the import-linter contract "app.services imports only app.models and app.config"
(`apps/api/pyproject.toml`) forbids `app.services` from importing `app.eval`, while the reverse
direction (`app.eval` -> `app.services`) is the declared-legal one (DESIGN §B1). So the constants
live at the bottom, in `app.services`, and `app.eval.taxonomy` imports them up — rather than each
layer re-typing `0.15` and drifting apart, which is exactly what task 06's own comment warned
against.

Deliberately NOT `Settings` fields (CONVENTIONS.md §5): these are definitions, not deployment
knobs. An operator who retuned the near-miss band per environment would change what "near miss"
MEANS between a recorded eval run and the weak-query report read off the same rows.
"""

from __future__ import annotations

# DESIGN §D: a refusal whose best chunk scored within this much of `similarity_threshold` is a
# `near_miss` ("the corpus almost had it"), not a `refused` ("nothing close exists"). Also row 5 of
# `app.eval.taxonomy.classify_failure`'s decision table (`corpus_gap` vs `threshold_refusal`) — the
# same boundary, by construction, because it is the same number.
NEAR_MISS_BAND: float = 0.15

# DESIGN §D: an answer that DID clear the threshold, but only just (`< threshold +
# LOW_CONFIDENCE_BAND`), is a `low_confidence` weak query — the class that makes "a bad answer is
# undetectable" (DESIGN's "Where we actually stand" table) false. Not a taxonomy input: the eval
# harness judges answers directly instead of guessing from retrieval scores.
LOW_CONFIDENCE_BAND: float = 0.10

# DESIGN "Diagnosis" row: the failure taxonomy maps 1:1 onto `content_proposals.kind`, so this
# mapping is the seam between a diagnosed eval failure (`app.eval.taxonomy.classify_failure`) and
# the proposal that fixes it (`app.services.proposals.kind_for_cause`, task 16) — two layers that
# cannot import each other, which is why it sits here. Keys are written as literals rather than
# importing `app.eval.taxonomy`'s cause constants (the same contract that put this module here
# forbids that import); `tests/test_failure_taxonomy.py`'s existing
# `set(PROPOSAL_KIND_BY_CAUSE) == set(FAILURE_CAUSES)` pin (line 104) is what keeps the two from
# drifting. `judge_disagreement` maps to `None`: the fix is judge calibration (task 08), not
# content.
PROPOSAL_KIND_BY_CAUSE: dict[str, str | None] = {
    "retrieval_miss": "retune",
    "corpus_gap": "new_article",
    "threshold_refusal": "retune",
    "generation_unfaithful": "expand_article",
    "judge_disagreement": None,
}

#: `content_proposals.kind`'s CHECK constraint, in Python (DESIGN §D / `app.models.eval`) — used by
#: task 16's `propose_content_fix` to reject a bad kind before the DB does.
PROPOSAL_KINDS: tuple[str, ...] = ("new_article", "expand_article", "retune")

#: `content_proposals.status`'s CHECK constraint, in Python.
PROPOSAL_STATUSES: tuple[str, ...] = ("proposed", "accepted", "rejected")
```

### `app/eval/taxonomy.py` change (exactly this, nothing else)

1. Delete the `NEAR_MISS_BAND: float = 0.15` definition (lines 32-34) **and** the
   `PROPOSAL_KIND_BY_CAUSE` dict literal (lines 36-44), and add with the other imports:

```python
from app.services.eval_policy import NEAR_MISS_BAND, PROPOSAL_KIND_BY_CAUSE
```

2. Keep both explaining comments, reworded to point at the new home, e.g.:

```python
# DESIGN §D: the near-miss band and the cause -> proposal-kind mapping are both shared with
# `app.services` (weak-query classification, task 15; `app.services.proposals`, task 16) and
# therefore live in `app.services.eval_policy` — the import-linter contract lets `app.eval` import
# `app.services` but not the reverse, so they live at the bottom and are imported up. Re-exported
# from this module (see `__all__`) so `from app.eval.taxonomy import NEAR_MISS_BAND,
# PROPOSAL_KIND_BY_CAUSE` (task 06's own tests) keeps working.
```

3. Add an explicit `__all__` right after the imports — `classify_failure` still *uses*
   `NEAR_MISS_BAND`, but nothing here uses the mapping, so without this ruff `F401` would flag the
   import rather than seeing a deliberate re-export:

```python
__all__ = [
    "CORPUS_GAP",
    "FAILURE_CAUSES",
    "GENERATION_UNFAITHFUL",
    "JUDGE_DISAGREEMENT",
    "NEAR_MISS_BAND",
    "PROPOSAL_KIND_BY_CAUSE",
    "RETRIEVAL_MISS",
    "THRESHOLD_REFUSAL",
    "ClassifiableRow",
    "classify_failure",
    "failure_distribution",
]
```

`classify_failure`, `failure_distribution`, `FAILURE_CAUSES` and the five cause constants are
otherwise untouched — every name `tests/test_failure_taxonomy.py` imports is still importable from
`app.eval.taxonomy`, and that file must pass **unedited**.

### `app/services/chat.py` — the pairing extraction (`content_gaps` stays frozen)

```python
@dataclass(frozen=True)
class _PairedTurn:
    """One user question joined to its next assistant reply, with that reply's outcome columns.

    Private: the ONE shape both `content_gaps` (PRD §6, frozen) and `weak_queries` (phase-9
    DESIGN §D) read the §6 pairing through. Adding a consumer must not re-derive the join.
    """

    question: str
    asked_at: datetime
    session_id: uuid.UUID
    retrieval_found: bool | None
    top_similarity: float | None
    feedback: int | None


def _paired_turns(
    session: Session, *, days: int, limit: int, uncovered_only: bool
) -> list[_PairedTurn]:
    """The §6 user↔reply pairing, newest question first, at most `limit` rows.

    Args:
        session: the caller's `Session`.
        days: window on the USER row's `created_at` (the question's `asked_at`), per §6.
        limit: SQL `LIMIT` on ROWS (not groups) — applied in SQL, before any Python filtering,
            so a caller that filters afterwards must pass a limit that accounts for it.
        uncovered_only: `True` adds `reply.retrieval_found.is_(False)` to the join (the §6 gap
            definition); `False` returns every paired turn in the window whatever its outcome.
    """
```

The body is today's `content_gaps` query verbatim — same `aliased(ChatMessage)` pair, same
correlated `func.min(reply_msg.created_at)` scalar subquery with `.correlate(user_msg)`, same
`and_(...)` join condition, same `user_msg.created_at >= cutoff`, same
`.order_by(user_msg.created_at.desc()).limit(limit)` — with exactly two differences:

1. the `select(...)` entity list grows `reply_msg.retrieval_found`, `reply_msg.top_similarity`,
   `reply_msg.feedback`;
2. `reply_msg.retrieval_found.is_(False)` is applied **only when `uncovered_only` is `True`**
   (`if uncovered_only: stmt = stmt.where(...)`).

Move the existing explaining docstring prose about the pairing/NULL/`days` semantics onto
`_paired_turns`, and leave `content_gaps`' own docstring pointing at it — the §6 normative text
must still be findable from `content_gaps`.

```python
def content_gaps(session: Session, *, days: int = 30, limit: int = 20) -> list[GapRow]:
    """`report_content_gaps`'s query (PRD §6, normative) — unchanged behaviour, one line thick.

    A wrapper over `_paired_turns(..., uncovered_only=True)` since phase-9 task 15: the pairing it
    used to own inline is now shared with `weak_queries` (DESIGN §D). Signature, ordering, window
    and result rows are byte-identical to phase 7's — `tests/test_content_gaps.py`'s 12 tests and
    `mcp-tools.json` are the proof and must not move.
    """
    return [
        GapRow(question=turn.question, asked_at=turn.asked_at, session_id=turn.session_id)
        for turn in _paired_turns(session, days=days, limit=limit, uncovered_only=True)
    ]
```

### `app/services/chat.py` — `weak_queries`

```python
NEGATIVE_FEEDBACK = "negative_feedback"
REFUSED = "refused"
NEAR_MISS = "near_miss"
LOW_CONFIDENCE = "low_confidence"

#: Canonical order: the classification ladder itself (DESIGN §D, first match wins). Also the order
#: `WeakQueryGroup.kinds` lists the distinct kinds it saw, so two reports of the same group are
#: textually comparable.
WEAK_QUERY_KINDS: tuple[str, ...] = (NEGATIVE_FEEDBACK, REFUSED, NEAR_MISS, LOW_CONFIDENCE)

#: Hard ceiling on ROWS `weak_queries` pulls out of SQL before grouping. Grouping and
#: classification happen in Python (the `feedback`/band ladder is not expressible as one portable
#: GROUP BY over a correlated join), so `limit` cannot be pushed down: it caps GROUPS. This caps
#: the scan instead — orders of magnitude above this app's real 30-day volume (a single demo
#: session is tens of turns), and it keeps one pathological window from pulling the whole
#: `chat_messages` table into memory.
_WEAK_QUERY_SCAN_LIMIT = 2000


@dataclass(frozen=True)
class WeakQueryExample:
    """One concrete turn behind a `WeakQueryGroup` — verbatim text, for the report/slide."""

    question: str
    kind: str
    top_similarity: float | None
    created_at: datetime


@dataclass(frozen=True)
class WeakQueryGroup:
    """One normalised question and every weak turn that asked it (DESIGN §D)."""

    normalized: str
    count: int
    kinds: list[str]                    # distinct, in `WEAK_QUERY_KINDS` order
    worst_top_similarity: float | None   # min over non-None similarities; None iff all were None
    examples: list[WeakQueryExample]     # at most 3, newest `created_at` first


def weak_queries(
    session: Session, *, days: int = 30, limit: int = 20, threshold: float
) -> list[WeakQueryGroup]:
    """Client questions the system answered badly — not just the ones it refused (DESIGN §D).

    Every paired turn in the window is classified, FIRST MATCH WINS:

    | # | Kind | Condition |
    |---|---|---|
    | 1 | `negative_feedback` | `feedback == -1` — a human said so; it outranks every inferred signal |
    | 2 | `refused` | not found, and (`top_similarity is None` or `< threshold - NEAR_MISS_BAND`) |
    | 3 | `near_miss` | not found, and `top_similarity >= threshold - NEAR_MISS_BAND` |
    | 4 | `low_confidence` | found, and `top_similarity < threshold + LOW_CONFIDENCE_BAND` |

    Anything else is not weak and is dropped. "found" means `retrieval_found is True` and "not
    found" means `retrieval_found is False` — a NULL `retrieval_found` (a pre-0009 row, whose
    outcome was never recorded) satisfies NEITHER, so such a row is weak only through rule 1. That
    mirrors `content_gaps`' deliberate `.is_(False)`-not-`.isnot(True)` choice: NULL is never read
    as "uncovered".

    Turns are then grouped by normalised text (casefold, collapse whitespace, strip trailing
    `?`/`!`/`.`), ordered `count` desc, then `worst_top_similarity` asc (a group whose worst
    similarity is `None` sorts FIRST within its count — nothing was retrieved at all, which is as
    weak as it gets), then `normalized` asc as a deterministic final tiebreaker.

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first; reads only).
        days: window on when the question was ASKED (same rule as `content_gaps`).
        limit: maximum number of GROUPS returned (not rows — see `_WEAK_QUERY_SCAN_LIMIT`).
        threshold: the retrieval similarity threshold the answers were served under —
            `Settings.similarity_threshold`, passed in by the caller. Keyword-only with NO
            default: a band is meaningless against a guessed threshold, and `app.services` must
            not reach for `Settings` on its own (the MCP tool layer owns that wiring).

    Returns:
        `WeakQueryGroup`s, at most `limit` of them, in the order described above.
    """
```

Implementation notes (all behaviour is pinned by the tests below):

- `_normalize_question(text)` = `" ".join(text.split()).casefold().rstrip("?!. ")` — one private
  helper, docstringed with the DESIGN §D rule it implements.
- `_classify_turn(turn, *, threshold) -> str | None` — the ladder above, one `return` per row,
  each commented with its table row number (mirrors `app.eval.taxonomy.classify_failure`'s style).
- `weak_queries` calls `_paired_turns(session, days=days, limit=_WEAK_QUERY_SCAN_LIMIT,
  uncovered_only=False)`, classifies, buckets into a `dict[str, list[tuple[_PairedTurn, str]]]`
  (insertion order = newest first, because the SQL is newest-first — so `examples` needs no
  re-sort, only a `[:3]` slice; say so in a comment rather than relying on it silently).
- Sorting key: `(-count, worst if worst is not None else -1.0, normalized)`.

### `app/mcp/tools_gaps.py` — the tenth tool

Registered by **extending the existing `GAPS_TOOLS` tuple** (not a new module): this tool is the
same "what did clients ask that went badly" family, `GAPS_TOOLS` is already collected into
`app.mcp.runtime._ALL_TOOLS`, and appending there keeps `runtime.py` untouched and the
`mcp-tools.json` diff purely additive (entries are emitted in `_ALL_TOOLS` order). Update the
module docstring's first line (it currently says "the ninth MCP tool").

```python
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
```

> **Fact the tool test depends on:** `Settings` declares no `env_file`
> (`apps/api/app/config.py:28` — plain `BaseSettings`), so `Settings()` reads the **process
> environment only** and never the repo's `.env`. Under the §Global Constraints gate command (only
> `TEST_DATABASE_URL` exported) `similarity_threshold` is therefore deterministically `0.5`, which
> is what `test_report_weak_queries_tool_returns_classified_groups` asserts. Do not "fix" that
> test by injecting a threshold argument into the tool.

Tool description (verbatim — it ships in `mcp-tools.json` and is the model's only view of this):

```
"Report client questions the system answered BADLY, grouped and classified: negative_feedback "
"(a client pressed thumbs-down), refused (nothing in the corpus was close), near_miss (a source "
"was just under the retrieval threshold — the corpus nearly had it), low_confidence (answered, "
"but only just above the threshold). Newest `days` days, most-asked first. Use this to decide "
"what content to write or expand next."
```

### `app/agent/loop.py` — awareness (one clause)

Append to `SYSTEM_PROMPT`, after the topics/tags sentence:

```python
"To find out what clients asked that the content handled badly, call report_weak_queries "
"(grouped and classified by why each was weak) or report_content_gaps (plain refusals)."
```

Add a numbered bullet 6 to the intent comment above `SYSTEM_PROMPT` recording **why this is not a
repeat of the removed clause**: the final-review fix at lines 71-74 deleted a gaps promise because
`report_content_gaps` was not registered at that HEAD and the sentence was therefore a capability
lie. Both tools are registered now (`_ALL_TOOLS` via `GAPS_TOOLS`), so the sentence is true —
state that, and state that truth is the condition for ever re-adding it.

## Steps (TDD)

- [ ] **RED — test-author.** Create `apps/api/tests/test_weak_queries.py`:

```python
"""`weak_queries` + `report_weak_queries` pins (phase-9 task-15, DESIGN §D).

Seeding mirrors `tests/test_content_gaps.py`'s helpers: every `chat_messages` row gets an EXPLICIT
`created_at`, so the §6 "next assistant reply by created_at" pairing and the `days` window are
both deterministic instead of racing the server clock. Each question gets its OWN `ChatSession`
unless a test is specifically about several turns in one session, so "next reply" is never
ambiguous.

`top_similarity` is Postgres `REAL` (single precision): a stored `0.4` reads back as
`0.4000000059604645`, so every similarity assertion uses `pytest.approx` and no boundary VALUE is
asserted exactly (the band boundaries 0.35 / 0.60 are approached with 0.30/0.40 and 0.55/0.80).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.agent.loop import SYSTEM_PROMPT
from app.mcp.runtime import call_tool, list_tool_schemas
from app.models import ChatMessage, ChatSession, User
from app.services.chat import (
    LOW_CONFIDENCE,
    NEAR_MISS,
    NEGATIVE_FEEDBACK,
    REFUSED,
    WEAK_QUERY_KINDS,
    content_gaps,
    weak_queries,
)
from app.services.errors import ToolInputError
from app.services.eval_policy import (
    LOW_CONFIDENCE_BAND,
    NEAR_MISS_BAND,
    PROPOSAL_KIND_BY_CAUSE,
    PROPOSAL_KINDS,
    PROPOSAL_STATUSES,
)

_THRESHOLD = 0.5


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` `call_tool` takes (PRD §4.1)."""
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


def _ask(
    session: Session,
    question: str,
    *,
    found: bool | None,
    top_similarity: float | None,
    feedback: int | None = None,
    ago: timedelta = timedelta(minutes=1),
) -> ChatSession:
    """Seed one user question + its next assistant reply, asked `ago` before now."""
    chat_session = ChatSession()
    session.add(chat_session)
    session.flush()
    asked_at = datetime.now(UTC) - ago
    session.add(
        ChatMessage(
            session_id=chat_session.id, role="user", content=question, created_at=asked_at
        )
    )
    session.add(
        ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content="reply",
            created_at=asked_at + timedelta(seconds=1),
            citations=[],
            retrieval_found=found,
            top_similarity=top_similarity,
            feedback=feedback,
        )
    )
    session.flush()
    return chat_session


# ---------------------------------------------------------------------------
# The shared constants (the import-linter ruling, Interfaces)
# ---------------------------------------------------------------------------


def test_the_shared_loop_constants_live_in_one_place_and_the_taxonomy_re_exports_them() -> None:
    """`app.eval.taxonomy` must not own a second copy of the near-miss band or the cause -> kind
    mapping: `app.services` may not import `app.eval` (import-linter), so both live in the leaf and
    the taxonomy imports them up — the same objects, not equal ones. The old import path keeps
    working, which is what leaves task 06's tests untouched."""
    from app.eval import taxonomy

    assert NEAR_MISS_BAND == pytest.approx(0.15)
    assert LOW_CONFIDENCE_BAND == pytest.approx(0.10)
    assert taxonomy.NEAR_MISS_BAND is NEAR_MISS_BAND
    assert taxonomy.PROPOSAL_KIND_BY_CAUSE is PROPOSAL_KIND_BY_CAUSE
    # The literal-keys-in-the-leaf choice is only safe because the taxonomy's own pin
    # (`tests/test_failure_taxonomy.py:104`) compares this key set to `FAILURE_CAUSES`.
    assert set(PROPOSAL_KIND_BY_CAUSE) == set(taxonomy.FAILURE_CAUSES)
    assert PROPOSAL_KINDS == ("new_article", "expand_article", "retune")
    assert PROPOSAL_STATUSES == ("proposed", "accepted", "rejected")


def test_weak_query_kinds_is_the_classification_ladder_in_order() -> None:
    assert WEAK_QUERY_KINDS == (NEGATIVE_FEEDBACK, REFUSED, NEAR_MISS, LOW_CONFIDENCE)


# ---------------------------------------------------------------------------
# Classification — one test per rung, plus the precedence
# ---------------------------------------------------------------------------


def test_thumbs_down_outranks_every_inferred_signal(db_session: Session) -> None:
    """Rule 1 beats rule 4: a well-grounded, high-similarity answer a human disliked is
    `negative_feedback`, never `low_confidence`/not-weak."""
    _ask(db_session, "Was this answer any good?", found=True, top_similarity=0.92, feedback=-1)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.kinds for group in groups] == [[NEGATIVE_FEEDBACK]]


def test_thumbs_down_on_a_refusal_is_still_negative_feedback(db_session: Session) -> None:
    """Rule 1 beats rule 2 as well — first match wins, and the human signal is first."""
    _ask(db_session, "Do you cover crypto comp?", found=False, top_similarity=0.2, feedback=-1)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEGATIVE_FEEDBACK]


def test_thumbs_up_is_not_a_weak_query(db_session: Session) -> None:
    _ask(db_session, "Great answer?", found=True, top_similarity=0.9, feedback=1)

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


def test_refusal_with_nothing_close_is_refused(db_session: Session) -> None:
    """Rule 2: 0.30 is below `threshold - NEAR_MISS_BAND` (0.35)."""
    _ask(db_session, "What about QSBS?", found=False, top_similarity=0.30)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [REFUSED]
    assert groups[0].worst_top_similarity == pytest.approx(0.30, abs=1e-6)


def test_refusal_with_no_similarity_at_all_is_refused(db_session: Session) -> None:
    """Rule 2's `None` half — an empty index reports no similarity."""
    _ask(db_session, "Anything on divorce and options?", found=False, top_similarity=None)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [REFUSED]
    assert groups[0].worst_top_similarity is None


def test_refusal_inside_the_band_is_a_near_miss(db_session: Session) -> None:
    """Rule 3 — demo beat 3: the corpus ALMOST had it, and the report says by how much."""
    _ask(db_session, "Do RSUs work differently outside the US?", found=False, top_similarity=0.40)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]
    assert groups[0].worst_top_similarity == pytest.approx(0.40, abs=1e-6)


def test_answered_just_above_the_threshold_is_low_confidence(db_session: Session) -> None:
    """Rule 4: 0.55 cleared 0.5 but not `threshold + LOW_CONFIDENCE_BAND` (0.60)."""
    _ask(db_session, "How is my ESPP discount taxed?", found=True, top_similarity=0.55)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [LOW_CONFIDENCE]


def test_a_confidently_answered_question_is_not_weak(db_session: Session) -> None:
    _ask(db_session, "When do my RSUs vest?", found=True, top_similarity=0.80)

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


def test_a_row_with_no_recorded_outcome_is_weak_only_through_feedback(
    db_session: Session,
) -> None:
    """A NULL `retrieval_found` (pre-0009 row) is neither found nor not-found — the same
    deliberate NULL handling `content_gaps` documents. Without feedback it is not weak; with a
    thumbs-down it is."""
    _ask(db_session, "An old untracked turn", found=None, top_similarity=None)
    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []

    _ask(db_session, "An old disliked turn", found=None, top_similarity=None, feedback=-1)
    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.normalized for group in groups] == ["an old disliked turn"]


def test_a_question_with_no_reply_at_all_is_never_weak(db_session: Session) -> None:
    """Same §6 pairing rule `content_gaps` relies on: no following assistant row, no row."""
    chat_session = ChatSession()
    db_session.add(chat_session)
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=chat_session.id,
            role="user",
            content="Nobody answered me",
            created_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


# ---------------------------------------------------------------------------
# Grouping, ordering, limits, window
# ---------------------------------------------------------------------------


def test_grouping_folds_case_whitespace_and_trailing_punctuation(db_session: Session) -> None:
    _ask(db_session, "What about QSBS?", found=False, top_similarity=0.30, ago=timedelta(hours=3))
    _ask(db_session, "what about   qsbs", found=False, top_similarity=0.40, ago=timedelta(hours=2))
    _ask(db_session, "What about QSBS!!", found=True, top_similarity=0.55, ago=timedelta(hours=1))

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert len(groups) == 1
    group = groups[0]
    assert group.normalized == "what about qsbs"
    assert group.count == 3
    assert group.kinds == [REFUSED, NEAR_MISS, LOW_CONFIDENCE]
    assert group.worst_top_similarity == pytest.approx(0.30, abs=1e-6)
    assert [example.question for example in group.examples] == [
        "What about QSBS!!",
        "what about   qsbs",
        "What about QSBS?",
    ]
    assert [example.kind for example in group.examples] == [LOW_CONFIDENCE, NEAR_MISS, REFUSED]


def test_examples_are_capped_at_three_newest_first(db_session: Session) -> None:
    for hours in (1, 2, 3, 4):
        _ask(
            db_session,
            "Crypto comp?",
            found=False,
            top_similarity=0.2,
            ago=timedelta(hours=hours),
        )

    group = weak_queries(db_session, days=30, threshold=_THRESHOLD)[0]

    assert group.count == 4
    assert len(group.examples) == 3
    timestamps = [example.created_at for example in group.examples]
    assert timestamps == sorted(timestamps, reverse=True)


def test_groups_are_ordered_by_count_then_by_worst_similarity(db_session: Session) -> None:
    # Two asks of the same question -> highest count, listed first.
    _ask(db_session, "Mega backdoor Roth?", found=True, top_similarity=0.58, ago=timedelta(hours=5))
    _ask(db_session, "Mega backdoor Roth?", found=True, top_similarity=0.57, ago=timedelta(hours=4))
    # Single asks: the lower worst-similarity sorts first.
    _ask(db_session, "Crypto comp?", found=False, top_similarity=0.41, ago=timedelta(hours=3))
    _ask(db_session, "QSBS?", found=False, top_similarity=0.22, ago=timedelta(hours=2))
    # No similarity at all sorts first of the single asks — nothing was retrieved.
    _ask(db_session, "401k loan on employer stock?", found=False, top_similarity=None, ago=timedelta(hours=1))

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.normalized for group in groups] == [
        "mega backdoor roth",
        "401k loan on employer stock",
        "qsbs",
        "crypto comp",
    ]


def test_limit_caps_groups_not_rows(db_session: Session) -> None:
    _ask(db_session, "QSBS?", found=False, top_similarity=0.2, ago=timedelta(hours=4))
    _ask(db_session, "QSBS?", found=False, top_similarity=0.2, ago=timedelta(hours=3))
    _ask(db_session, "Crypto comp?", found=False, top_similarity=0.3, ago=timedelta(hours=2))
    _ask(db_session, "Divorce and options?", found=False, top_similarity=0.4, ago=timedelta(hours=1))

    groups = weak_queries(db_session, days=30, limit=2, threshold=_THRESHOLD)

    assert len(groups) == 2
    assert groups[0].normalized == "qsbs"
    assert groups[0].count == 2


def test_the_days_window_reads_on_when_the_question_was_asked(db_session: Session) -> None:
    _ask(db_session, "Old question?", found=False, top_similarity=0.2, ago=timedelta(days=40))
    _ask(db_session, "Recent question?", found=False, top_similarity=0.2, ago=timedelta(days=3))

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.normalized for group in groups] == ["recent question"]


def test_a_higher_threshold_moves_rows_up_the_ladder(db_session: Session) -> None:
    """The threshold is an argument, not a constant: the same 0.40 refusal that is a `near_miss`
    at 0.5 is a plain `refused` at 0.6 (0.40 < 0.6 - 0.15)."""
    _ask(db_session, "Non-US RSUs?", found=False, top_similarity=0.40)

    assert weak_queries(db_session, days=30, threshold=0.5)[0].kinds == [NEAR_MISS]
    assert weak_queries(db_session, days=30, threshold=0.6)[0].kinds == [REFUSED]


# ---------------------------------------------------------------------------
# `content_gaps` stayed frozen (its own 12 tests are the real guard)
# ---------------------------------------------------------------------------


def test_content_gaps_still_sees_only_uncovered_turns_after_the_extraction(
    db_session: Session,
) -> None:
    _ask(db_session, "Refused one?", found=False, top_similarity=0.2, ago=timedelta(hours=2))
    _ask(db_session, "Answered one?", found=True, top_similarity=0.55, ago=timedelta(hours=1))

    gaps = content_gaps(db_session, days=30, limit=20)

    assert [gap.question for gap in gaps] == ["Refused one?"]
    # ...while the weak-query report sees BOTH, which is the point of this task.
    assert len(weak_queries(db_session, days=30, threshold=_THRESHOLD)) == 2


# ---------------------------------------------------------------------------
# The MCP tool
# ---------------------------------------------------------------------------


def test_report_weak_queries_tool_returns_classified_groups(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Happy path through `call_tool`, with the default `Settings.similarity_threshold` (0.5):
    JSON-able payload, ISO `asked_at`, the threshold it classified against."""
    _ask(db_session, "Non-US RSUs?", found=False, top_similarity=0.40)

    result = call_tool("report_weak_queries", {}, session=db_session, actor_id=actor_id)

    assert result["count"] == 1
    assert result["threshold"] == pytest.approx(0.5)
    group = result["weak_queries"][0]
    assert group["normalized_question"] == "non-us rsus"
    assert group["count"] == 1
    assert group["kinds"] == [NEAR_MISS]
    assert group["worst_top_similarity"] == pytest.approx(0.40, abs=1e-6)
    example = group["examples"][0]
    assert example["question"] == "Non-US RSUs?"
    assert example["kind"] == NEAR_MISS
    assert isinstance(example["asked_at"], str)
    datetime.fromisoformat(example["asked_at"])


def test_report_weak_queries_tool_rejects_bad_arguments(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """§9 floor, same as `report_content_gaps`: a negative window and an unknown argument both
    fail as a named `ToolInputError` before the service is reached."""
    with pytest.raises(ToolInputError, match="days"):
        call_tool("report_weak_queries", {"days": 0}, session=db_session, actor_id=actor_id)
    with pytest.raises(ToolInputError, match="threshold"):
        call_tool(
            "report_weak_queries", {"threshold": 0.9}, session=db_session, actor_id=actor_id
        )


def test_report_weak_queries_is_registered_with_a_description_and_schema() -> None:
    """Needs no DB: the registry is module state."""
    by_name = {entry["name"]: entry for entry in list_tool_schemas()}

    assert "report_weak_queries" in by_name
    assert "report_content_gaps" in by_name
    assert len(by_name) == 10
    entry = by_name["report_weak_queries"]
    assert "near_miss" in entry["description"]
    assert set(entry["inputSchema"]["properties"]) == {"days", "limit"}


def test_system_prompt_tells_the_agent_the_weak_query_report_exists() -> None:
    """Keyword-based, like `tests/test_agent_loop.py`'s own prompt pins — and true by
    construction now: the tool is registered (the clause the final review removed was a lie only
    because no such tool existed then)."""
    lower = SYSTEM_PROMPT.lower()

    assert "report_weak_queries" in lower
    assert "report_content_gaps" in lower
```

- [ ] **Run RED:**
  ```sh
  export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r')"
  cd apps/api && uv run pytest tests/test_weak_queries.py -q
  ```
  Expect collection to fail first on `ModuleNotFoundError: app.services.eval_policy` / `ImportError:
  cannot import name 'weak_queries' from 'app.services.chat'`. Paste the evidence into the
  test-author report.

- [ ] **GREEN — implementer, 1/4 (constants).** Create `app/services/eval_policy.py` with all five
  values; edit `app/eval/taxonomy.py` to import `NEAR_MISS_BAND` + `PROPOSAL_KIND_BY_CAUSE` from it,
  delete both local definitions, reword both comments and add the `__all__` (per Interfaces). Then,
  before anything else:
  `uv run lint-imports && uv run pytest tests/test_failure_taxonomy.py -q && uv run ruff check --no-cache .`
  — layering in both directions, task 06's tests green **unedited**, and `F401` clean on the
  re-export. This is the only task in the phase that touches `taxonomy.py`.

- [ ] **GREEN — implementer, 2/4 (the extraction).** Add `_PairedTurn`/`_paired_turns` to
  `app/services/chat.py`, move the pairing docstring prose onto it, and reduce `content_gaps` to
  the wrapper. Run `uv run pytest tests/test_content_gaps.py -q` **before writing `weak_queries`**
  — all 12 must still pass, untouched. If any fails, the extraction is wrong; do not edit that file.

- [ ] **GREEN — implementer, 3/4 (`weak_queries`).** Add the kind constants, `WeakQueryExample`,
  `WeakQueryGroup`, `_normalize_question`, `_classify_turn`, `weak_queries`.

- [ ] **GREEN — implementer, 4/4 (tool + prompt + baseline).** Extend `GAPS_TOOLS` with
  `report_weak_queries` (args model, handler, description verbatim from Interfaces), add the
  `SYSTEM_PROMPT` clause and its intent bullet, then regenerate the baseline and apply the five
  pre-authorized registry-pin edits:
  ```sh
  cd apps/api && uv run python scripts/export_mcp_tools.py && git diff --stat -- mcp-tools.json
  ```
  The diff must contain exactly one new entry (`report_weak_queries`, appended) and nothing else.

- [ ] **Run GREEN:** `uv run pytest tests/test_weak_queries.py tests/test_content_gaps.py
  tests/test_failure_taxonomy.py tests/test_agent_loop.py -q`, then the whole suite `uv run pytest -q`.

- [ ] **Gates:** `pnpm gates:api` (ruff, ruff format, mypy, **lint-imports**, pytest) clean.

- [ ] **Commit:**
  `git add apps/api/app apps/api/tests apps/api/mcp-tools.json`
  `git commit -m "feat(api): weak_queries + report_weak_queries MCP tool (p9 t15)"`

## Verify

```sh
export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r')"
cd apps/api
uv run pytest tests/test_weak_queries.py tests/test_content_gaps.py tests/test_failure_taxonomy.py -q
uv run lint-imports
uv run python scripts/export_mcp_tools.py && git diff --exit-code -- mcp-tools.json   # clean AFTER the commit
pnpm gates:api
```

## Acceptance

- `weak_queries` classifies exactly per the four-rung table, first match wins, including: a
  thumbs-down outranking a confident answer; `None` similarity counting as `refused`; a NULL
  `retrieval_found` being weak **only** through feedback.
- Grouping folds case, internal whitespace and trailing `?`/`!`/`.`; `count` counts rows,
  `kinds` is distinct in ladder order, `worst_top_similarity` is the minimum (or `None`),
  `examples` is ≤ 3 newest-first; ordering is count desc → worst similarity asc (`None` first) →
  normalized asc; `limit` caps groups.
- `content_gaps`' 12 tests pass **untouched**; its signature, ordering and rows are unchanged;
  the `report_content_gaps` entry in `mcp-tools.json` is byte-identical; PRD §6 is not edited.
- `0.15` appears exactly once in the codebase as a near-miss band, and the cause → proposal-kind
  mapping exactly once, both in `app/services/eval_policy.py`;
  `app.eval.taxonomy.NEAR_MISS_BAND`/`.PROPOSAL_KIND_BY_CAUSE` **are** those same objects (identity,
  not equality); `uv run lint-imports` is green and no contract in `pyproject.toml` was edited.
- **`tests/test_failure_taxonomy.py` (task 06) passes green and unedited** — every name it imports
  is still importable from `app.eval.taxonomy`, and its
  `set(PROPOSAL_KIND_BY_CAUSE) == set(FAILURE_CAUSES)` pin still holds across the new layer
  boundary. `app/eval/taxonomy.py` carries an `__all__` so both re-exports are deliberate (and
  ruff-clean).
- `report_weak_queries` is the tenth registered tool, takes only `days`/`limit`, reads
  `Settings.similarity_threshold` itself, and returns JSON-able values only.
- `mcp-tools.json` regenerated in the same commit; the five registry-inventory pins updated
  exactly as listed, with no other pre-existing test touched.
- `SYSTEM_PROMPT` names both report tools, and the implementer report restates the
  "capability-lie" history (why re-adding this clause is correct now).

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-15-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-15-implementer.md` — must
  restate the shared-constants placement ruling (both constants, one move, task 16 only imports),
  confirm `lint-imports` green without any contract edit and `tests/test_failure_taxonomy.py` green
  unedited, plus the exact `mcp-tools.json` diff stat.
