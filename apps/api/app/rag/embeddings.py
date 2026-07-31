"""The `Embedder` seam + the real NVIDIA NIM (OpenAI-compatible) client (PRD §7.2, v1.5).

`app.rag.pipeline.EmbeddingChunkPipeline` depends on `Embedder` only —
never on `OpenAICompatibleEmbedder` directly — so tests exercise the real
pipeline against `FakeEmbedder`/`FailingEmbedder` (`tests/test_lifecycle.py`)
with no live provider call anywhere in the suite. `OpenAICompatibleEmbedder`
is wired exactly once, in `app/main.py` (CONVENTIONS.md §10: external seams
are injectable, never reached for in tests).

The model (`nvidia/nv-embedqa-e5-v5` by default) is asymmetric: publishing
embeds chunk text with `input_type="passage"`; retrieval (phase-4 task-01)
embeds the user's question with `input_type="query"` through this same
`Embedder` contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from openai import OpenAI, OpenAIError

from app.config import Settings
from app.services.errors import EmbeddingFailedError

__all__ = ["Embedder", "EmbeddingFailedError", "OpenAICompatibleEmbedder"]


class Embedder(Protocol):
    """The embedding-provider seam `app.rag.pipeline` depends on.

    Structurally implemented by `OpenAICompatibleEmbedder` (the real NVIDIA
    NIM client) and by `tests/test_lifecycle.py`'s `FakeEmbedder`/
    `FailingEmbedder` — a `Protocol`, not an ABC, so a test fake needs no
    inheritance relationship to satisfy it.
    """

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        """Embed every text in `texts`, in order, in a single provider call.

        Args:
            texts: the chunk texts (publish) or the single user question
                (retrieval) to embed.
            input_type: `"passage"` when embedding chunks at publish time,
                `"query"` when embedding a user question at retrieval time
                (PRD §7.2 — the model is asymmetric).

        Returns:
            One vector per input text, same order as `texts`.

        Raises:
            EmbeddingFailedError: the provider call failed, or a returned
                vector's length does not match the configured embedding
                dimension.
        """
        ...


class OpenAICompatibleEmbedder:
    """The real `Embedder`, built from `Settings` (PRD §7.2, v1.5).

    Talks to NVIDIA NIM's OpenAI-compatible `/v1/embeddings` endpoint via
    the `openai` SDK — that SDK is used purely because it speaks the
    compatible wire protocol against any `base_url` (PRD §7.2: "a provider
    swap never touches code"), not because the provider is actually OpenAI.
    """

    def __init__(self, *, client: OpenAI, model: str, dimensions: int) -> None:
        """Store the already-built SDK client plus the model/dims to embed with.

        Args:
            client: an `openai.OpenAI` client pointed at the provider's
                OpenAI-compatible base URL, already carrying the API key.
            model: the embedding model name (`Settings.embedding_model`).
            dimensions: the expected output vector width
                (`Settings.embedding_dimensions`) — every returned vector is
                checked against this (the drift guard below).
        """
        self._client = client
        self._model = model
        self._dimensions = dimensions

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAICompatibleEmbedder:
        """Build the real client from `Settings` — the one non-test constructor.

        `nvidia_api_key` is allowed to be empty in development
        (`app/main.py`'s not-`is_dev` guard only requires it in production,
        same dev-exempt shape as the `GOOGLE_*` vars) — but the `openai` SDK
        raises `OpenAIError` at *construction* time for a falsy `api_key`
        with no `OPENAI_API_KEY` env var set either, which would crash
        `app.main`'s module-level wiring on every offline dev boot, not just
        fail an actual embedding call. Falling back to a harmless
        `"unset"` placeholder when the setting is empty keeps construction
        boot-safe; a real embedding attempt with a placeholder key still
        fails, correctly, as an `EmbeddingFailedError` at request time —
        "won't work until it's set," never "won't boot."
        """
        api_key = settings.nvidia_api_key.get_secret_value() or "unset"
        client = OpenAI(api_key=api_key, base_url=settings.llm_base_url)
        return cls(
            client=client,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        """Embed `texts` in one batched call (PRD §7.2 "Batch per content item").

        Passes `input_type` straight through (the asymmetric-model pin) plus
        `truncate="END"` (PRD §7.2: "a defense against over-length input")
        via `extra_body`, since neither is a parameter the `openai` SDK's
        `embeddings.create` knows natively — both are NVIDIA NIM-specific
        additions to the OpenAI-compatible request body.

        Raises:
            EmbeddingFailedError: the provider call itself failed (any
                `openai.OpenAIError` — auth, rate limit, connection,
                non-2xx, ...), or a returned vector's length does not match
                `self._dimensions` (a provider/config drift guard: the
                caller asked for `Settings.embedding_dimensions`-dim
                vectors and got something else).
        """
        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=list(texts),
                extra_body={"input_type": input_type, "truncate": "END"},
            )
        except OpenAIError as exc:
            raise EmbeddingFailedError(f"embedding provider call failed: {exc}") from exc

        # The API's documented contract is response-order == request-order,
        # but each item also carries its own `index` — sorting by it is a
        # cheap guard against a provider that ever reorders, so a chunk
        # never silently gets a sibling chunk's vector.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [item.embedding for item in ordered]

        for vector in vectors:
            if len(vector) != self._dimensions:
                raise EmbeddingFailedError(
                    f"embedding provider returned a {len(vector)}-dim vector; expected "
                    f"{self._dimensions} (settings.embedding_dimensions)."
                )

        return vectors
