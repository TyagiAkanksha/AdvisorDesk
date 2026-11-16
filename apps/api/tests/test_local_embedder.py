"""Test-author (RED) file for Task A of the local-embeddings brief — `LocalEmbedder`.

Pins the `embed_texts` contract (A2 points 1-8) and `from_settings` (lazy `fastembed` import,
exact constructor kwargs, boot-error wrapping) with hand-written fakes. No network, no real
model, no real `fastembed`. DB-less.
"""

from __future__ import annotations

import logging
import math
import subprocess
import sys
import threading
import time
import types
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from app.config import Settings
from app.services.errors import EmbeddingFailedError

_ENV = [
    "EMBEDDING_PROVIDER",
    "EMBEDDING_DIMENSIONS",
    "LOCAL_EMBEDDING_MODEL",
    "LOCAL_EMBEDDING_QUERY_PREFIX",
    "LOCAL_EMBEDDING_CACHE_DIR",
    "LOCAL_EMBEDDING_OFFLINE",
    "LOCAL_EMBEDDING_THREADS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


class FakeModel:
    """Records calls; returns one `width`-wide vector per document (value = 1-based index)."""

    def __init__(self, width: int = 3, *, as_numpy_like: bool = False) -> None:
        self.width = width
        self.calls: list[tuple[list[str], int | None]] = []
        self.as_numpy_like = as_numpy_like

    def embed(self, documents: Any, batch_size: int | None = None, **_: Any) -> Iterator[Any]:
        self.calls.append((documents, batch_size))
        for i, _doc in enumerate(documents, start=1):
            yield [float(i)] * self.width


def _embedder(model: Any, *, dimensions: int = 5, query_prefix: str = "") -> Any:
    from app.rag.local_embeddings import LocalEmbedder

    return LocalEmbedder(model=model, dimensions=dimensions, query_prefix=query_prefix)


# ---- A2.1 empty input ----


def test_empty_texts_returns_empty_and_does_not_call_model() -> None:
    model = FakeModel()
    assert _embedder(model).embed_texts([]) == []
    assert model.calls == []


# ---- A2.2 query prefix ----


def test_query_input_type_prefixes_every_text() -> None:
    model = FakeModel()
    _embedder(model, query_prefix="Q: ").embed_texts(["a", "b"], input_type="query")
    assert model.calls[0][0] == ["Q: a", "Q: b"]


def test_passage_input_type_leaves_text_unchanged() -> None:
    model = FakeModel()
    _embedder(model, query_prefix="Q: ").embed_texts(["a", "b"], input_type="passage")
    assert model.calls[0][0] == ["a", "b"]


def test_default_input_type_is_passage() -> None:
    model = FakeModel()
    _embedder(model, query_prefix="Q: ").embed_texts(["a"])
    assert model.calls[0][0] == ["a"]


# ---- A2.3 one call, list[str], batch_size=1 ----


def test_model_called_exactly_once_with_list_and_batch_size_one() -> None:
    model = FakeModel()
    _embedder(model).embed_texts(("x", "y", "z"))
    assert len(model.calls) == 1
    documents, batch_size = model.calls[0]
    assert isinstance(documents, list)
    assert documents == ["x", "y", "z"]
    assert batch_size == 1


# ---- A2.4 padding, plain floats, order ----


def test_vectors_are_right_padded_with_zero_to_dimensions_in_order() -> None:
    result = _embedder(FakeModel(width=3), dimensions=5).embed_texts(["a", "b"])
    assert result == [[1.0, 1.0, 1.0, 0.0, 0.0], [2.0, 2.0, 2.0, 0.0, 0.0]]


def test_vector_exactly_dimensions_wide_is_not_padded() -> None:
    result = _embedder(FakeModel(width=5), dimensions=5).embed_texts(["a"])
    assert result == [[1.0] * 5]


def test_returned_values_are_plain_python_lists_of_floats() -> None:
    class ArrayLike:
        """Mimics a numpy row: iterable of non-builtin float scalars, not a list."""

        def __init__(self, values: Sequence[float]) -> None:
            self._values = values

        def __iter__(self) -> Iterator[Any]:
            return iter(self._values)

        def __len__(self) -> int:
            return len(self._values)

        def tolist(self) -> list[float]:
            return list(self._values)

    class Model:
        def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
            for _ in documents:
                yield ArrayLike([1, 2, 3])  # ints must come back as float

    (vector,) = _embedder(Model(), dimensions=4).embed_texts(["a"])
    assert type(vector) is list
    assert vector == [1.0, 2.0, 3.0, 0.0]
    assert all(type(v) is float for v in vector)


def test_zero_padding_preserves_cosine_similarity() -> None:
    a, b = [0.6, 0.8, 0.0], [0.28, 0.96, 0.0]

    class Model:
        def __init__(self) -> None:
            self.rows = iter([a, b])

        def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
            for _ in documents:
                yield next(self.rows)

    pa, pb = _embedder(Model(), dimensions=8).embed_texts(["a", "b"])

    def cos(u: Sequence[float], v: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(u, v, strict=True))
        return dot / (math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(y * y for y in v)))

    assert len(pa) == len(pb) == 8
    assert cos(pa, pb) == pytest.approx(cos(a, b), abs=1e-12)


# ---- A2.5 too-wide vector ----


def test_vector_wider_than_dimensions_raises_naming_both_widths() -> None:
    with pytest.raises(EmbeddingFailedError) as info:
        _embedder(FakeModel(width=7), dimensions=5).embed_texts(["a"])
    assert "7" in str(info.value)
    assert "5" in str(info.value)


# ---- A2.6 count mismatch ----


def test_too_few_vectors_raises_embedding_failed() -> None:
    class ShortModel:
        def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
            yield [1.0, 2.0]

    with pytest.raises(EmbeddingFailedError):
        _embedder(ShortModel(), dimensions=5).embed_texts(["a", "b", "c"])


# ---- A2.7 any model exception -> generic EmbeddingFailedError ----


def test_model_exception_becomes_generic_error_chained_and_logged_not_leaked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_text = "private client question"
    boom = RuntimeError(f"onnx blew up on {secret_text}")

    class RaisingModel:
        def embed(self, documents: Any, batch_size: int | None = None) -> Any:
            raise boom

    with caplog.at_level(logging.WARNING), pytest.raises(EmbeddingFailedError) as info:
        _embedder(RaisingModel()).embed_texts([secret_text])
    assert str(info.value) == "The embedding provider call failed."
    assert secret_text not in str(info.value)
    assert info.value.__cause__ is boom
    assert any(
        r.levelno == logging.WARNING and "onnx blew up" in r.getMessage() for r in caplog.records
    )


def test_exception_raised_mid_iteration_is_also_wrapped() -> None:
    boom = ValueError("mid-iteration failure")

    class LazyRaisingModel:
        def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
            yield [1.0, 2.0]
            raise boom

    with pytest.raises(EmbeddingFailedError) as info:
        _embedder(LazyRaisingModel()).embed_texts(["a", "b"])
    assert str(info.value) == "The embedding provider call failed."
    assert info.value.__cause__ is boom


# ---- A2.8 serialisation lock ----


def test_concurrent_calls_are_serialised_around_the_model_call() -> None:
    state = {"active": 0, "max": 0}
    guard = threading.Lock()

    class ConcurrencyModel:
        def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
            with guard:
                state["active"] += 1
                state["max"] = max(state["max"], state["active"])
            try:
                for _ in documents:
                    time.sleep(0.02)  # widen the race window, incl. during lazy iteration
                    yield [1.0, 2.0]
            finally:
                with guard:
                    state["active"] -= 1

    embedder = _embedder(ConcurrencyModel(), dimensions=3)
    errors: list[BaseException] = []

    def work() -> None:
        try:
            embedder.embed_texts(["a", "b"])
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert state["max"] == 1


# ---- from_settings ----


class _RecordingTextEmbedding:
    instances: list[_RecordingTextEmbedding] = []
    kwargs_seen: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).kwargs_seen.append({"args": args, **kwargs})
        type(self).instances.append(self)

    def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
        for _ in documents:
            yield [0.5] * 384


def _stub_fastembed(monkeypatch: pytest.MonkeyPatch, cls: type) -> None:
    module = types.ModuleType("fastembed")
    module.TextEmbedding = cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)


def test_from_settings_builds_text_embedding_eagerly_with_exact_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.rag.local_embeddings import LocalEmbedder

    class Recorder(_RecordingTextEmbedding):
        instances: list[_RecordingTextEmbedding] = []
        kwargs_seen: list[dict[str, Any]] = []

    _stub_fastembed(monkeypatch, Recorder)
    settings = Settings(
        embedding_provider="local",
        local_embedding_model="some/model",
        local_embedding_cache_dir="/tmp/cache-x",
        local_embedding_threads=3,
        local_embedding_offline=True,
        local_embedding_query_prefix="PFX: ",
        embedding_dimensions=400,
    )

    embedder = LocalEmbedder.from_settings(settings)

    assert Recorder.kwargs_seen == [
        {
            "args": (),
            "model_name": "some/model",
            "cache_dir": "/tmp/cache-x",
            "threads": 3,
            "local_files_only": True,
        }
    ]
    vectors = embedder.embed_texts(["q"], input_type="query")
    assert len(vectors[0]) == 400
    assert vectors[0][:384] == [0.5] * 384 and vectors[0][384:] == [0.0] * 16


def test_from_settings_passes_query_prefix_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.rag.local_embeddings import LocalEmbedder

    seen: list[list[str]] = []

    class Recorder:
        def __init__(self, **_: Any) -> None: ...

        def embed(self, documents: Any, batch_size: int | None = None) -> Iterator[Any]:
            seen.append(list(documents))
            for _ in documents:
                yield [0.1] * 4

    _stub_fastembed(monkeypatch, Recorder)
    settings = Settings(
        embedding_provider="local", local_embedding_query_prefix="PFX: ", embedding_dimensions=8
    )
    LocalEmbedder.from_settings(settings).embed_texts(["hello"], input_type="query")
    assert seen == [["PFX: hello"]]


def test_from_settings_load_failure_is_runtime_error_naming_env_vars_and_chained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.rag.local_embeddings import LocalEmbedder

    boom = ValueError("Could not load model from any source.")

    class Failing:
        def __init__(self, **_: Any) -> None:
            raise boom

    _stub_fastembed(monkeypatch, Failing)
    with pytest.raises(RuntimeError) as info:
        LocalEmbedder.from_settings(Settings(embedding_provider="local"))
    assert "LOCAL_EMBEDDING_MODEL" in str(info.value)
    assert "LOCAL_EMBEDDING_CACHE_DIR" in str(info.value)
    assert info.value.__cause__ is boom


def test_importing_local_embeddings_module_does_not_import_fastembed() -> None:
    code = (
        "import sys\n"
        "import app.rag.local_embeddings\n"
        "import app.rag.embedder_factory\n"
        "assert 'fastembed' not in sys.modules, 'fastembed imported eagerly'\n"
        "assert 'onnxruntime' not in sys.modules, 'onnxruntime imported eagerly'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stderr
