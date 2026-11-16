"""Task C3 (final review m4): `app.main` boots under the exact production local-embedding config.

`ENVIRONMENT=production`, `LLM_PROVIDER=anthropic`, a dummy `ANTHROPIC_API_KEY`, empty
`OPENAI_API_KEY`, `EMBEDDING_PROVIDER=local`, and a stub `fastembed` in `sys.modules` (the real
library is never imported). Reuses `test_main_guard.py`'s `_VALID_ENV`/`_reload_main`.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest

from app.rag.local_embeddings import LocalEmbedder
from tests.test_main_guard import _reload_main


class _StubTextEmbedding:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
        for _ in documents:
            yield [0.5] * 384


@pytest.fixture(autouse=True)
def _isolate_main(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    module = types.ModuleType("fastembed")
    module.TextEmbedding = _StubTextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)
    yield
    sys.modules.pop("app.main", None)


def test_main_boots_in_production_with_local_embeddings_and_no_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = _reload_main(
        monkeypatch,
        {
            "ENVIRONMENT": "production",
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "test-anthropic-api-key",
            "OPENAI_API_KEY": "",
            "EMBEDDING_PROVIDER": "local",
        },
    )

    assert isinstance(main.embedder, LocalEmbedder)
