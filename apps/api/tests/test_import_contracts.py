"""Gates-as-tests: import-linter contracts hold (CONVENTIONS.md §2, §10)."""

from __future__ import annotations

import subprocess


def test_lint_imports_clean() -> None:
    """CI = pytest: `uv run lint-imports` must exit 0 (all four §2 contracts kept)."""
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
