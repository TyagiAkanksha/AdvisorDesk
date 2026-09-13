"""eval tables, feedback/latency signals

phase-9 eval-data-loop, task-01 (docs/plans/phase-9-eval-data-loop/DESIGN.md §"Migration
`0009_eval_and_feedback`"): one additive migration, no backfill. Two new nullable `chat_messages`
columns (`feedback`, `latency_ms` — "never asked"/"never measured" must stay distinguishable from
a real value, hence no default on either) plus three new tables: `eval_runs` (one row per harness
invocation), `eval_results` (one row per question inside a run, FK cascade to its `eval_runs`
row), and `content_proposals` (created here, left inert until a later task wires its MCP tools).

Hand-written (Alembic is the only DDL path, CONVENTIONS.md §6) to mirror `app/models/chat.py` and
`app/models/eval.py` exactly — constraint/index names follow `app.models.base.Base`'s naming
convention (verified against the live ORM metadata, not guessed), matching 0007's own discipline,
so `tests/test_models_schema.py::test_orm_metadata_matches_migration_head` sees zero drift.

Table creation order (and the reverse for `downgrade`) follows FK dependency, same shape as 0007:
the two `chat_messages` columns first (no dependency on the new tables), then `eval_runs` (no
dependency on anything new), then `eval_results` (FK -> `eval_runs`), then `content_proposals`
last (FKs -> `content` x2, `eval_runs` x2, `users`).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add the two `chat_messages` signal columns, then create the three new eval-loop tables."""
    op.add_column("chat_messages", sa.Column("feedback", sa.SmallInteger(), nullable=True))
    op.add_column("chat_messages", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_chat_messages_feedback_valid"), "chat_messages", "feedback in (-1, 1)"
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.Text(), server_default=sa.text("'answer'"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("git_sha", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("chat_model", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.Text(), nullable=False),
        sa.Column("similarity_threshold", sa.Float(), nullable=False),
        sa.Column("retrieval_k", sa.Integer(), nullable=False),
        sa.Column("corpus_content_count", sa.Integer(), nullable=False),
        sa.Column("corpus_chunk_count", sa.Integer(), nullable=False),
        sa.Column("corpus_max_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("corpus_digest", sa.Text(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("pct_fully_supported", sa.Float(), nullable=False),
        sa.Column("refusal_correct", sa.Integer(), nullable=False),
        sa.Column("refusal_total", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind in ('answer', 'agent')", name=op.f("ck_eval_runs_kind_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    op.create_index("ix_eval_runs_kind_created", "eval_runs", ["kind", "created_at"], unique=False)

    op.create_table(
        "eval_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_class", sa.Text(), nullable=True),
        sa.Column("persona", sa.Text(), nullable=True),
        sa.Column("answerable", sa.Boolean(), nullable=False),
        sa.Column("expected_slugs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cited_slugs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("slugs_hit", sa.Boolean(), nullable=False),
        sa.Column("fully_supported", sa.Boolean(), nullable=True),
        sa.Column("refused", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("top_similarity", sa.REAL(), nullable=True),
        sa.Column("answer_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["eval_runs.id"],
            name=op.f("fk_eval_results_run_id_eval_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_results")),
        sa.UniqueConstraint("run_id", "question", name=op.f("uq_eval_results_run_id_question")),
    )
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"], unique=False)

    op.create_table(
        "content_proposals",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_content_id", sa.UUID(), nullable=True),
        sa.Column("draft_content_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'proposed'"), nullable=False),
        sa.Column("eval_run_before_id", sa.UUID(), nullable=True),
        sa.Column("eval_run_after_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind in ('new_article', 'expand_article', 'retune')",
            name=op.f("ck_content_proposals_kind_valid"),
        ),
        sa.CheckConstraint(
            "status in ('proposed', 'accepted', 'rejected')",
            name=op.f("ck_content_proposals_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["target_content_id"],
            ["content.id"],
            name=op.f("fk_content_proposals_target_content_id_content"),
        ),
        sa.ForeignKeyConstraint(
            ["draft_content_id"],
            ["content.id"],
            name=op.f("fk_content_proposals_draft_content_id_content"),
        ),
        sa.ForeignKeyConstraint(
            ["eval_run_before_id"],
            ["eval_runs.id"],
            name=op.f("fk_content_proposals_eval_run_before_id_eval_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["eval_run_after_id"],
            ["eval_runs.id"],
            name=op.f("fk_content_proposals_eval_run_after_id_eval_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_content_proposals_created_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_proposals")),
    )
    op.create_index(
        "ix_content_proposals_status_created",
        "content_proposals",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Reverse `upgrade()` exactly: drop the three tables (indexes first, per 0007's shape, in
    reverse FK-dependency order), then the `chat_messages` CHECK, then its two columns."""
    op.drop_index("ix_content_proposals_status_created", table_name="content_proposals")
    op.drop_table("content_proposals")

    op.drop_index("ix_eval_results_run_id", table_name="eval_results")
    op.drop_table("eval_results")

    op.drop_index("ix_eval_runs_kind_created", table_name="eval_runs")
    op.drop_table("eval_runs")

    op.drop_constraint(op.f("ck_chat_messages_feedback_valid"), "chat_messages", type_="check")
    op.drop_column("chat_messages", "latency_ms")
    op.drop_column("chat_messages", "feedback")
