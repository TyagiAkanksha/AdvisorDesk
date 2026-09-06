"""api_tokens.expires_at: bearer-token expiry (PRD §9; phase-6 remediation task-09, WR-02 residual)

WR-02 residual (the expiry half 6R-03's session_epoch work, 0005, deliberately left open): today a
minted `api_tokens` row never expires on its own — only a hard `--revoke` or an owner-wide
`/auth/logout` epoch bump ever kills one. This migration adds a per-row expiry stamp so
`app.auth.tokens.resolve_bearer_token` can reject a token whose `expires_at` has passed.

Added nullable, in ONE step, with NO backfill UPDATE — unlike 0005's `session_epoch` (nullable ->
backfilled via a `UPDATE ... FROM users` join -> tightened to `NOT NULL`). Design pin (task brief):
`NULL` means "no expiry", PERMANENTLY, not a transient pre-backfill state — every pre-existing row
is `NULL` "for free" the instant this column is added, which IS the intended value for a
already-deployed connector's token (no forced expiry on migration day). `scripts/mint_mcp_token.py
::mint` stamps `now() + Settings.mcp_token_ttl_days` on every FRESH mint from here on; only
already-minted rows stay perpetually NULL. Mirrors the existing `content.published_at` column
shape (`app/models/content.py`: `Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
nullable=True)`), not `api_tokens.session_epoch`'s nullable-then-NOT-NULL shape.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add `api_tokens.expires_at` (nullable `TIMESTAMPTZ`, no backfill needed — `NULL` already
    means "no expiry" for every pre-existing row the instant this column exists)."""
    op.add_column("api_tokens", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop `api_tokens.expires_at` — no data worth preserving across a schema-review rollback
    (mirrors 0005's own downgrade of `session_epoch`)."""
    op.drop_column("api_tokens", "expires_at")
