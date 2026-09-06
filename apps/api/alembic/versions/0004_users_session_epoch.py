"""users.session_epoch: server-side session revocation counter (PRD §9; phase-6 task-05)

Phase-2 review finding t01-M6 (logout does not revoke): `/auth/logout` previously only cleared
the calling browser's cookie — a captured/stolen cookie kept authenticating for the rest of its
30-day signed lifetime. `users.session_epoch` is the fix: every session cookie is now signed
with the `session_epoch` value in effect at issuance (`app.auth.sessions.issue_cookie`), and
`/auth/logout` bumps this counter (`app.services.users.bump_session_epoch`), so `require_admin`
(`app.auth.deps`) can reject any cookie whose signed epoch no longer matches the row — dead the
instant the row moves to N+1, no server-side session-store table needed.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add `users.session_epoch`: integer, not null, server default `0`.

    Every existing row (there is at most a single admin pre-deploy, per the brief) backfills to
    `0` via the server default, matching the ORM model's `default=0` for freshly-inserted rows.
    """
    op.add_column(
        "users",
        sa.Column("session_epoch", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    """Drop `users.session_epoch` — no data worth preserving across a schema-review rollback."""
    op.drop_column("users", "session_epoch")
