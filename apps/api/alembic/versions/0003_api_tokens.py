"""api_tokens: bearer tokens for the MCP endpoint (PRD §3, §9; phase-6 task-04)

Not a PRD §4 table — added by task-04 so a deployed Claude connector (which can send an
`Authorization: Bearer` header but never the admin session cookie) can authenticate against
`/api/v1/mcp`. Task-04 brief, design ruling: `api_tokens` composes ONLY `TimestampMixin`
(`app.models.api_tokens.ApiToken`), like the append-only tables 0001 already created
(`content_tags`, `chunks`, `chat_sessions`, `chat_messages`) — PRD §4.1 scopes `SoftDeleteMixin`
to `users`/`content`/`tags` specifically, and revocation here (`scripts/mint_mcp_token.py
--revoke`) is an honest hard `DELETE`, no restore path — so this migration creates exactly
`id`/`user_id`/`token_hash`/`name`/`created_at` and nothing else (no `updated_at`, no
`is_deleted`).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create `api_tokens`: uuid PK, FK to `users.id`, a unique `token_hash`, `name`, `created_at`.

    No FK index on `user_id`: PRD §4.1's "minimal FK index set" names exactly three lookups the
    app actually performs (`chunks.content_id`, `content_tags.tag_id`,
    `chat_messages.session_id`) — `api_tokens` is looked up by `token_hash` (already unique, and
    therefore indexed) at auth time and read in full by `scripts/mint_mcp_token.py --list`; no
    code path filters this table by `user_id` alone, so no additional index is warranted at this
    table's scale.
    """
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_tokens_token_hash")),
    )


def downgrade() -> None:
    """Drop `api_tokens` outright — an honest hard-delete table has no data worth preserving
    across a schema-review rollback."""
    op.drop_table("api_tokens")
