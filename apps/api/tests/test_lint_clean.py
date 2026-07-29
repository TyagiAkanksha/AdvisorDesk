"""Gates-as-tests: the lint/format/type-check tools are clean (CONVENTIONS.md §10)."""

from __future__ import annotations

import subprocess


def test_lint_clean() -> None:
    """CI = pytest: ruff check, ruff format --check, and mypy all exit 0.

    mypy is invoked with no path args so this stays aligned with the
    canonical `files = ["app"]` config in pyproject.toml (CONVENTIONS.md §10).
    """
    check = subprocess.run(
        ["uv", "run", "ruff", "check", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr

    fmt = subprocess.run(
        ["uv", "run", "ruff", "format", "--check", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr

    mypy = subprocess.run(
        ["uv", "run", "mypy"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert mypy.returncode == 0, mypy.stdout + mypy.stderr
