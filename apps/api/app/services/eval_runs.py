"""Eval-run persistence: `corpus_fingerprint`, `record_run`, `latest_runs`, `compare_runs`
(phase-9 DESIGN §B1) — `app.eval.groundedness`'s CLI calls these to make every harness run data,
and `compare_runs` is the evidence behind "validated before acceptance".

Plain, session-first functions (CONVENTIONS.md §3) — no retrieval, no LLM calls, no YAML loading:
those live in `app.eval`/`app.rag`, which `app.services` may never import (CONVENTIONS.md §2
layering: "app.services imports only app.models and app.config"; `apps/api/pyproject.toml`'s
import-linter contract for this package now names `app.eval` in its `forbidden_modules` — the
layering is a gate here, not a habit). `record_run`/`compare_runs` therefore accept
`EvalReportLike`/`EvalRowLike`, structural Protocols the real `app.eval.groundedness.EvalReport`/
`EvalRow` (frozen dataclasses) satisfy by shape, with no inheritance relationship — the same seam
pattern `app.services.chat.RetrievedChunkLike`/`RetrievalResultLike` use for `app.rag`.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chunk, Content, EvalResult, EvalRun
from app.services.errors import ConflictError, NotFoundError
from app.services.queries import active_select


class EvalRowLike(Protocol):
    """The subset of `app.eval.groundedness.EvalRow`'s shape this module persists.

    Structural, read-only `@property` members — the same seam pattern `app.services.chat.
    RetrievedChunkLike` uses, and for the same reason: the import-linter contract "app.services
    imports only app.models and app.config" forbids importing `app.eval` from here, and `EvalRow`
    is a frozen dataclass that satisfies this by shape.
    """

    @property
    def question(self) -> str: ...
    @property
    def question_class(self) -> str | None: ...
    @property
    def persona(self) -> str | None: ...
    @property
    def answerable(self) -> bool: ...
    @property
    def expected_slugs(self) -> Sequence[str]: ...
    @property
    def cited_slugs(self) -> Sequence[str]: ...
    @property
    def slugs_hit(self) -> bool: ...
    @property
    def fully_supported(self) -> bool | None: ...
    @property
    def refused(self) -> bool: ...
    @property
    def verdict(self) -> str: ...
    @property
    def top_similarity(self) -> float | None: ...
    @property
    def answer_text(self) -> str: ...
    @property
    def metrics(self) -> dict[str, object] | None: ...


class EvalReportLike(Protocol):
    """The subset of `app.eval.groundedness.EvalReport`'s shape `record_run` persists."""

    @property
    def rows(self) -> Sequence[EvalRowLike]: ...
    @property
    def pct_fully_supported(self) -> float: ...
    @property
    def refusal_correct(self) -> int: ...
    @property
    def refusal_total(self) -> int: ...


@dataclass(frozen=True)
class CorpusFingerprint:
    """Identifies the corpus a run measured (DESIGN §B1/§D: `Content.updated_at` is stamped on
    every write, so no corpus-version column is needed)."""

    content_count: int
    chunk_count: int
    max_updated_at: datetime | None
    digest: str


@dataclass(frozen=True)
class RunDiff:
    """`compare_runs`' answer, joined on question text.

    Fix wave F1: `regressions`/`improvements`/`unchanged` are now FAMILY-MAJORITY classifications
    (see `compare_runs`'s own docstring) rather than a straight per-run verdict comparison, and
    `pct_delta` is the difference of the two families' `pct_fully_supported` MEANS. A family of
    one (the common case for a one-off `--label` with no `--runs N`) makes every one of these
    identical to the old single-run behaviour — nothing here changes shape or meaning for that
    case, only for a genuine multi-run family.

    Fix wave round 2 (M4): `pct_before`/`pct_after` are the two family means `pct_delta` was
    always the DIFFERENCE of — now surfaced as their own fields (computed once; `pct_delta ==
    pct_after - pct_before` by construction) so a caller (the CLI's `compare` line,
    `app.eval.groundedness._run_from_cli`) can print the exact numbers the acceptance gate judged
    instead of either named run's own single-run scalar.
    """

    before_id: uuid.UUID
    after_id: uuid.UUID
    regressions: list[str]  # questions whose family-majority verdict went PASS -> FAIL (fix wave
    # round 2, M2: an after-side TIE counts as a FAIL here, against a before-side PASS)
    improvements: list[str]  # family-majority FAIL -> a CLEAN after-side PASS (a tie does not
    # count as an improvement)
    unchanged: list[str]  # same family-majority verdict both sides, a before-side tie, or a
    # before-FAIL/after-tie (see `compare_runs`'s own docstring for the full truth table)
    added: list[str]  # present in the after family only (no before-family member measured it)
    removed: list[str]  # present in the before family only (no after-family member measured it)
    pct_before: float  # mean(before family pct_fully_supported)
    pct_after: float  # mean(after family pct_fully_supported)
    pct_delta: float  # pct_after - pct_before, by construction
    before_family: list[uuid.UUID]  # before_id's family, oldest first (always includes before_id)
    after_family: list[uuid.UUID]  # after_id's family, oldest first (always includes after_id)


def corpus_fingerprint(session: Session) -> CorpusFingerprint:
    """Fingerprint the corpus retrieval can currently see (PRD §4.1 active-row rule).

    Counts only rows retrieval can see: published, non-deleted `Content` (`active_select` +
    `status == "published"`) and the `Chunk` rows that belong to them. `digest` hashes
    `(slug, updated_at)` pairs ordered by slug, so it changes exactly when a published row's
    content or its `updated_at` stamp moves — the content-only half of "what did this run
    measure", independent of the code version (`git_sha`, recorded separately by `record_run`).

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first).

    Returns:
        A `CorpusFingerprint` describing the corpus as of right now.
    """
    published = session.scalars(
        active_select(Content).where(Content.status == "published").order_by(Content.slug)
    ).all()

    content_count = len(published)
    max_updated_at = max((row.updated_at for row in published), default=None)

    if published:
        content_ids = [row.id for row in published]
        chunk_count = (
            session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.content_id.in_(content_ids))
            )
            or 0
        )
    else:
        chunk_count = 0

    # Fix round 1, M7: `.astimezone(UTC)` before `.isoformat()` — the un-normalized text of an
    # aware datetime depends on the DB session's `TimeZone` setting, so a server/role configured
    # to a different zone would hash a different string for the SAME instant, producing a false
    # "corpus changed" digest for an unchanged corpus.
    digest_source = "\n".join(
        f"{row.slug}\t{row.updated_at.astimezone(UTC).isoformat()}" for row in published
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]

    return CorpusFingerprint(
        content_count=content_count,
        chunk_count=chunk_count,
        max_updated_at=max_updated_at,
        digest=digest,
    )


def record_run(
    session: Session,
    report: EvalReportLike,
    *,
    label: str,
    kind: str = "answer",
    embedding_model: str,
    chat_model: str,
    judge_model: str,
    similarity_threshold: float,
    retrieval_k: int,
    git_sha: str = "",
) -> EvalRun:
    """Persist one harness invocation: one `EvalRun` row plus one `EvalResult` per `report.rows`
    entry (DESIGN §B1).

    Computes its own `corpus_fingerprint` — callers never pass one in, so the fingerprint always
    describes the corpus AT RECORD TIME. Flushes only; never commits (CONVENTIONS.md §3 — the
    CLI, not this service function, owns the transaction boundary).

    Fix round 1, C1: `created_at` is stamped app-side (`datetime.now(UTC)`), not left to the
    column's `now()` server default. Postgres' `now()` is the *transaction* timestamp — every run
    of one `--runs N` invocation shares one transaction, so they would otherwise all carry the
    IDENTICAL `created_at` and `latest_runs`' declared `created_at DESC, id DESC` order would tie
    on a random UUID, not on recency. A Python-side value is distinct per call at microsecond
    resolution, needs no DDL change (the column keeps its `server_default` for any other writer),
    and makes both `latest_runs` and `--compare-to latest` genuinely newest-first.

    Args:
        session: the caller's `Session`.
        report: the run's outcome (real `EvalReport` or anything `EvalReportLike`-shaped).
        label: the run family this invocation belongs to (e.g. `"baseline-2026-09"`).
        kind: `"answer"` (default) or `"agent"` — which harness produced `report`.
        embedding_model: the embedding model name the run used.
        chat_model: the answering chat model name the run used.
        judge_model: the judge model name the run used.
        similarity_threshold: the retrieval similarity threshold the run used.
        retrieval_k: the retrieval `k` the run used.
        git_sha: the code version that produced `report`, or `""` when unknown.

    Returns:
        The newly created (and flushed) `EvalRun` row.
    """
    fingerprint = corpus_fingerprint(session)
    run = EvalRun(
        created_at=datetime.now(UTC),
        kind=kind,
        label=label,
        git_sha=git_sha,
        embedding_model=embedding_model,
        chat_model=chat_model,
        judge_model=judge_model,
        similarity_threshold=similarity_threshold,
        retrieval_k=retrieval_k,
        corpus_content_count=fingerprint.content_count,
        corpus_chunk_count=fingerprint.chunk_count,
        corpus_max_updated_at=fingerprint.max_updated_at,
        corpus_digest=fingerprint.digest,
        total_questions=len(report.rows),
        pct_fully_supported=report.pct_fully_supported,
        refusal_correct=report.refusal_correct,
        refusal_total=report.refusal_total,
    )
    session.add(run)
    session.flush()

    for row in report.rows:
        session.add(
            EvalResult(
                run_id=run.id,
                question=row.question,
                question_class=row.question_class,
                persona=row.persona,
                answerable=row.answerable,
                expected_slugs=list(row.expected_slugs),
                cited_slugs=list(row.cited_slugs),
                slugs_hit=row.slugs_hit,
                fully_supported=row.fully_supported,
                refused=row.refused,
                verdict=row.verdict,
                top_similarity=row.top_similarity,
                answer_text=row.answer_text,
                # `EvalResult.metrics` is plain JSONB (no `MutableDict`) — always a freshly built
                # dict, never an alias to the caller's own `row.metrics` object, so nothing later
                # mutates this column's value in place (SQLAlchemy would never notice such a
                # mutation without `MutableDict`). Fix round 1, M9: a DEEP copy — `row.metrics`
                # may hold nested dicts/lists (tasks 05/06's recall@k/rubric-score payloads), and
                # a shallow `dict(...)` would leave those inner containers aliased to the
                # caller's own object.
                metrics=copy.deepcopy(row.metrics) if row.metrics is not None else None,
            )
        )
    session.flush()
    return run


def latest_runs(
    session: Session, *, kind: str = "answer", label: str | None = None, limit: int = 10
) -> list[EvalRun]:
    """The `limit` most recent `EvalRun`s of `kind` (optionally filtered further by `label`).

    Orders `created_at DESC, id DESC`. `created_at` is stamped app-side by `record_run` (fix
    round 1, C1) rather than left to Postgres' `now()` transaction timestamp, so several runs
    written in one transaction (e.g. `--runs 3`) are still strictly ordered by actual insertion
    time; `id` (a random UUID) is a deterministic, but not recency-meaningful, final tiebreaker
    for the one-in-a-microsecond case two calls land on the identical instant.

    Args:
        session: the caller's `Session`.
        kind: `"answer"` (default) or `"agent"`.
        label: when given, only runs with this exact label.
        limit: caps the number of runs returned.

    Returns:
        `EvalRun`s newest-first, at most `limit` of them.
    """
    stmt = select(EvalRun).where(EvalRun.kind == kind)
    if label is not None:
        stmt = stmt.where(EvalRun.label == label)
    stmt = stmt.order_by(EvalRun.created_at.desc(), EvalRun.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def run_family(session: Session, run: EvalRun) -> list[EvalRun]:
    """Every `kind="answer"` `EvalRun` sharing `run`'s `label` AND `corpus_digest`, oldest first
    (fix wave F1 — the harness's own `--runs N` writes exactly this shape: one label, N rows, all
    measuring the same recorded corpus).

    `run` is always a member of its own family (`run.label == run.label` and `run.corpus_digest
    == run.corpus_digest` trivially hold), so a family is never empty — a caller degrading to a
    single-run comparison needs no special case; a family of one behaves exactly like the run
    itself.

    The digest guard keeps a re-used label from mixing corpora: two runs can share a label (an
    honest re-run of the same demo label on a different day) while measuring genuinely different
    corpora if a publish happened between them, and those must not be averaged/voted together.

    `kind="answer"` only: the family concept exists to vote/average over repeated MEASUREMENTS of
    the same corpus, which is not what `app.eval.agent_suite`'s `kind="agent"` runs are for (that
    harness has its own three-run stability story — task 07b's verification-record §9a — entirely
    separate from this one).

    Args:
        session: the caller's `Session`.
        run: any member of the family to look up.

    Returns:
        The family's `EvalRun` rows, ordered oldest (`created_at` ascending) first.
    """
    stmt = (
        select(EvalRun)
        .where(
            EvalRun.kind == "answer",
            EvalRun.label == run.label,
            EvalRun.corpus_digest == run.corpus_digest,
        )
        .order_by(EvalRun.created_at.asc(), EvalRun.id.asc())
    )
    return list(session.scalars(stmt).all())


def _majority_verdict(verdicts: Sequence[str]) -> str | None:
    """`"PASS"`/`"FAIL"` iff strictly more than half of `verdicts` agree; `None` on an exact tie
    or an empty sequence (fix wave F1).

    A tie is not "reproduced in a majority" in either direction — this function itself takes no
    side on what a `None` means. Fix wave round 2 (M2, correcting this docstring's own prior
    claim): the caller (`compare_runs`) treats a `None` differently depending on WHICH side ties.
    A `None` on the AFTER side is folded in with `"FAIL"` for the regression comparison —
    fail-closed where it matters, since a fix that cannot even hold a clean majority is not
    evidence the fix worked. A `None` on the BEFORE side folds to `unchanged` instead: there is no
    majority verdict to have regressed FROM, so it can be neither a regression nor an improvement.
    """
    if not verdicts:
        return None
    passes = sum(1 for verdict in verdicts if verdict == "PASS")
    fails = len(verdicts) - passes
    threshold = len(verdicts) / 2
    if passes > threshold:
        return "PASS"
    if fails > threshold:
        return "FAIL"
    return None


def _verdicts_by_question(session: Session, run_ids: Sequence[uuid.UUID]) -> dict[str, list[str]]:
    """Every `EvalResult.verdict` for `run_ids`, grouped by question text.

    `eval_results`' own `(run_id, question)` uniqueness (`uq_eval_results_run_id_question`) means
    each run contributes at most one verdict per question, so `len(grouped[question])` is exactly
    the number of `run_ids` that measured that question — the denominator `_majority_verdict`
    needs.
    """
    if not run_ids:
        return {}
    rows = session.scalars(select(EvalResult).where(EvalResult.run_id.in_(run_ids))).all()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.question, []).append(row.verdict)
    return grouped


def compare_runs(session: Session, before_id: uuid.UUID, after_id: uuid.UUID) -> RunDiff:
    """Diff two runs' FAMILIES of `EvalResult` verdicts, joined on question text (DESIGN §B1 —
    the evidence behind "validated before acceptance"; fix wave F1 — a regression is a flip that
    REPRODUCES).

    `before_id`/`after_id` each name one run; `run_family` resolves each to every `kind="answer"`
    run sharing that run's `label` AND `corpus_digest` (its "family" — the harness's `--runs N`
    writes exactly this shape). A question is a **regression** when the BEFORE family's majority
    verdict is PASS and the AFTER family's majority verdict is FAIL **or ties** (fix wave round 2,
    M2: an after-side tie counts against the fix — fail-closed where it matters, since padding a
    reproducing regression's after-family with passing runs until it merely TIES must not be a
    way to vote it away). An **improvement** is NOT the exact mirror: it requires the before
    family's majority to be FAIL and the after family's majority to be a CLEAN "PASS" — a tie on
    the after side is not evidence of an improvement either. Anything else — both sides agree, a
    before-side tie (there is no majority to have regressed/improved FROM), or a before-FAIL
    paired with an after-side tie — is `unchanged`. `pct_before`/`pct_after` are the two families'
    `pct_fully_supported` MEANS (not the two named runs' own scalars); `pct_delta` is
    `pct_after - pct_before` by construction. A family of one — the common case, e.g. a one-off
    `--label` with no `--runs N` — makes every one of these identical to the pre-F1 single-run
    behaviour: this is why every pre-existing `compare_runs` test keeps passing unchanged.

    `added`/`removed` are computed over the FAMILY UNION on each side: a question counts as
    `removed` only when NO after-family member ever measured it (some after-family members
    covering it while others do not is a per-run coverage gap `app.services.proposals.
    check_acceptance` checks independently, per member — not something `compare_runs` itself
    decides).

    Every list in the returned `RunDiff` is sorted by question text so output is stable.

    Args:
        session: the caller's `Session`.
        before_id: an `EvalRun.id` naming the before family.
        after_id: an `EvalRun.id` naming the after family.

    Returns:
        A `RunDiff` classifying every question either family's results as a regression,
        improvement, unchanged, added, or removed, plus both families' member ids.

    Raises:
        NotFoundError: `before_id` or `after_id` names no `EvalRun` row.
        ConflictError: `before`/`after` have different `kind`s (fix round 1, M3) — an `"answer"`
            run and an `"agent"` run share no comparable question set, so diffing across `kind`
            (probe P5 in the task-03 review) is a caller error, not a valid comparison.
    """
    before = session.get(EvalRun, before_id)
    if before is None:
        raise NotFoundError(f"No eval run {before_id}.")
    after = session.get(EvalRun, after_id)
    if after is None:
        raise NotFoundError(f"No eval run {after_id}.")
    if before.kind != after.kind:
        raise ConflictError(f"Cannot compare a {before.kind!r} run to a {after.kind!r} run.")

    before_family = run_family(session, before)
    after_family = run_family(session, after)
    before_family_ids = [member.id for member in before_family]
    after_family_ids = [member.id for member in after_family]

    before_verdicts = _verdicts_by_question(session, before_family_ids)
    after_verdicts = _verdicts_by_question(session, after_family_ids)

    before_questions = set(before_verdicts)
    after_questions = set(after_verdicts)
    common = before_questions & after_questions

    regressions: list[str] = []
    improvements: list[str] = []
    unchanged: list[str] = []
    for question in sorted(common):
        before_majority = _majority_verdict(before_verdicts[question])
        after_majority = _majority_verdict(after_verdicts[question])
        # Fix wave round 2 (M2): an after-side TIE (`None`) is folded in with `"FAIL"` for the
        # regression side ONLY — a before-side PASS with an after-side tie still counts against
        # the fix. An improvement has no such allowance: it requires a CLEAN after-side PASS, so a
        # before-FAIL/after-tie question falls through to `unchanged`, and a before-side tie
        # (`before_majority is None`) can never satisfy either branch, so it always lands in
        # `unchanged` too — see `_majority_verdict`'s docstring for the full reasoning.
        if before_majority == "PASS" and after_majority in ("FAIL", None):
            regressions.append(question)
        elif before_majority == "FAIL" and after_majority == "PASS":
            improvements.append(question)
        else:
            unchanged.append(question)

    before_pct_values = [member.pct_fully_supported for member in before_family]
    after_pct_values = [member.pct_fully_supported for member in after_family]
    pct_before = sum(before_pct_values) / len(before_pct_values)
    pct_after = sum(after_pct_values) / len(after_pct_values)

    return RunDiff(
        before_id=before_id,
        after_id=after_id,
        regressions=regressions,
        improvements=improvements,
        unchanged=unchanged,
        added=sorted(after_questions - before_questions),
        removed=sorted(before_questions - after_questions),
        pct_before=pct_before,
        pct_after=pct_after,
        pct_delta=pct_after - pct_before,
        before_family=before_family_ids,
        after_family=after_family_ids,
    )
