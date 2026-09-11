"""Drop dead `oauth_consents.revoked_at` column (chore-2026-09 closeout item 2).

`revoked_at` (added by 0007) was FILTERED (`revoked_at IS NULL`) in
`app.services.oauth_consents.find_active_consent`/`record_consent` and
`app.services.oauth_clients.list_connected_apps`'s consent aggregate, and assigned `None` at
insert/revive time, but never set to a timestamp anywhere in the codebase — consent revocation
does not exist; the admin "Disconnect" action deletes the `OAuthClient` outright, cascading the
`oauth_consents` row away with it (`app.services.oauth_clients.delete_client`). Dead schema.

`0007_oauth_tables.py` never indexed this column (verified against that migration directly), so
there is nothing to drop before the column itself, and nothing beyond the column to recreate on
downgrade.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Drop `oauth_consents.revoked_at` — never set to a timestamp anywhere in the codebase."""
    op.drop_column("oauth_consents", "revoked_at")


def downgrade() -> None:
    """Re-add `oauth_consents.revoked_at`, exactly as `0007_oauth_tables.py` defined it."""
    op.add_column(
        "oauth_consents",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
