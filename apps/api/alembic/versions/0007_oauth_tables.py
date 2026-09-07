"""oauth data model: four new tables + three nullable api_tokens columns

mcp-oauth plan, task-01 (docs/plans/mcp-oauth/DESIGN.md §"Token & data model"): the persistent
foundation for an OAuth 2.1 authorization server co-hosted with the existing `/api/v1/mcp`
endpoint. Nothing yet issues, verifies, or rotates a code/token — that lands in later mcp-oauth
tasks, built on this schema and `app.services.token_hashing`.

Hand-written (Alembic is the only DDL path, CONVENTIONS.md §6) to mirror `app/models/oauth.py` and
`app/models/api_tokens.py`'s three new columns exactly — constraint/index names follow
`app.models.base.Base`'s naming convention (verified against the live ORM metadata rather than
guessed) so `tests/test_models_schema.py::test_orm_metadata_matches_migration_head` sees zero
drift.

Table creation order (and the reverse for `downgrade`) follows FK dependency: `oauth_clients` has
no dependencies; `oauth_authorization_codes`/`oauth_refresh_tokens`/`oauth_consents` each
reference it (and `users`); `oauth_refresh_tokens` additionally references the pre-existing
`api_tokens` (`access_token_id`, `ON DELETE SET NULL`) and itself (`rotated_from_id`, self-FK,
also `ON DELETE SET NULL`). The three new `api_tokens` columns are added last, since
`api_tokens.client_id`'s FK targets `oauth_clients`, which must already exist.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create the four mcp-oauth tables, then add the three new nullable `api_tokens` columns."""
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("redirect_uris", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("client_id", name=op.f("pk_oauth_clients")),
    )

    op.create_table(
        "oauth_authorization_codes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.client_id"],
            name=op.f("fk_oauth_authorization_codes_client_id_oauth_clients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_authorization_codes_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_authorization_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_oauth_authorization_codes_code_hash")),
    )
    op.create_index(
        "ix_oauth_authorization_codes_client_id",
        "oauth_authorization_codes",
        ["client_id"],
        unique=False,
    )

    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("access_token_id", sa.UUID(), nullable=True),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("rotated_from_id", sa.UUID(), nullable=True),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.client_id"],
            name=op.f("fk_oauth_refresh_tokens_client_id_oauth_clients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_refresh_tokens_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["access_token_id"],
            ["api_tokens.id"],
            name=op.f("fk_oauth_refresh_tokens_access_token_id_api_tokens"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rotated_from_id"],
            ["oauth_refresh_tokens.id"],
            name=op.f("fk_oauth_refresh_tokens_rotated_from_id_oauth_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_oauth_refresh_tokens_token_hash")),
    )
    op.create_index(
        "ix_oauth_refresh_tokens_client_id",
        "oauth_refresh_tokens",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_refresh_tokens_family_id",
        "oauth_refresh_tokens",
        ["family_id"],
        unique=False,
    )

    op.create_table(
        "oauth_consents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_consents_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.client_id"],
            name=op.f("fk_oauth_consents_client_id_oauth_clients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_consents")),
        sa.UniqueConstraint(
            "user_id", "client_id", name=op.f("uq_oauth_consents_user_id_client_id")
        ),
    )

    op.add_column("api_tokens", sa.Column("client_id", sa.Text(), nullable=True))
    op.add_column("api_tokens", sa.Column("resource", sa.Text(), nullable=True))
    op.add_column(
        "api_tokens", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_api_tokens_client_id_oauth_clients"),
        "api_tokens",
        "oauth_clients",
        ["client_id"],
        ["client_id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_api_tokens_client_id", "api_tokens", ["client_id"], unique=False)


def downgrade() -> None:
    """Reverse `upgrade()` exactly: drop the three `api_tokens` additions, then the four tables
    in dependency order (children before `oauth_clients`, which the other three all reference)."""
    op.drop_index("ix_api_tokens_client_id", table_name="api_tokens")
    op.drop_constraint(
        op.f("fk_api_tokens_client_id_oauth_clients"), "api_tokens", type_="foreignkey"
    )
    op.drop_column("api_tokens", "last_used_at")
    op.drop_column("api_tokens", "resource")
    op.drop_column("api_tokens", "client_id")

    op.drop_table("oauth_consents")

    op.drop_index("ix_oauth_refresh_tokens_family_id", table_name="oauth_refresh_tokens")
    op.drop_index("ix_oauth_refresh_tokens_client_id", table_name="oauth_refresh_tokens")
    op.drop_table("oauth_refresh_tokens")

    op.drop_index("ix_oauth_authorization_codes_client_id", table_name="oauth_authorization_codes")
    op.drop_table("oauth_authorization_codes")

    op.drop_table("oauth_clients")
