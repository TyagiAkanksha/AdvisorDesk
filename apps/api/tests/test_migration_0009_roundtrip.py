"""0009 round-trip: head -> 0008 -> head leaves a schema identical to the ORM metadata."""

from __future__ import annotations

import os
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine

from app.models import Base

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_ALEMBIC_SCRIPT_LOCATION = Path(__file__).resolve().parent.parent / "alembic"


def _alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    url = os.environ["TEST_DATABASE_URL"]
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _ignore_alembic_version_table(
    object_: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    return not (type_ == "table" and name == "alembic_version")


def test_0009_downgrades_to_0008_and_upgrades_back_to_a_matching_schema(
    tmp_engine: Engine,
) -> None:
    with tmp_engine.connect() as conn:
        schema = conn.execute(sa.text("SELECT current_schema()")).scalar_one()

    cfg = _alembic_config()
    previous = os.environ.get("MIGRATE_SCHEMA")
    os.environ["MIGRATE_SCHEMA"] = str(schema)
    try:
        downgrade(cfg, "0008")
        inspector = sa.inspect(tmp_engine)
        tables = set(inspector.get_table_names(schema=str(schema)))
        assert "eval_runs" not in tables
        assert "eval_results" not in tables
        assert "content_proposals" not in tables
        chat_columns = {
            c["name"] for c in inspector.get_columns("chat_messages", schema=str(schema))
        }
        assert "feedback" not in chat_columns
        assert "latency_ms" not in chat_columns

        upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("MIGRATE_SCHEMA", None)
        else:
            os.environ["MIGRATE_SCHEMA"] = previous

    with tmp_engine.connect() as conn:
        context = MigrationContext.configure(
            conn,
            opts={
                "compare_server_default": True,
                "include_object": _ignore_alembic_version_table,
            },
        )
        assert compare_metadata(context, Base.metadata) == []
