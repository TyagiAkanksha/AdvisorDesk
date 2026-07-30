"""initial schema

PRD §4: all seven tables, the `vector` extension, and the §4.1 index set
(HNSW on `chunks.embedding`, plus the three FK indexes). Hand-reviewed from
`alembic revision --autogenerate` output — table/column shapes are copied
verbatim from the PRD §4 SQL block; constraint/index names not given
explicitly by the PRD follow the naming convention configured on
`app.models.base.Base.metadata`.

Revision ID: 0001
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create the `vector` extension, all seven PRD §4 tables, and the §4.1 index set.

    The extension is installed once into `public` — never into a per-test
    schema — so that parallel throwaway test schemas (each connecting with
    `search_path=<schema>,public`) all resolve the same `vector` TYPE
    without collision.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS vector SCHEMA public")

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
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
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("retrieval_found", sa.Boolean(), nullable=True),
        sa.Column("top_similarity", sa.REAL(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role in ('user', 'assistant')", name=op.f("ck_chat_messages_role_valid")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_chat_messages_session_id_chat_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    op.create_index(
        "ix_chat_messages_session_created",
        "chat_messages",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "content",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("body_md", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "status in ('draft', 'published', 'archived')",
            name=op.f("ck_content_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_content_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_content_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content")),
        sa.UniqueConstraint("slug", name=op.f("uq_content_slug")),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("content_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content.id"],
            name=op.f("fk_chunks_content_id_content"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_index("ix_chunks_content_id", "chunks", ["content_id"], unique=False)
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "content_tags",
        sa.Column("content_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content.id"],
            name=op.f("fk_content_tags_content_id_content"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name=op.f("fk_content_tags_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_id", "tag_id", name=op.f("pk_content_tags")),
    )
    op.create_index("ix_content_tags_tag_id", "content_tags", ["tag_id"], unique=False)


def downgrade() -> None:
    """Drop all seven tables in FK-safe order.

    The `vector` extension is deliberately NOT dropped here: it is shared,
    installed-once infrastructure (see `upgrade`) — dropping it could break
    other schemas/connections still relying on it (e.g. sibling throwaway
    test schemas created concurrently).
    """
    op.drop_index("ix_content_tags_tag_id", table_name="content_tags")
    op.drop_table("content_tags")
    op.drop_index(
        "ix_chunks_embedding_hnsw",
        table_name="chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_chunks_content_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("content")
    op.drop_index("ix_chat_messages_session_created", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("users")
    op.drop_table("tags")
    op.drop_table("chat_sessions")
