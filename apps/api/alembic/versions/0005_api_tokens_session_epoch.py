"""api_tokens.session_epoch: per-token revocation stamp (PRD §9; phase-6 remediation task-03)

WR-02 (bearer-token revocation via session epoch): today `/auth/logout` bumping
`users.session_epoch` (0004) revokes every outstanding session COOKIE (`require_admin` rejects a
stale cookie epoch) but leaves every outstanding bearer TOKEN (`api_tokens`) alive for the rest of
its lifetime — a leaked MCP connector token survives a logout indefinitely. This migration adds
the same per-row epoch stamp to `api_tokens`, so `app.auth.tokens.resolve_bearer_token` can reject
a token whose `session_epoch` no longer matches its owner's CURRENT `users.session_epoch`.

Backfill (deliberate, not a bare constant): each EXISTING row backfills to its OWNING user's
CURRENT `session_epoch` via `UPDATE ... FROM users`, not a static default — a hard-revoke backfill
(e.g. `0`) would silently break every already-deployed connector's live token the moment this
migration ran, even for owners who never logged out. Freshly-minted tokens after this migration
stamp the mint-time epoch directly (`scripts/mint_mcp_token.py::mint`), so only a SUBSEQUENT
`/auth/logout` ever revokes them.

Added nullable, backfilled, then tightened to NOT NULL (rather than a single `add_column(...,
nullable=False)` with a scalar `server_default`) because the backfill value depends on a JOIN to
`users`, which no `server_default=` expression can express.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add `api_tokens.session_epoch` (integer, not null), backfilled per-row from the owning
    user's CURRENT `session_epoch` before the NOT NULL constraint is applied."""
    op.add_column("api_tokens", sa.Column("session_epoch", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE api_tokens SET session_epoch = users.session_epoch "
        "FROM users WHERE api_tokens.user_id = users.id"
    )
    op.alter_column("api_tokens", "session_epoch", nullable=False)


def downgrade() -> None:
    """Drop `api_tokens.session_epoch` — no data worth preserving across a schema-review
    rollback (mirrors 0004's own downgrade of `users.session_epoch`)."""
    op.drop_column("api_tokens", "session_epoch")
