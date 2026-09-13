"""Content proposals: the record that closes the eval loop (phase-9 DESIGN §D).

Session-first plain functions (CONVENTIONS.md §3) — flush, never commit. The one thing this module
exists to enforce is `accept_proposal`'s gate: "validated before acceptance" is a DATA
PRECONDITION, not a synchronous harness run (a run takes minutes; no MCP step budget allows one).
A proposal may only become `accepted` when two persisted eval runs say so.

Ruling A (task-16 brief): the cause -> proposal-kind mapping, and the two CHECK-constraint value
sets, are IMPORTED from `app.services.eval_policy` (task 15 already moved them there so both
`app.services` and `app.eval` — which may not import each other — can share one definition). This
module re-types neither the five cause names nor the three kinds.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ContentProposal, EvalResult, EvalRun
from app.services.content import archive_content, create_draft, get_content
from app.services.errors import ConflictError, NotFoundError
from app.services.eval_policy import PROPOSAL_KIND_BY_CAUSE, PROPOSAL_KINDS, PROPOSAL_STATUSES
from app.services.eval_runs import compare_runs, latest_runs
from app.services.lifecycle import ChunkPipeline

# Behaviour pin (task-16 brief): the draft body stub is deterministic and names the gap it exists
# to close. `{questions}` is built by `_format_questions` below, one bullet per evidence row.
_DRAFT_BODY_TEMPLATE = (
    "# {title}\n\n"
    "> Proposed content fix — drafted by AdvisorDesk's eval loop, not yet written.\n\n"
    "{rationale}\n\n"
    "## Weak queries this should answer\n\n"
    "{questions}\n"
)


@dataclass(frozen=True)
class AcceptanceCheck:
    """Why `accept_proposal` would (not) accept — the gate's own explanation, for reports/slides.

    `blocked_by` is `None` when the proposal is acceptable, else the name of the first gate (in
    evaluation order) that failed: one of `"no_before_run"`, `"missing_before_run"`,
    `"incomplete_before_run"`, `"missing_after_run"`, `"after_run_wrong_kind"`,
    `"after_run_not_newer"`, `"corpus_unchanged"`, `"pct_dropped"`, `"draft_not_published"`,
    `"after_run_predates_publication"`, `"incomplete_after_run"`, `"regressions"`.

    Fix round 1 (reviewer C1): `missing_questions` names the before-run questions the after-run
    did not measure (`app.services.eval_runs.RunDiff.removed`) — populated only for
    `blocked_by="incomplete_after_run"`, `[]` otherwise. Mirrors `regressions`' own shape: both
    exist so `accept_proposal` can name specific questions in its refusal message without a
    second `compare_runs` call.

    Observation carried forward (reviewer, fix round 1 review): `corpus_changed` is a claim about
    evaluation order, not about the world — every branch that returns before the digest is
    actually compared reports `corpus_changed=False`, even for `"after_run_not_newer"`,
    `"draft_not_published"` or `"after_run_predates_publication"`, where the digests might well
    differ. Read it as "corpus_changed, as far as this gate got", not "the corpus is unchanged".
    """

    before_id: uuid.UUID | None
    after_id: uuid.UUID | None
    corpus_changed: bool
    pct_before: float | None
    pct_after: float | None
    regressions: list[str]
    missing_questions: list[str]
    blocked_by: str | None


def _format_questions(evidence: Sequence[Mapping[str, object]]) -> str:
    """Render the draft stub's per-question bullet list (task-16 brief, verbatim shape).

    One line per evidence row: `- "<normalized_question>" (asked <count>x, <kinds>, closest
    similarity <worst_top_similarity or "none">)`. Reads every key via `.get()` — an evidence row
    is caller-supplied JSON, not a typed object — and the literal `- (no weak-query rows
    supplied)` when `evidence` is empty.
    """
    if not evidence:
        return "- (no weak-query rows supplied)"
    return "\n".join(_format_one_question(row) for row in evidence)


def _format_one_question(row: Mapping[str, object]) -> str:
    question = row.get("normalized_question", "unknown question")
    count = row.get("count", "?")
    kinds = row.get("kinds", [])
    if isinstance(kinds, list | tuple):
        kinds_text = ", ".join(str(kind) for kind in kinds) or "unclassified"
    else:
        kinds_text = str(kinds)
    similarity = row.get("worst_top_similarity")
    similarity_text = "none" if similarity is None else str(similarity)
    return f'- "{question}" (asked {count}x, {kinds_text}, closest similarity {similarity_text})'


def kind_for_cause(failure_cause: str) -> str:
    """Map a taxonomy failure cause onto the `content_proposals.kind` that fixes it.

    DESIGN "Diagnosis" row ("maps 1:1 onto proposal kinds"), via
    `app.services.eval_policy.PROPOSAL_KIND_BY_CAUSE`.

    Args:
        failure_cause: one of `PROPOSAL_KIND_BY_CAUSE`'s keys (the failure taxonomy's cause
            names — `app.eval.taxonomy.FAILURE_CAUSES`, imported up from this same mapping).

    Returns:
        The proposal `kind` that fixes `failure_cause`.

    Raises:
        ValueError: `failure_cause` is unknown, or is `judge_disagreement` — which maps to no
            proposal at all: a judge that disagrees with a human is fixed by calibration
            (task 08), and writing an article would be treating the symptom.
    """
    if failure_cause not in PROPOSAL_KIND_BY_CAUSE:
        raise ValueError(f"Unknown failure cause {failure_cause!r}.")
    kind = PROPOSAL_KIND_BY_CAUSE[failure_cause]
    if kind is None:
        raise ValueError(
            f"{failure_cause}: judge_disagreement is a judge-calibration problem, not a "
            "content gap — no proposal kind fixes it."
        )
    return kind


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

    Steps, in order: validate `kind` (before any write, so a bad kind touches the database not
    at all); `create_draft` the stub article through the existing content service, so it is an
    ordinary CMS draft with a server-generated slug, actor stamping and lifecycle rules,
    indistinguishable from a hand-made one; write the `ContentProposal` row, stamping the latest
    `"answer"` eval run as `eval_run_before_id` (or `None` — no baseline yet is not an error
    here, `accept_proposal` is where it becomes one); flush and return.

    `evidence` is the caller's weak-query rows (e.g. `report_weak_queries`'s `weak_queries`
    list), stored as a SNAPSHOT wrapped in one envelope — `{"weak_queries": [...],
    "captured_at": "<iso>"}` — not as FKs (chat rows are prunable; the blob is the artifact). A
    NEW list of NEW dicts is built so nothing later mutates a dict the caller still holds (plain
    JSONB, no `MutableDict`).

    `created_at` is stamped app-side (mirrors `app.services.eval_runs.record_run`'s own fix,
    fix round 1 C1 there): several proposals created within one open transaction would otherwise
    share Postgres' `now()` (the *transaction* timestamp), making `list_proposals`' `created_at
    DESC` order tie on an unrelated random UUID instead of on recency.

    Args:
        session: the caller's `Session`.
        kind: `new_article` | `expand_article` | `retune` — use `kind_for_cause` to derive it
            from a failure cause.
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
    if kind not in PROPOSAL_KINDS:
        raise ValueError(f"kind must be one of {PROPOSAL_KINDS}, got {kind!r}.")

    evidence_snapshot = [dict(row) for row in evidence]

    draft = create_draft(
        session,
        title=title,
        body_md=_DRAFT_BODY_TEMPLATE.format(
            title=title, rationale=rationale, questions=_format_questions(evidence_snapshot)
        ),
        tags=(),
        actor_id=actor_id,
    )

    baseline_runs = latest_runs(session, kind="answer", limit=1)
    before_id = baseline_runs[0].id if baseline_runs else None

    proposal = ContentProposal(
        created_at=datetime.now(UTC),
        kind=kind,
        title=title,
        rationale=rationale,
        evidence={
            "weak_queries": evidence_snapshot,
            "captured_at": datetime.now(UTC).isoformat(),
        },
        target_content_id=target_content_id,
        draft_content_id=draft.id,
        eval_run_before_id=before_id,
        created_by=actor_id,
    )
    session.add(proposal)
    session.flush()
    return proposal


def list_proposals(
    session: Session, *, status: str | None = None, limit: int = 50
) -> list[ContentProposal]:
    """Proposals newest-first (`created_at DESC, id DESC`), optionally filtered by `status`.

    Raises:
        ValueError: `status` is not one of `app.services.eval_policy.PROPOSAL_STATUSES` — a
            typo'd filter would otherwise return an empty list that reads like "no proposals",
            exactly the wrong answer to show on a stage.
    """
    if status is not None and status not in PROPOSAL_STATUSES:
        raise ValueError(f"status must be one of {PROPOSAL_STATUSES}, got {status!r}.")

    stmt = select(ContentProposal)
    if status is not None:
        stmt = stmt.where(ContentProposal.status == status)
    stmt = stmt.order_by(ContentProposal.created_at.desc(), ContentProposal.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def check_acceptance(
    session: Session, proposal: ContentProposal, after_id: uuid.UUID
) -> AcceptanceCheck:
    """Evaluate `accept_proposal`'s DATA gates without mutating anything, in order, so a caller
    (a human operator, or `accept_proposal` itself) can explain a refusal before committing to
    one. The FIRST failing gate stops evaluation; `blocked_by` names it (`None` when acceptable).

    Fix round 1 (reviewer M1): this covers the comparison gates only (2-8 in `accept_proposal`'s
    table) — it does not look at `proposal.status` at all, so calling it directly on an
    already-`accepted`/`rejected` proposal can return `blocked_by=None` ("the data supports it")
    even though `accept_proposal` would still refuse on `status` alone (gate 1, checked before
    `accept_proposal` ever calls this function). Read `blocked_by=None` from this function as "the
    DATA gates pass", not "accept_proposal would accept".

    Fix round 1 (reviewer M3): when `proposal.eval_run_before_id` names a run of `kind !=
    "answer"` (reachable only by hand-stamping that column — `propose_content_fix` always picks
    an answer run), this function does not check `before.kind` itself and instead lets
    `compare_runs`' own `ConflictError` ("Cannot compare a ... run to a ... run") propagate out of
    this function — a documented exception to "without mutating anything" (raising is not
    mutating).

    Fix round 2 (reviewer I3, owner ruling): when `proposal.draft_content_id` is set, the linked
    `Content` row must be `published` (fix wave C1: `status == "published"`, not merely
    `published_at is not None` — see the rung's own comment below) and the after-run's
    `corpus_max_updated_at` must be at or after that `published_at` — otherwise this run cannot
    show it measured a corpus containing THIS proposal's own fix, whatever else it shows. A
    proposal with no linked draft (nullable column; `propose_content_fix` always sets one today,
    but the column itself allows `None`) is exempt from both checks — there is no fix-specific
    publish event to compare against. This exemption is therefore RESERVED for a future
    drafting-free proposal kind that does not exist yet; today it is reachable only by
    hand-building a `ContentProposal` row directly (fix wave C4 pins the documented behaviour with
    exactly such a row, so a day this kind is added, a test — not silent drift — notices whether
    the exemption is still the intended reading).
    """
    before_id = proposal.eval_run_before_id
    if before_id is None:
        return AcceptanceCheck(
            before_id=None,
            after_id=None,
            corpus_changed=False,
            pct_before=None,
            pct_after=None,
            regressions=[],
            missing_questions=[],
            blocked_by="no_before_run",
        )

    before = session.get(EvalRun, before_id)
    if before is None:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=None,
            corpus_changed=False,
            pct_before=None,
            pct_after=None,
            regressions=[],
            missing_questions=[],
            blocked_by="missing_before_run",
        )

    # Fix round 2 (reviewer I2 — Important): `compare_runs`' verdict sets are computed over
    # QUESTIONS BOTH RUNS MEASURED, so a before-run with ZERO questions compares zero questions —
    # `diff.removed` is vacuously empty (nothing to be missing), `pct_fully_supported` is
    # vacuously `0.0` (so gate "pct not dropped" passes against anything), and `diff.regressions`
    # is vacuously `[]`. C1 closed this hole from the AFTER side (gate "incomplete_after_run"
    # below); this closes the identical hole from the BEFORE side. A distinct `blocked_by` (rather
    # than folding into "incomplete_after_run") because the operator's fix differs: an empty
    # BEFORE-run means the baseline itself is worthless (re-propose against a real baseline), an
    # incomplete AFTER-run means re-run the harness more broadly.
    #
    # Fix wave C3 (t16-rereview2 M8): `before.total_questions` is the run's own HEADER, written by
    # `record_run` in the same transaction as its `eval_results` rows — but nothing stops the two
    # from disagreeing on a hand-built or partially-restored row (unreachable through shipped
    # code; defence in depth after the source-side empty-questions guard in
    # `app.eval.groundedness.run_eval`). Requiring an actual `eval_results` row, not just a
    # nonzero header, closes that one layer down: a before-run whose header lies compares zero
    # questions against anything, exactly like an honestly-empty one.
    before_result_count = (
        session.scalar(
            select(func.count()).select_from(EvalResult).where(EvalResult.run_id == before_id)
        )
        or 0
    )
    if before.total_questions == 0 or before_result_count == 0:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=None,
            corpus_changed=False,
            pct_before=before.pct_fully_supported,
            pct_after=None,
            regressions=[],
            missing_questions=[],
            blocked_by="incomplete_before_run",
        )

    after = session.get(EvalRun, after_id)
    if after is None:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=None,
            corpus_changed=False,
            pct_before=before.pct_fully_supported,
            pct_after=None,
            regressions=[],
            missing_questions=[],
            blocked_by="missing_after_run",
        )

    if after.kind != "answer":
        return AcceptanceCheck(
            before_id=before_id,
            after_id=after_id,
            corpus_changed=False,
            pct_before=before.pct_fully_supported,
            pct_after=after.pct_fully_supported,
            regressions=[],
            missing_questions=[],
            blocked_by="after_run_wrong_kind",
        )

    # Fix round 1 (reviewer I1): a DIFFERENT corpus digest is not a LATER one. Without this,
    # any historical answer-run recorded when the corpus happened to look different qualifies as
    # "after" — and since `propose_content_fix` always stamps `before` as the LATEST answer run
    # at proposal time (`:178-179`), every other run already in the table is older than `before`,
    # making the entire run history a pool of candidate "after" runs. Checked before the digest/
    # pct/coverage/regression comparisons below: none of them can substitute for it (a stale run
    # can easily have a different digest and a higher pct than `before`, by coincidence of when
    # it happened to run).
    if after.created_at <= before.created_at:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=after_id,
            corpus_changed=False,
            pct_before=before.pct_fully_supported,
            pct_after=after.pct_fully_supported,
            regressions=[],
            missing_questions=[],
            blocked_by="after_run_not_newer",
        )

    corpus_changed = after.corpus_digest != before.corpus_digest
    if not corpus_changed:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=after_id,
            corpus_changed=False,
            pct_before=before.pct_fully_supported,
            pct_after=after.pct_fully_supported,
            regressions=[],
            missing_questions=[],
            blocked_by="corpus_unchanged",
        )

    if after.pct_fully_supported < before.pct_fully_supported:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=after_id,
            corpus_changed=True,
            pct_before=before.pct_fully_supported,
            pct_after=after.pct_fully_supported,
            regressions=[],
            missing_questions=[],
            blocked_by="pct_dropped",
        )

    # Fix round 2 (reviewer I3 — Important, owner ruling): nothing above ties the after-run to
    # THIS PROPOSAL'S OWN fix — a run whose digest moved and whose pct improved for an entirely
    # UNRELATED publish would pass every gate so far. Exempt when there is no linked draft (a
    # nullable column; always set by `propose_content_fix` today, but the check must not crash on
    # a future/hand-built proposal that has none).
    if proposal.draft_content_id is not None:
        try:
            draft = get_content(session, proposal.draft_content_id)
        except NotFoundError:
            draft = None
        # Fix wave C1 (t16-rereview2 I4): `published_at is not None` tests "was EVER published",
        # which an ARCHIVED draft still satisfies — `archive_content` never clears `published_at`
        # (by design: `publish_content` never overwrites it either, so the public feed's
        # `published_at DESC` order stays stable across a later re-publish of something else).
        # `status != "published"` tests "IS published now", which is what "this fix is live in
        # the corpus the after-run measured" actually requires; it implies `published_at is not
        # None` (nothing reaches `published` without being stamped), so this replaces rather than
        # supplements the previous check.
        if draft is None or draft.status != "published":
            return AcceptanceCheck(
                before_id=before_id,
                after_id=after_id,
                corpus_changed=False,
                pct_before=before.pct_fully_supported,
                pct_after=after.pct_fully_supported,
                regressions=[],
                missing_questions=[],
                blocked_by="draft_not_published",
            )
        # `status == "published"` implies `published_at is not None` — `publish_content` stamps
        # it on every draft/archived -> published transition and never clears it — but mypy
        # cannot infer that cross-column invariant from the `status` check above, hence the
        # assert (a real `None` here would be a `Content` model/service bug, not a caller error).
        assert draft.published_at is not None
        if after.corpus_max_updated_at is None or after.corpus_max_updated_at < draft.published_at:
            return AcceptanceCheck(
                before_id=before_id,
                after_id=after_id,
                corpus_changed=False,
                pct_before=before.pct_fully_supported,
                pct_after=after.pct_fully_supported,
                regressions=[],
                missing_questions=[],
                blocked_by="after_run_predates_publication",
            )

    diff = compare_runs(session, before_id, after_id)

    # Fix round 1 (reviewer C1 — CRITICAL): `compare_runs` can only find a regression in a
    # question BOTH runs measured, so the regression gate below passes VACUOUSLY on an empty
    # after-run and PARTIALLY on a truncated one (e.g. a narrowed `--questions <path>` re-run) —
    # neither the digest gate (only needs "different") nor the pct gate (computed over whatever
    # rows the after-run happens to contain, so a narrower run can score HIGHER, not lower) catch
    # this. `diff.removed` names exactly the before-run questions the after-run did not measure;
    # `after.total_questions < before.total_questions` is a cheap belt-and-braces check on data
    # already loaded (a genuine subset always leaves `diff.removed` non-empty too, given
    # `eval_results`' `(run_id, question)` uniqueness — this is defence in depth, not a distinct
    # scenario). This must run BEFORE the regressions check: an after-run that does not cover a
    # regressed question would otherwise make gate 8 non-vacuous only by accident.
    if diff.removed or after.total_questions < before.total_questions:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=after_id,
            corpus_changed=True,
            pct_before=before.pct_fully_supported,
            pct_after=after.pct_fully_supported,
            regressions=[],
            missing_questions=diff.removed,
            blocked_by="incomplete_after_run",
        )

    if diff.regressions:
        return AcceptanceCheck(
            before_id=before_id,
            after_id=after_id,
            corpus_changed=True,
            pct_before=before.pct_fully_supported,
            pct_after=after.pct_fully_supported,
            regressions=diff.regressions,
            missing_questions=[],
            blocked_by="regressions",
        )

    return AcceptanceCheck(
        before_id=before_id,
        after_id=after_id,
        corpus_changed=True,
        pct_before=before.pct_fully_supported,
        pct_after=after.pct_fully_supported,
        regressions=[],
        missing_questions=[],
        blocked_by=None,
    )


def accept_proposal(
    session: Session, proposal_id: uuid.UUID, *, eval_run_after_id: uuid.UUID
) -> ContentProposal:
    """Accept a proposal the DATA supports — the evidence behind "validated before acceptance".

    Gates 0-1 are proposal-level (existence, still-`proposed`) and are checked here directly;
    gates 2-11 are the data comparison and live entirely in `check_acceptance` — this function is
    a thin raiser on top of it, so one place owns the rules:

    | # | Gate | Raises |
    |---|---|---|
    | 0 | the proposal exists | `NotFoundError` |
    | 1 | its `status` is still `proposed` | `ConflictError` (idempotent re-accept is NOT
    |   |                                    | silently allowed — a second accept against a
    |   |                                    | different after-run would rewrite history) |
    | 2 | `eval_run_before_id` is set, and that run row exists | `ConflictError` / `NotFoundError` |
    | 3 | `before.total_questions != 0` AND ≥1 real `eval_results` row exists for it
    |   | (fix round 2 I2; fix wave C3/M8 closes the header-vs-rows gap one layer down) |
    |   | `ConflictError` |
    | 4 | `eval_run_after_id` names a run, of `kind="answer"` | `NotFoundError` / `ConflictError` |
    | 5 | `after.created_at > before.created_at` (fix round 1, I1) | `ConflictError` |
    | 6 | `after.corpus_digest != before.corpus_digest` | `ConflictError` |
    | 7 | `after.pct_fully_supported >= before.pct_fully_supported` | `ConflictError` |
    | 8 | the proposal's draft (if any) `status == "published"` (fix round 2, I3; fix wave C1
    |   | tightens "was ever published" to "is published now") | `ConflictError` |
    | 9 | the after-run's corpus postdates that publish (fix round 2, I3) | `ConflictError` |
    | 10 | the after-run covers every before-run question (fix round 1, C1) | `ConflictError`,
    |    |                                                                    | naming the count
    |    |                                                                    | and up to three
    |    |                                                                    | missing questions |
    | 11 | `compare_runs(before, after).regressions == []` | `ConflictError`, naming up to the
    |    |                                                   | first three regressed questions |

    Fix round 1 (reviewer C1, CRITICAL): gate 10 closes the hole where an after-run that does not
    measure a regressed question made gate 11 pass vacuously (an empty after-run) or partially (a
    narrowed re-run, e.g. a shipped `--questions <path>` CLI flag) — neither gate 6 nor gate 7
    would catch either case, since a narrower run is only ever compared against the rows it
    actually contains. Fix round 1 (reviewer I1, Important): gate 5 closes the hole where a
    historical answer-run older than `before` — a DIFFERENT digest is not a LATER digest — was
    accepted as "after" with no ordering check at all.

    Fix round 2 (reviewer I2, Important): gate 3 closes the identical vacuous-comparison hole
    from the BEFORE side — a zero-question before-run (reachable via a shipped `--questions
    <empty.yaml>` CLI flag; `app.eval.groundedness.run_eval` now also refuses to evaluate one at
    the source) compares zero questions against anything, passing every later gate for free.
    Fix round 2 (reviewer I3, Important, owner ruling): gates 8-9 close the hole where an
    UNRELATED publish (not this proposal's own fix) satisfied every earlier gate — "validated"
    must mean this run measured a corpus that contains THIS fix, not merely a corpus that changed
    for some other reason. Exempt when the proposal has no linked draft.

    Fix round 2 (reviewer M7, wording): the before-run is stamped at `propose_content_fix` time,
    not at publish time — any corpus change between propose and publish (an unrelated article, a
    second proposal) sits inside the comparison window gate 11 evaluates. A "regressed" question
    named in that gate's message is a question that regressed somewhere between the STAMPED
    before-run and the after-run, not necessarily because of THIS fix — the message below is
    worded to say exactly that, not to assert causation this gate cannot know.

    On success: `status = "accepted"`, `eval_run_after_id` stamped, `flush()`, return. Nothing is
    mutated on any refusal — every gate above is evaluated (via `check_acceptance`) BEFORE this
    function writes anything.
    """
    proposal = session.get(ContentProposal, proposal_id)
    if proposal is None:
        raise NotFoundError(f"No content proposal {proposal_id}.")
    if proposal.status != "proposed":
        raise ConflictError(
            f"Content proposal {proposal_id} is already {proposal.status!r}; only a "
            "'proposed' proposal can be accepted."
        )

    check = check_acceptance(session, proposal, eval_run_after_id)

    if check.blocked_by == "no_before_run":
        raise ConflictError(
            f"Content proposal {proposal_id} has no before-run recorded — propose_content_fix "
            "found no prior 'answer' eval run when this proposal was created, so there is "
            "nothing to validate the fix against."
        )
    if check.blocked_by == "missing_before_run":
        raise NotFoundError(f"No eval run {check.before_id}.")
    if check.blocked_by == "incomplete_before_run":
        raise ConflictError(
            f"before-run {check.before_id} measured no questions — there is no baseline to "
            "compare against. Re-propose this fix once a non-empty eval run exists."
        )
    if check.blocked_by == "missing_after_run":
        raise NotFoundError(f"No eval run {eval_run_after_id}.")
    if check.blocked_by == "after_run_wrong_kind":
        raise ConflictError(
            f"eval_run_after_id {eval_run_after_id} does not name an 'answer'-kind eval run; "
            "accept_proposal only accepts against an answer-kind run."
        )
    if check.blocked_by == "after_run_not_newer":
        raise ConflictError(
            f"eval_run_after_id {eval_run_after_id} is not newer than before-run "
            f"{check.before_id} — accept_proposal requires the after-run to have been recorded "
            "strictly after the before-run, not merely a run that happens to look different."
        )
    if check.blocked_by == "corpus_unchanged":
        raise ConflictError(
            f"The corpus did not change between eval run {check.before_id} and "
            f"{check.after_id} — the after-run measured the same corpus, so nothing new was "
            "validated."
        )
    if check.blocked_by == "pct_dropped":
        raise ConflictError(
            f"pct_fully_supported dropped from {check.pct_before} (run {check.before_id}) to "
            f"{check.pct_after} (run {check.after_id})."
        )
    if check.blocked_by == "draft_not_published":
        raise ConflictError(
            f"Content proposal {proposal_id}'s draft is not published — accept_proposal "
            "requires this proposal's own fix to be live before a run can validate it."
        )
    if check.blocked_by == "after_run_predates_publication":
        raise ConflictError(
            f"eval_run_after_id {eval_run_after_id}'s corpus predates content proposal "
            f"{proposal_id}'s draft being published — this run did not measure a corpus "
            "containing this fix."
        )
    if check.blocked_by == "incomplete_after_run":
        named = ", ".join(check.missing_questions[:3])
        raise ConflictError(
            f"eval_run_after_id {eval_run_after_id} did not measure "
            f"{len(check.missing_questions)} of the before-run's questions ({named}), so it "
            "cannot show whether they regressed."
        )
    if check.blocked_by == "regressions":
        named = ", ".join(check.regressions[:3])
        # Fix round 2, M7: worded relative to the STAMPED before-run, not as a claim that this
        # proposal's own fix caused the regression — `before` is stamped at propose time, and a
        # corpus change unrelated to this fix landing between propose and publish sits inside
        # this same comparison window (see this function's own docstring).
        raise ConflictError(
            f"{len(check.regressions)} question(s) regressed (PASS -> FAIL) between the "
            f"before-run stamped at propose time ({check.before_id}) and {check.after_id}: "
            f"{named}. This reflects the whole window since the proposal was made, not "
            "necessarily this fix in isolation."
        )

    proposal.status = "accepted"
    proposal.eval_run_after_id = eval_run_after_id
    proposal.updated_at = datetime.now(UTC)
    session.flush()
    return proposal


def _archive_draft_if_published(
    session: Session,
    draft_content_id: uuid.UUID | None,
    *,
    actor_id: uuid.UUID | None,
    pipeline: ChunkPipeline,
) -> str:
    """Archive `draft_content_id`'s row iff it is `published` (Ruling C); report what happened.

    Ruling C (task-16 brief): `archive_content` is legal from `published` only, and the
    *purpose* of the archive step is to take a bad fix out of the corpus — archiving removes its
    chunks, which is what undoes a regression. A `draft` has no chunks and is already invisible
    to retrieval, so there is nothing to undo; an already-`archived` row is already there; a
    missing or soft-deleted row (via `get_content`'s active-row read) has nothing to act on
    either. Every branch reports the status it found rather than staying silent.

    Returns:
        `"archived"` after archiving a published row; the row's current `status` when it was
        `draft` or already `archived`; the literal `"missing"` when `draft_content_id` is `None`
        or names no active row.
    """
    if draft_content_id is None:
        return "missing"
    try:
        draft = get_content(session, draft_content_id)
    except NotFoundError:
        return "missing"
    if draft.status != "published":
        return draft.status
    archive_content(session, draft.id, actor_id=actor_id, pipeline=pipeline)
    return "archived"


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
    `{"rejection": {"reason": ..., "at": "<iso>", "draft_status_after": "<status>|missing"}}` —
    a NEW dict assigned to the column (`content_proposals` has no `reason` column, and DESIGN's
    single-migration rule means it is not getting one; the evidence blob is already "the thing
    that goes on the slide"). The linked draft is archived via the existing `archive_content`
    **iff it is `published`** — see `_archive_draft_if_published`/Ruling C for the three other
    cases and why they archive nothing.

    Raises:
        NotFoundError: no such proposal.
        ConflictError: its `status` is not `proposed`.
    """
    proposal = session.get(ContentProposal, proposal_id)
    if proposal is None:
        raise NotFoundError(f"No content proposal {proposal_id}.")
    if proposal.status != "proposed":
        raise ConflictError(
            f"Content proposal {proposal_id} is already {proposal.status!r}; only a "
            "'proposed' proposal can be rejected."
        )

    draft_status_after = _archive_draft_if_published(
        session, proposal.draft_content_id, actor_id=actor_id, pipeline=pipeline
    )

    proposal.status = "rejected"
    proposal.evidence = {
        **proposal.evidence,
        "rejection": {
            "reason": reason,
            "at": datetime.now(UTC).isoformat(),
            "draft_status_after": draft_status_after,
        },
    }
    proposal.updated_at = datetime.now(UTC)
    session.flush()
    return proposal
