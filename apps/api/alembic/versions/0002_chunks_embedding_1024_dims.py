"""chunks.embedding: vector(1536) -> vector(1024) (PRD §7.2, v1.5)

Phase-3 task-02: the live embedding provider is NVIDIA NIM's
`nvidia/nv-embedqa-e5-v5` (1024 dims), not the 1536-dim
`text-embedding-3-small` shape 0001 originally provisioned. `chunks` is
derived, regenerable data (PRD §4.1: hard-delete only; every row is
rebuilt from `content.body_md` on the next publish/re-embed) and, as of
this migration, still empty in every environment this has been run
against — this task is `chunks`' first real writer — so this is a plain
resize with nothing to preserve.

General story for a populated table (documented, not exercised here): a
pgvector `vector(N)` column has no "widen/narrow" cast — `vector(1536)::
vector(1024)` raises (pgvector rejects a dimension-changing cast; it is not
truncation or padding), so `ALTER COLUMN ... TYPE ... USING ...` is not a
safe option once real rows exist. The correct procedure at that point is
either (a) `TRUNCATE chunks` before running this migration and let the next
publish/republish cycle repopulate every row at the new width, since chunks
carry no history of their own PRD wants kept, or (b) a genuine data
migration that re-embeds every existing chunk's `text` through the new
provider/model before the column is resized. This migration does neither —
it assumes an empty table (verified operationally, not by a guard in this
script) — so it uses the simpler drop-column/add-column shape below rather
than an `ALTER COLUMN TYPE` that would only ever work on zero rows anyway.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_INDEX_NAME = "ix_chunks_embedding_hnsw"
_INDEX_KWARGS = {
    "unique": False,
    "postgresql_using": "hnsw",
    "postgresql_ops": {"embedding": "vector_cosine_ops"},
}


def upgrade() -> None:
    """Drop and recreate `chunks.embedding` at 1024 dims, then the HNSW index.

    Explicit drop-index/drop-column/add-column/create-index, rather than an
    `ALTER COLUMN ... TYPE` — see the module docstring for why a type-level
    cast is not a real option here regardless of table contents. Dropping
    the column first (rather than relying on Postgres's implicit
    drop-dependent-index-on-column-drop behavior) keeps every step of this
    migration explicit and independently reviewable, matching 0001's style.
    """
    op.drop_index(_INDEX_NAME, table_name="chunks", **_INDEX_KWARGS)
    op.drop_column("chunks", "embedding")
    op.add_column("chunks", sa.Column("embedding", Vector(1024), nullable=True))
    op.create_index(_INDEX_NAME, "chunks", ["embedding"], **_INDEX_KWARGS)


def downgrade() -> None:
    """Reverse: drop/recreate `chunks.embedding` back to 1536 dims + its HNSW index.

    Same empty-table assumption as `upgrade` (see module docstring) — this
    is a downgrade path for schema review/rollback, not a data-preserving
    one.
    """
    op.drop_index(_INDEX_NAME, table_name="chunks", **_INDEX_KWARGS)
    op.drop_column("chunks", "embedding")
    op.add_column("chunks", sa.Column("embedding", Vector(1536), nullable=True))
    op.create_index(_INDEX_NAME, "chunks", ["embedding"], **_INDEX_KWARGS)
