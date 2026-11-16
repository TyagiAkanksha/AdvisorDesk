"""Task C2 (final review I3): eval runs record the embedding model actually used."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.config import Settings

_EVAL_DIR = Path(__file__).resolve().parents[1] / "app" / "eval"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "LOCAL_EMBEDDING_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_effective_model_is_local_model_under_local_provider() -> None:
    settings = Settings(
        embedding_provider="local",
        local_embedding_model="some/local-model",
        embedding_model="text-embedding-3-small",
    )
    assert settings.effective_embedding_model == "some/local-model"


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_effective_model_is_embedding_model_under_remote_providers(provider: str) -> None:
    settings = Settings(
        embedding_provider=provider,  # type: ignore[arg-type]
        embedding_model="remote-embed-x",
        local_embedding_model="some/local-model",
    )
    assert settings.effective_embedding_model == "remote-embed-x"


@pytest.mark.parametrize("filename", ["groundedness.py", "agent_suite.py"])
def test_eval_runs_record_the_effective_embedding_model(filename: str) -> None:
    source = (_EVAL_DIR / filename).read_text()
    assert "embedding_model=settings.effective_embedding_model" in source
    assert not re.search(r"embedding_model=settings\.embedding_model\b", source)
