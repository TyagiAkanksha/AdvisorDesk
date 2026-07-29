"""Shared test fixtures: throwaway-schema DB fixtures and the skip-by-fixture-name hook.

CONVENTIONS.md §10: DB tests run against a fresh Postgres schema
(`advisordesk_test_<hex8>`), migrated to head through the production engine
factory (`app.db.make_engine`) and Alembic, then dropped on teardown. When
`TEST_DATABASE_URL` is unset, any test that requests `tmp_engine` or
`db_session` is skipped **by fixture name** in collection — a skip is
recorded (visible in `-q` output), never a silent omission.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import make_engine, make_session_factory

# Fixture names that require a real database — a test requesting either one
# is skipped (not silently dropped) when TEST_DATABASE_URL is unset.
_DB_FIXTURE_NAMES = {"tmp_engine", "db_session"}

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_ALEMBIC_SCRIPT_LOCATION = Path(__file__).resolve().parent.parent / "alembic"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip DB-fixture tests when `TEST_DATABASE_URL` is unset (CONVENTIONS.md §10).

    Skips **by fixture name** rather than by test module/marker, so any
    present or future test that merely requests `tmp_engine`/`db_session`
    is covered automatically.
    """
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip_no_db = pytest.mark.skip(reason="TEST_DATABASE_URL not set")
    for item in items:
        if _DB_FIXTURE_NAMES.intersection(getattr(item, "fixturenames", ())):
            item.add_marker(skip_no_db)


def _require_database_url() -> str:
    """Return `TEST_DATABASE_URL`, or skip the current test if it is unset."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return url


@pytest.fixture
def tmp_engine() -> Iterator[Engine]:
    """A `sqlalchemy.Engine` bound to a throwaway Postgres schema, migrated to head.

    Creates schema `advisordesk_test_<hex8>`, runs `alembic upgrade head`
    into it (via `alembic.command.upgrade`, programmatically — faster than a
    subprocess) using the production engine factory, yields an engine
    pinned to that schema, then drops the schema (CONVENTIONS.md §10).
    """
    database_url = _require_database_url()
    schema = f"advisordesk_test_{secrets.token_hex(4)}"

    admin_engine = make_engine(database_url)
    with admin_engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    admin_engine.dispose()

    alembic_cfg = Config(str(_ALEMBIC_INI))
    alembic_cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    previous_migrate_schema = os.environ.get("MIGRATE_SCHEMA")
    os.environ["MIGRATE_SCHEMA"] = schema
    try:
        upgrade(alembic_cfg, "head")
    finally:
        if previous_migrate_schema is None:
            os.environ.pop("MIGRATE_SCHEMA", None)
        else:
            os.environ["MIGRATE_SCHEMA"] = previous_migrate_schema

    engine = make_engine(database_url, schema=schema)
    try:
        yield engine
    finally:
        engine.dispose()
        admin_engine = make_engine(database_url)
        with admin_engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def db_session(tmp_engine: Engine) -> Iterator[Session]:
    """A `Session` bound to `tmp_engine`, closed after the test."""
    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
