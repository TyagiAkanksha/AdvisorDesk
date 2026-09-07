"""Regression tests for `app.seed_paths.seed_data_dir` (fix: containerized seed was broken).

The bug: `app.seed` and `app.eval.groundedness` each computed a repo-root path from
`Path(__file__).resolve().parents[N]` at MODULE scope. Correct on host, but in the API image the
code lives at `/app/app/...`, so `parents[3]`/`parents[4]` went out of range and importing either
module — hence `python -m app.seed` — crashed before running. `seed_data_dir()` replaces that path
math with a `$SEED_DATA_DIR` override (baked into the image at `/app/seed`) plus a host fallback.

These tests pin both branches:
  - env set  → returns exactly that path, no filesystem walk (the container's behavior);
  - env unset → resolves to the real repo-root `seed/`, which must exist and hold the corpus
    (`sample_content/*.md`) and `eval_questions.yaml` (the host-dev behavior);
and assert the two call sites that consume it resolve to existing paths on host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.seed_paths import seed_data_dir


def test_seed_data_dir_prefers_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """With `$SEED_DATA_DIR` set, `seed_data_dir()` returns exactly that path.

    This is the container branch: the image bakes `SEED_DATA_DIR=/app/seed`, so no
    host-relative `parents[...]` walk is ever evaluated (the walk is what crashed on import
    in-container).
    """
    monkeypatch.setenv("SEED_DATA_DIR", "/app/seed")
    assert seed_data_dir() == Path("/app/seed")


def test_seed_data_dir_env_override_is_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    """The override is returned verbatim — not re-resolved against the repo tree."""
    monkeypatch.setenv("SEED_DATA_DIR", "/some/other/seed/location")
    assert seed_data_dir() == Path("/some/other/seed/location")


def test_seed_data_dir_host_fallback_points_at_real_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With `$SEED_DATA_DIR` unset, `seed_data_dir()` resolves to the real repo-root `seed/`.

    The fallback must land on a directory that actually exists and contains the corpus and the
    eval question set — otherwise the host `python -m app.seed` / groundedness harness would read
    from the wrong place.
    """
    monkeypatch.delenv("SEED_DATA_DIR", raising=False)
    resolved = seed_data_dir()
    assert resolved.name == "seed"
    assert resolved.is_dir()

    sample_content = resolved / "sample_content"
    assert sample_content.is_dir()
    assert list(sample_content.glob("*.md")), "expected seed markdown files under sample_content/"
    assert (resolved / "eval_questions.yaml").is_file()


def test_seed_and_eval_call_sites_resolve_on_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two consumers resolve to existing on-host paths via the shared resolver.

    `app.seed._run_from_cli` builds `seed_data_dir() / "sample_content"`; `app.eval.groundedness`
    exposes `_DEFAULT_QUESTIONS_PATH`. Both must exist on host so a real seed/eval run reads the
    committed corpus.
    """
    monkeypatch.delenv("SEED_DATA_DIR", raising=False)

    from app.eval.groundedness import _DEFAULT_QUESTIONS_PATH

    assert (seed_data_dir() / "sample_content").is_dir()
    assert _DEFAULT_QUESTIONS_PATH.is_file()
    assert _DEFAULT_QUESTIONS_PATH.name == "eval_questions.yaml"
