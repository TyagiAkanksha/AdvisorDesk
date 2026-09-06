"""Test-author (RED) file for task 6R-14 — the OpenAI-provider wire shape for
`app.rag.embeddings.OpenAICompatibleEmbedder`.

`docs/plans/phase-6-remediation/task-14-openai-provider-swap.md` (P0 production outage: both
pinned NVIDIA models are EOL/410 Gone). Design pin #2: when built for the OpenAI provider,
`embed_texts` must send `dimensions=<configured dims>` and **NO** NVIDIA-specific `extra_body`
(`input_type`/`truncate`) — OpenAI's `/v1/embeddings` REJECTS `input_type`/`truncate` outright
and REQUIRES `dimensions` to produce anything narrower than the model's own default width
(1536 for `text-embedding-3-small`; controller-verified live: `dimensions=1024` returns exactly
1024-dim vectors, a drop-in for the existing `chunks.embedding vector(1024)` column, no
migration). `encoding_format="float"` stays pinned for both providers.

Mirrors `tests/test_embeddings_client.py`'s `_embedder_with_transport`/`_embedding_response`
technique exactly (`httpx.MockTransport`, zero network — CONVENTIONS.md §10) but explicitly
builds the embedder for `provider="openai"`, the counterpart to that file's now-explicit
`provider="nvidia"` default (task 6R-14 pre-authorized pinned edit, same task).

Pinned interface (task-14 brief, test-author scope): `OpenAICompatibleEmbedder.__init__` gains
a `provider` keyword (accepting at least `"openai"`/`"nvidia"`, mirroring `Settings.llm_provider`
`Literal`); `from_settings` resolves the API key via `settings.llm_api_key` (the provider-
selecting property pinned in `tests/test_llm_provider_config.py`) rather than
`settings.nvidia_api_key` directly.

RED (current HEAD, pre-implementation): neither `provider=` (an `__init__` keyword) nor
`llm_provider="openai"` (a `Settings` keyword) exist yet. Every test below fails at
CONSTRUCTION/CALL time — `TypeError: __init__() got an unexpected keyword argument 'provider'`
or `pydantic_core.ValidationError: ... Extra inputs are not permitted` — never at collection
time (nothing here imports a symbol that doesn't exist; `OpenAICompatibleEmbedder`/`Settings`
both already exist today).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from openai import OpenAI

from app.config import Settings
from app.rag.embeddings import OpenAICompatibleEmbedder


def _openai_embedder_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    dimensions: int = 1024,
    max_retries: int = 0,
) -> OpenAICompatibleEmbedder:
    """Build a real `OpenAICompatibleEmbedder` for `provider="openai"`, wired to a fake HTTP
    transport — no network. Mirrors `test_embeddings_client.py::_embedder_with_transport`
    exactly, plus the explicit `provider="openai"` keyword task 6R-14 adds.
    """
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="test-openai-key",
        base_url="https://fake-provider.example/v1",
        http_client=http_client,
        max_retries=max_retries,
    )
    return OpenAICompatibleEmbedder(
        client=client,
        model="text-embedding-3-small",
        dimensions=dimensions,
        provider="openai",
    )


def _embedding_response(vectors: list[list[float]]) -> httpx.Response:
    """A well-formed `/v1/embeddings` 200 response body carrying `vectors`, in order — mirrors
    `test_embeddings_client.py::_embedding_response`.
    """
    data = [
        {"object": "embedding", "index": index, "embedding": vector}
        for index, vector in enumerate(vectors)
    ]
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": data,
            "model": "text-embedding-3-small",
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        },
    )


# ---- Design pin #2: dimensions present, no extra_body/input_type/truncate ----------------------


def test_openai_request_body_carries_model_input_encoding_format_and_dimensions_only() -> None:
    """The actual HTTP request body for `provider="openai"` must be EXACTLY `{"model", "input",
    "encoding_format", "dimensions"}` — `dimensions=1024` present (OpenAI defaults to the
    model's own 1536 width without it) and NO NVIDIA-specific `input_type`/`truncate` keys
    anywhere in the body (OpenAI's `/v1/embeddings` REJECTS both as unknown parameters).
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _embedding_response([[0.1] * 1024])

    embedder = _openai_embedder_with_transport(handler, dimensions=1024)

    embedder.embed_texts(["hello"], input_type="passage")

    body = captured["body"]
    assert isinstance(body, dict)
    assert set(body.keys()) == {"model", "input", "encoding_format", "dimensions"}
    assert body["model"] == "text-embedding-3-small"
    assert body["input"] == ["hello"]
    assert body["encoding_format"] == "float"
    assert body["dimensions"] == 1024
    assert "input_type" not in body
    assert "truncate" not in body


def test_openai_request_ignores_the_input_type_argument_regardless_of_value() -> None:
    """`embed_texts`'s `input_type` PARAMETER stays accepted for interface compatibility with the
    NVIDIA branch (so callers — `app.rag.retrieval`/`app.rag.pipeline` — never need their own
    provider-aware branch), but for `provider="openai"` it must NEVER reach the wire, whether
    `"passage"` (publish time) or `"query"` (retrieval time) is passed — OpenAI's embedding model
    is symmetric; the asymmetric input_type distinction is NVIDIA-branch-specific (task-14
    brief).
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _embedding_response([[0.2] * 1024])

    embedder = _openai_embedder_with_transport(handler, dimensions=1024)

    embedder.embed_texts(["a question"], input_type="query")

    body = captured["body"]
    assert isinstance(body, dict)
    assert "input_type" not in body
    assert "truncate" not in body


def test_openai_embed_texts_still_returns_validated_vectors_in_order() -> None:
    """The response-count + per-vector-dim validation at the seam is UNCHANGED by the provider
    branch (task-14 design pin #2: "the response-count + per-vector-dim validation at the seam
    is unchanged") — the happy path still returns clean, ordered vectors for `provider="openai"`.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _embedding_response([[0.1] * 1024, [0.2] * 1024])

    embedder = _openai_embedder_with_transport(handler, dimensions=1024)

    vectors = embedder.embed_texts(["one", "two"], input_type="passage")

    assert vectors == [[0.1] * 1024, [0.2] * 1024]


# ---- from_settings: resolves the OpenAI key via settings.llm_api_key ---------------------------


def test_from_settings_uses_the_openai_key_when_provider_is_openai() -> None:
    """Design pin #2: `from_settings` builds the client with `settings.llm_api_key` — under the
    default `llm_provider="openai"`, that must be `settings.openai_api_key`, NOT
    `settings.nvidia_api_key` (task-14: "the credential field `nvidia_api_key`... must pick up
    the OpenAI key" — via the new `llm_api_key` property, not by repurposing the old field name).
    """
    settings = Settings(
        llm_provider="openai",
        openai_api_key="sk-test-openai-key",
        nvidia_api_key="nvapi-should-not-be-used",
    )

    embedder = OpenAICompatibleEmbedder.from_settings(settings)

    assert embedder._client.api_key == "sk-test-openai-key"


def test_from_settings_falls_back_to_the_nvidia_key_when_provider_is_nvidia() -> None:
    """The back-compat branch: `llm_provider="nvidia"` still resolves the client's API key to
    `settings.nvidia_api_key`, exactly as every embedding call site behaved before this task.
    """
    settings = Settings(
        llm_provider="nvidia",
        openai_api_key="sk-should-not-be-used",
        nvidia_api_key="nvapi-test-key",
    )

    embedder = OpenAICompatibleEmbedder.from_settings(settings)

    assert embedder._client.api_key == "nvapi-test-key"


def test_from_settings_falls_back_to_unset_api_key_when_openai_api_key_is_empty() -> None:
    """Dev-mode boot-safety, extended to the OpenAI branch (mirrors
    `test_embeddings_client.py`'s existing NVIDIA-shape boot-safety pin, and task-14 design pin
    #1: "The empty-key... boot-safety fallback pattern stays"): an empty `openai_api_key` under
    the default `llm_provider="openai"` must not crash `from_settings` — the `openai` SDK raises
    at *construction* time for a falsy `api_key` with no `OPENAI_API_KEY` env var either, which
    would crash `app.main`'s module-level wiring on every offline dev boot.
    """
    settings = Settings(llm_provider="openai", openai_api_key="")

    embedder = OpenAICompatibleEmbedder.from_settings(settings)

    assert embedder._client.api_key == "unset"


def test_from_settings_uses_the_openai_default_model_and_dimensions() -> None:
    """A zero-env-var `Settings()` (defaults now OpenAI, task-14 design pin #1) round-trips onto
    the embedder built from it: `text-embedding-3-small` at 1024 dims.
    """
    embedder = OpenAICompatibleEmbedder.from_settings(Settings())

    assert embedder._model == "text-embedding-3-small"
    assert embedder._dimensions == 1024
