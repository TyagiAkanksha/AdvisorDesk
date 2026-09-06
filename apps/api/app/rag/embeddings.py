"""The `Embedder` seam + the real OpenAI-compatible embedding client (PRD §7.2, v1.6).

`app.rag.pipeline.EmbeddingChunkPipeline` depends on `Embedder` only —
never on `OpenAICompatibleEmbedder` directly — so tests exercise the real
pipeline against `FakeEmbedder`/`FailingEmbedder` (`tests/test_lifecycle.py`)
with no live provider call anywhere in the suite. `OpenAICompatibleEmbedder`
is wired exactly once, in `app/main.py` (CONVENTIONS.md §10: external seams
are injectable, never reached for in tests).

v1.6 (task 6R-14, production-outage remediation): the default provider is
now OpenAI (`text-embedding-3-small`, symmetric) — both NVIDIA NIM models
this app was pinned to went end-of-life (410 Gone) 2026-08-25/26.
`Settings.llm_provider`/`Settings.llm_api_key` (config.py) select which
provider `from_settings` builds a client for; `__init__`'s `provider`
keyword records that choice on the instance so `embed_texts` can branch on
it. The NVIDIA branch is asymmetric — publishing embeds chunk text with
`input_type="passage"`; retrieval embeds the user's question with
`input_type="query"` — but OpenAI's embedding model is symmetric, so
`input_type` is accepted (interface compatibility with the NVIDIA branch —
callers never need their own provider-aware branch) but never reaches the
OpenAI wire request.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal, Protocol

from openai import OpenAI, OpenAIError

from app.config import Settings
from app.services.errors import EmbeddingFailedError

logger = logging.getLogger(__name__)

__all__ = ["Embedder", "EmbeddingFailedError", "OpenAICompatibleEmbedder"]


class Embedder(Protocol):
    """The embedding-provider seam `app.rag.pipeline` depends on.

    Structurally implemented by `OpenAICompatibleEmbedder` (the real
    OpenAI-compatible client) and by `tests/test_lifecycle.py`'s `FakeEmbedder`/
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
    """The real `Embedder`, built from `Settings` (PRD §7.2, v1.6).

    Talks to an OpenAI-compatible `/v1/embeddings` endpoint via the `openai`
    SDK — that SDK is used purely because it speaks the compatible wire
    protocol against any `base_url` (PRD §7.2: "a provider swap never
    touches code"). Since v1.6 (task 6R-14) that endpoint is OpenAI's own by
    default; `provider="nvidia"` still selects NVIDIA NIM's compatible
    endpoint as a back-compat branch.
    """

    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        dimensions: int,
        provider: Literal["openai", "nvidia"] = "openai",
    ) -> None:
        """Store the already-built SDK client plus the model/dims to embed with.

        Args:
            client: an `openai.OpenAI` client pointed at the provider's
                OpenAI-compatible base URL, already carrying the API key.
            model: the embedding model name (`Settings.embedding_model`).
            dimensions: the expected output vector width
                (`Settings.embedding_dimensions`) — every returned vector is
                checked against this (the drift guard below).
            provider: which wire shape `embed_texts` sends (v1.6, task
                6R-14) — `"openai"` (the default) sends `dimensions` and no
                `extra_body`; `"nvidia"` keeps the original NVIDIA NIM shape
                (`extra_body={"input_type", "truncate"}`, no `dimensions`).
                Mirrors `Settings.llm_provider`'s own values, so
                `from_settings` passes it straight through with no
                translation.
        """
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._provider = provider

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAICompatibleEmbedder:
        """Build the real client from `Settings` — the one non-test constructor.

        Reads the API key via `settings.llm_api_key` (v1.6, task 6R-14) —
        `openai_api_key` under the default `llm_provider="openai"`, else
        `nvidia_api_key` — rather than a hardcoded field name, so the
        provider swap is config-only. The selected key is allowed to be
        empty in development (`app/main.py`'s not-`is_dev` guard only
        requires the active provider's key in production, same dev-exempt
        shape as the `GOOGLE_*` vars) — but the `openai` SDK raises
        `OpenAIError` at *construction* time for a falsy `api_key` with no
        `OPENAI_API_KEY`/`NVIDIA_API_KEY` env var set either, which would
        crash `app.main`'s module-level wiring on every offline dev boot,
        not just fail an actual embedding call. Falling back to a harmless
        `"unset"` placeholder when the setting is empty keeps construction
        boot-safe; a real embedding attempt with a placeholder key still
        fails, correctly, as an `EmbeddingFailedError` at request time —
        "won't work until it's set," never "won't boot."

        `timeout=settings.embedding_timeout_seconds` and
        `max_retries=settings.embedding_max_retries` replace the `openai`
        SDK's own defaults (`read=600s`, `max_retries=2`) — review round 1,
        finding I1: this pipeline calls the embedder inside the same DB
        transaction it's about to `flush()` into (PRD §4 atomicity), so an
        unbounded client budget would hold that write transaction open for
        up to ~30 minutes against a stalled provider, and phase-4 reuses
        this same client on the public chat path where first-token latency
        matters.
        """
        api_key = settings.llm_api_key.get_secret_value() or "unset"
        client = OpenAI(
            api_key=api_key,
            base_url=settings.llm_base_url,
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )
        return cls(
            client=client,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            provider=settings.llm_provider,
        )

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        """Embed `texts` in one batched call (PRD §7.2 "Batch per content item").

        The request body branches on `self._provider` (v1.6, task 6R-14):

          - `"nvidia"`: passes `input_type` straight through (the
            asymmetric-model pin) plus `truncate="END"` (PRD §7.2: "a
            defense against over-length input") via `extra_body`, since
            neither is a parameter the `openai` SDK's `embeddings.create`
            knows natively — both are NVIDIA NIM-specific additions to the
            OpenAI-compatible request body. No `dimensions` is sent (the
            model has a single fixed output width).
          - `"openai"`: sends `dimensions=self._dimensions` instead — the
            model's own default output width is wider (1536 for
            `text-embedding-3-small`) than the `chunks.embedding` column
            (1024), so `dimensions` must be requested explicitly to get a
            drop-in vector. `input_type` is accepted as a parameter
            (interface compatibility with the NVIDIA branch) but NEVER
            reaches the wire — OpenAI's `/v1/embeddings` REJECTS unknown
            parameters, and the model is symmetric so the distinction is
            meaningless to it. No `extra_body` is sent at all.

        `encoding_format="float"` is passed explicitly either way (review
        round 1, finding M5): left unset, the SDK silently requests
        `"base64"` and decodes it back client-side, a non-deterministic wire
        shape for a call PRD §7.2 promises stays "provider-agnostic" —
        pinning `"float"` keeps the actual HTTP request body plain JSON
        floats.

        The response is validated once, completely, at this seam: every
        returned vector's count and every vector's dimension are checked
        before any is handed back, so no partially-validated response ever
        reaches the caller.

        Raises:
            EmbeddingFailedError: the provider call itself failed (any
                `openai.OpenAIError` — auth, rate limit, connection,
                non-2xx, ...); the provider returned a different number of
                vectors than `texts` submitted (review round 1, finding M1 —
                a truncated/short batch response, left unchecked, previously
                escaped as an unhandled `ValueError` from `zip(...,
                strict=True)` in `app.rag.pipeline`); or a returned vector's
                length does not match `self._dimensions` (a provider/config
                drift guard: the caller asked for
                `Settings.embedding_dimensions`-dim vectors and got
                something else). The client-facing message is always a
                fixed, generic string (review round 1, finding M6) — never
                the raw provider exception text, which is logged instead.
        """
        try:
            if self._provider == "openai":
                response = self._client.embeddings.create(
                    model=self._model,
                    input=list(texts),
                    encoding_format="float",
                    dimensions=self._dimensions,
                )
            else:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=list(texts),
                    encoding_format="float",
                    extra_body={"input_type": input_type, "truncate": "END"},
                )
        except OpenAIError as exc:
            # Review round 1, finding M6: the provider's raw exception text
            # (which can carry request/response detail not meant for an
            # end user — this client is reused on phase-4's public chat
            # path) is logged for operators, never placed in
            # `EmbeddingFailedError.message`/the §9 envelope; `from exc`
            # still chains it into the traceback for local debugging.
            logger.warning("embedding provider call failed: %s", exc)
            raise EmbeddingFailedError("The embedding provider call failed.") from exc

        # The API's documented contract is response-order == request-order,
        # but each item also carries its own `index` — sorting by it is a
        # cheap guard against a provider that ever reorders, so a chunk
        # never silently gets a sibling chunk's vector.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [item.embedding for item in ordered]

        # Review round 1, finding M1: a provider that silently truncates a
        # batch (fewer embeddings than inputs) must fail here, explicitly,
        # as `EmbeddingFailedError` — not escape as a raw `ValueError` from
        # `app.rag.pipeline`'s `zip(chunk_data, vectors, strict=True)`,
        # which the §9 envelope has no mapping for (an unhandled 500).
        if len(vectors) != len(texts):
            raise EmbeddingFailedError(
                f"embedding provider returned {len(vectors)} vector(s) for "
                f"{len(texts)} input text(s)."
            )

        for vector in vectors:
            if len(vector) != self._dimensions:
                raise EmbeddingFailedError(
                    f"embedding provider returned a {len(vector)}-dim vector; expected "
                    f"{self._dimensions} (settings.embedding_dimensions)."
                )

        return vectors
