"""CI mass-skip guard (6R-02, WR-51).

`conftest.py`'s `pytest_collection_modifyitems` skips DB-fixture tests **by
fixture name** when `TEST_DATABASE_URL` is unset — the correct behavior for
local dev without Docker running (CONVENTIONS.md §10). That same behavior is
dangerous in CI: if the job's Postgres service ever fails to wire up
`TEST_DATABASE_URL`, every DB-backed test file would silently skip instead of
failing, and CI would report green with most of the suite never having run.

This test is the tripwire. GitHub Actions sets `CI=true` for every job, so it
asserts only there; a local run without `CI` set skips harmlessly regardless
of whether `TEST_DATABASE_URL` happens to be exported.
"""

from __future__ import annotations

import os

import pytest


def test_ci_must_provide_a_test_database() -> None:
    """Fail in CI (only) when `TEST_DATABASE_URL` is unset — see module docstring."""
    if os.environ.get("CI") != "true":
        pytest.skip("not running in CI; local runs may omit TEST_DATABASE_URL")
    assert os.environ.get("TEST_DATABASE_URL"), (
        "CI must provide a database; 28 DB test files would silently skip"
    )
