"""`EvalRun`/`EvalResult`/`ContentProposal` ORM models — phase-9 eval-data-loop.

DESIGN.md §B1 ("Persist runs"): `eval_runs` is one row per harness invocation (a fingerprint of
the models/settings/corpus it ran against, plus the aggregate totals it produced); `eval_results`
is one row per question inside that run, unique on `(run_id, question)` so a re-run of the same
question set never collides, and cascades away with its parent run. `eval_results.metrics` is
deliberately a bare JSONB bucket with no columns of its own yet — tasks 05/06/07 (recall@k,
context-precision/recall, the failure-taxonomy classifier) write into it without a second
migration (INDEX plan-time ruling; DESIGN "one migration").

DESIGN.md §D ("Weak queries and the proposal record"): `content_proposals` is created here and
left inert until task 16 wires its MCP tools (`propose_content_fix`/`accept_proposal`/etc.) — the
table exists now so every later task in this phase needs no second migration. `evidence` is a
JSONB **snapshot** of the weak-query rows that motivated the proposal (not FKs — chat rows are
prunable and the blob itself is the artifact), not a live join.

Note (task-01 report): DESIGN gives `content_proposals` an `updated_at` (`UpdatedAtMixin`), even
though PRD §4.1 scopes that mixin to `users`/`content`/`tags` only. DESIGN is authoritative on any
conflict with the PRD (this file's own module list of sources of truth) — `content_proposals` is
a phase-9 table the PRD never enumerated in the first place, so there is no PRD table to conflict
with; it is mutable (`status` moves `proposed -> accepted|rejected`, `draft_content_id`/
`eval_run_after_id` are filled in after creation) and tracking when it last changed is exactly
`UpdatedAtMixin`'s job, so this is a straightforward DESIGN extension rather than a genuine rules
clash.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    REAL,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UpdatedAtMixin, uuid_pk


class EvalRun(Base, TimestampMixin):
    """One harness invocation: the models/settings/corpus it ran with, plus its totals.

    `kind` distinguishes an answer-quality run (`"answer"`, the default — recall@k, faithfulness,
    refusal correctness) from an agent-trajectory run (`"agent"`, phase-9 execution-order item 3)
    sharing this same table so `compare_runs`/`latest_runs` (DESIGN §B1) work uniformly over
    either. `corpus_digest` is a sha256 of `(slug, updated_at)` pairs (DESIGN §B1) — a content-only
    fingerprint of what the run measured, independent of `git_sha` (the code that measured it).
    """

    __tablename__ = "eval_runs"
    __table_args__ = (
        CheckConstraint("kind in ('answer', 'agent')", name="kind_valid"),
        Index("ix_eval_runs_kind_created", "kind", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default="answer", server_default=text("'answer'")
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    chat_model: Mapped[str] = mapped_column(Text, nullable=False)
    judge_model: Mapped[str] = mapped_column(Text, nullable=False)
    similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_k: Mapped[int] = mapped_column(Integer, nullable=False)
    corpus_content_count: Mapped[int] = mapped_column(Integer, nullable=False)
    corpus_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # A `Content.updated_at` value (max across the corpus), not this run's own `created_at` —
    # nullable because a corpus with zero content rows has no max to report.
    corpus_max_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    corpus_digest: Mapped[str] = mapped_column(Text, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    pct_fully_supported: Mapped[float] = mapped_column(Float, nullable=False)
    refusal_correct: Mapped[int] = mapped_column(Integer, nullable=False)
    refusal_total: Mapped[int] = mapped_column(Integer, nullable=False)


class EvalResult(Base, TimestampMixin):
    """One eval question's outcome inside a run (DESIGN §B1) — cascades away with its `EvalRun`.

    `metrics` is an open JSONB bucket (task-01 brief line 106-107): tasks 05/06/07 write
    recall@k/precision@k/MRR, the rubric-judge scores, and the failure-taxonomy label into it,
    with no further migration.
    """

    __tablename__ = "eval_results"
    __table_args__ = (
        UniqueConstraint("run_id", "question", name="uq_eval_results_run_id_question"),
        Index("ix_eval_results_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_slugs: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    cited_slugs: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    slugs_hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fully_supported: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    top_similarity: Mapped[float | None] = mapped_column(REAL, nullable=True)
    answer_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    metrics: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class ContentProposal(Base, TimestampMixin, UpdatedAtMixin):
    """A proposed content fix, generated from a `weak_queries` report (DESIGN §D).

    Created inert (task-01): no tool in this task writes a row here yet — task 16 wires
    `propose_content_fix`/`list_proposals`/`accept_proposal`/`reject_proposal` on top of this
    table. `target_content_id` names the article a fix would `expand_article`/`retune`; `evidence`
    is a JSONB snapshot (not FKs) of the weak-query rows that motivated the proposal.
    """

    __tablename__ = "content_proposals"
    __table_args__ = (
        CheckConstraint("kind in ('new_article', 'expand_article', 'retune')", name="kind_valid"),
        CheckConstraint("status in ('proposed', 'accepted', 'rejected')", name="status_valid"),
        Index("ix_content_proposals_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    target_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content.id"), nullable=True
    )
    draft_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="proposed", server_default=text("'proposed'")
    )
    eval_run_before_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id"), nullable=True
    )
    eval_run_after_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
