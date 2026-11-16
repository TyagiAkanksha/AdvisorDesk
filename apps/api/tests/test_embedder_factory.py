"""Test-author (RED) file for Task A of the local-embeddings brief — `build_embedder` (A3/A4).

DB-less, no network, no real `fastembed` (stubbed in `sys.modules`).
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.rag.embeddings import OpenAICompatibleEmbedder

_API_ROOT = Path(__file__).resolve().parent.parent

_ENV = [
    "LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "OPENAI_API_KEY",
    "NVIDIA_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "LLM_BASE_URL",
    "EMBEDDING_DIMENSIONS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def _stub_fastembed(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    class TextEmbedding:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs)

        def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
            for _ in documents:
                yield [0.0] * 384

    module = types.ModuleType("fastembed")
    module.TextEmbedding = TextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)
    return seen


def test_build_embedder_local_returns_local_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.rag.embedder_factory import build_embedder
    from app.rag.local_embeddings import LocalEmbedder

    seen = _stub_fastembed(monkeypatch)
    embedder = build_embedder(Settings(embedding_provider="local"))
    assert isinstance(embedder, LocalEmbedder)
    assert len(seen) == 1


def test_build_embedder_openai_returns_openai_compatible_embedder() -> None:
    from app.rag.embedder_factory import build_embedder

    embedder = build_embedder(Settings(embedding_provider="openai", openai_api_key="sk-x"))
    assert isinstance(embedder, OpenAICompatibleEmbedder)


def test_build_embedder_nvidia_returns_openai_compatible_embedder() -> None:
    from app.rag.embedder_factory import build_embedder

    embedder = build_embedder(
        Settings(llm_provider="nvidia", embedding_provider="nvidia", nvidia_api_key="nv-x")
    )
    assert isinstance(embedder, OpenAICompatibleEmbedder)


def test_build_embedder_default_settings_is_openai_and_never_loads_fastembed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.rag.embedder_factory import build_embedder

    monkeypatch.delitem(sys.modules, "fastembed", raising=False)
    assert isinstance(build_embedder(Settings()), OpenAICompatibleEmbedder)
    assert "fastembed" not in sys.modules


def test_openai_compatible_embedder_refuses_local_provider() -> None:
    with pytest.raises(ValueError) as info:
        OpenAICompatibleEmbedder.from_settings(Settings(embedding_provider="local"))
    assert "EMBEDDING_PROVIDER=local" in str(info.value)
    assert "build_embedder" in str(info.value)


# ---- A4: call-site pins (source scan) ----


def _python_files() -> list[Path]:
    files = [*(_API_ROOT / "app").rglob("*.py"), *(_API_ROOT / "scripts").rglob("*.py")]
    return [f for f in files if f.is_file()]


def test_only_embeddings_and_factory_call_openai_embedder_from_settings() -> None:
    allowed = {
        _API_ROOT / "app" / "rag" / "embeddings.py",
        _API_ROOT / "app" / "rag" / "embedder_factory.py",
    }
    files = _python_files()
    assert files, "source scan found no files; wrong root?"
    offenders = [
        str(f.relative_to(_API_ROOT))
        for f in files
        if f not in allowed and "OpenAICompatibleEmbedder.from_settings(" in f.read_text()
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "relative",
    [
        "app/main.py",
        "app/seed.py",
        "app/eval/groundedness.py",
        "app/eval/agent_suite.py",
        "scripts/reembed.py",
    ],
)
def test_call_site_uses_build_embedder(relative: str) -> None:
    assert "build_embedder" in (_API_ROOT / relative).read_text()
