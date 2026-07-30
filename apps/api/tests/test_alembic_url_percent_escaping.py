"""Pins the `%`-escaping technique `conftest.py::tmp_engine` uses to pin the Alembic URL.

`alembic.config.Config` is `configparser`-backed, which treats a bare `%`
as the start of an interpolation token (`%(name)s`) — a percent-encoded
password (routine for Supabase, the default target, e.g. `%40` for `@`)
raises on `set_main_option` unless doubled to `%%` first. No live database
is needed to pin this property; it's a property of `Config` itself, and DB
fixture tests (`tests/conftest.py`) are skipped by fixture name when
`TEST_DATABASE_URL` is unset anyway (CONVENTIONS.md §10) — this test always
runs.
"""

from __future__ import annotations

import pytest
from alembic.config import Config

_PERCENT_ENCODED_URL = "postgresql+psycopg://user:p%40ss@localhost:5432/db"


def test_percent_encoded_url_round_trips_when_escaped() -> None:
    """`database_url.replace("%", "%%")` survives `set_main_option`/`get_main_option` unmodified.

    Mirrors `tests/conftest.py::tmp_engine`'s escape call exactly.
    """
    cfg = Config()

    cfg.set_main_option("sqlalchemy.url", _PERCENT_ENCODED_URL.replace("%", "%%"))

    assert cfg.get_main_option("sqlalchemy.url") == _PERCENT_ENCODED_URL


def test_unescaped_percent_encoded_url_raises_on_set_main_option() -> None:
    """Without the escape, `set_main_option` itself raises — pins WHY the escape exists."""
    cfg = Config()

    with pytest.raises(ValueError, match="invalid interpolation syntax"):
        cfg.set_main_option("sqlalchemy.url", _PERCENT_ENCODED_URL)
