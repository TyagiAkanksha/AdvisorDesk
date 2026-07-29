"""Schema tests for the PRD §4 tables: defaults, constraints, the active-row filter, and indexes.

All tests here use the `db_session`/`tmp_engine` fixtures (CONVENTIONS.md
§10) — they run for real against a throwaway Postgres schema when
`TEST_DATABASE_URL` is set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Chunk, Content
from app.services.queries import active_select


def test_content_insert_sets_defaults(db_session: Session) -> None:
    """Inserting a `Content` row yields a server-generated id and timestamps (PRD §4)."""
    content = Content(title="Roth IRA Basics", slug="roth-ira-basics")
    db_session.add(content)
    db_session.flush()

    assert isinstance(content.id, uuid.UUID)
    assert isinstance(content.created_at, datetime)
    assert isinstance(content.updated_at, datetime)
    assert content.is_deleted is False


def test_slug_unique_constraint_raises_on_duplicate(db_session: Session) -> None:
    """`content.slug` is unique — PRD §4.1: slug uniqueness spans deleted rows too."""
    db_session.add(Content(title="First", slug="dup-slug"))
    db_session.flush()

    db_session.add(Content(title="Second", slug="dup-slug"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_slug_unique_constraint_spans_soft_deleted_rows(db_session: Session) -> None:
    """PRD §4.1: a deleted item's slug is never reused — the constraint is not partial."""
    db_session.add(Content(title="Gone", slug="gone-slug", is_deleted=True))
    db_session.flush()

    db_session.add(Content(title="New Attempt", slug="gone-slug"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_status_check_constraint_rejects_bogus_value(db_session: Session) -> None:
    """`content.status` is constrained to draft/published/archived (PRD §4)."""
    db_session.add(Content(title="Bad Status", slug="bad-status", status="bogus"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_chunk_embedding_round_trips_1536_floats(db_session: Session) -> None:
    """`chunks.embedding` stores/returns a 1536-dim vector (PRD §4, §7.2)."""
    content = Content(title="Embeddable", slug="embeddable")
    db_session.add(content)
    db_session.flush()

    vector = [(i % 100) / 100.0 for i in range(1536)]
    chunk = Chunk(content_id=content.id, chunk_index=0, text="hello world", embedding=vector)
    db_session.add(chunk)
    db_session.flush()
    db_session.expire(chunk)

    stored = db_session.get(Chunk, chunk.id)
    assert stored is not None
    assert stored.embedding is not None
    assert len(stored.embedding) == 1536
    assert stored.embedding == pytest.approx(vector, rel=1e-4)


def test_active_select_excludes_soft_deleted_rows(db_session: Session) -> None:
    """`active_select` is THE §4.1 active-row filter — it excludes `is_deleted=True` rows."""
    kept = Content(title="Kept", slug="kept")
    deleted = Content(title="Deleted", slug="deleted", is_deleted=True)
    db_session.add_all([kept, deleted])
    db_session.flush()

    results = db_session.scalars(active_select(Content)).all()

    slugs = {row.slug for row in results}
    assert "kept" in slugs
    assert "deleted" not in slugs


def test_inspector_sees_hnsw_and_fk_indexes(tmp_engine: Engine) -> None:
    """Migration 0001 creates the HNSW index and the three §4.1 FK indexes with named identities."""
    inspector = sa.inspect(tmp_engine)

    chunk_index_names = {ix["name"] for ix in inspector.get_indexes("chunks")}
    assert "ix_chunks_embedding_hnsw" in chunk_index_names
    assert "ix_chunks_content_id" in chunk_index_names

    content_tags_index_names = {ix["name"] for ix in inspector.get_indexes("content_tags")}
    assert "ix_content_tags_tag_id" in content_tags_index_names

    chat_messages_index_names = {ix["name"] for ix in inspector.get_indexes("chat_messages")}
    assert "ix_chat_messages_session_created" in chat_messages_index_names

    with tmp_engine.connect() as conn:
        index_def = conn.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw'")
        ).scalar_one()
    assert "USING hnsw" in index_def
    assert "vector_cosine_ops" in index_def
