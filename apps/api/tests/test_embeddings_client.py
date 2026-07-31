"""Fixer-owned tests for `app.rag.embeddings.OpenAICompatibleEmbedder` (phase-3 task-02 review
round 1).

`tests/test_lifecycle.py` (pinned, untouched) already covers `EmbeddingChunkPipeline` end to end
against a fake `Embedder` — it never constructs a real `OpenAICompatibleEmbedder` or reaches a
network (CONVENTIONS.md §10). This file is the one level down: it exercises the real
`OpenAICompatibleEmbedder` (the real `openai` SDK client) against a fake HTTP transport
(`httpx.MockTransport`), so it's still zero-network, but actually proves what request the SDK
puts on the wire and how `openai.OpenAIError`/a malformed response become `EmbeddingFailedError`.

Covers the reviewer's provider-client findings from phase-3 task-02's round-1 review:
  - F1/I1: `from_settings` applies `Settings.embedding_timeout_seconds`/`embedding_max_retries`
    to the built client (not the SDK's own much larger defaults).
  - F2/M1: a provider that returns fewer vectors than inputs submitted (a truncated batch) fails
    as `EmbeddingFailedError`, not an unhandled `ValueError`/500 further down the pipeline.
  - F5/M5: the actual request body sent to the provider carries `encoding_format: "float"`
    explicitly, not the SDK's silent default `"base64"`.
  - F6/M6: a raw provider failure's detail is logged, not placed in the client-facing
    `EmbeddingFailedError.message` (which the §9 envelope renders verbatim), and the original
    exception is still chained via `from exc`.
  - F3/M2: `app.models.Chunk`'s ndarray-→list normalization also needs to fire on
    SQLAlchemy's `"refresh"` event, not just `"load"` (this file is where every other embedding-
    shape finding from the same review round lives, so the `Chunk.embedding` twin listener joins
    it here rather than in the general-purpose `tests/test_models_schema.py`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from unittest.mock import patch

import httpx
import pytest
from openai import OpenAI
from sqlalchemy.orm import Session

import app.models.chunks as chunks_module
from app.config import Settings
from app.models import Chunk, Content
from app.rag.embeddings import EmbeddingFailedError, OpenAICompatibleEmbedder


def _embedder_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    dimensions: int = 3,
    max_retries: int = 0,
) -> OpenAICompatibleEmbedder:
    """Build a real `OpenAICompatibleEmbedder` wired to a fake HTTP transport — no network.

    `max_retries=0` by default so an error-path test doesn't sit through the SDK's real retry
    backoff; F1's own tests override the client's retry budget directly where that's the point.
    """
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="test-key",
        base_url="https://fake-provider.example/v1",
        http_client=http_client,
        max_retries=max_retries,
    )
    return OpenAICompatibleEmbedder(client=client, model="test-embed-model", dimensions=dimensions)


def _embedding_response(vectors: list[list[float]]) -> httpx.Response:
    """A well-formed `/v1/embeddings` 200 response body carrying `vectors`, in order."""
    data = [
        {"object": "embedding", "index": index, "embedding": vector}
        for index, vector in enumerate(vectors)
    ]
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": data,
            "model": "test-embed-model",
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        },
    )


# ---- F1 (review round 1, finding I1): timeout/retry budget is introspectable on the client ----


def test_from_settings_passes_embedding_timeout_and_max_retries_to_the_client() -> None:
    """`from_settings` must apply `Settings.embedding_timeout_seconds`/`embedding_max_retries` to
    the real `openai.OpenAI` client instead of the SDK's own defaults (`read=600s`,
    `max_retries=2`, i.e. up to ~30 minutes across 3 attempts) — `EmbeddingChunkPipeline` calls
    the embedder inside the same DB transaction it's about to `flush()` into (PRD §4 atomicity),
    so an unbounded budget would hold that write transaction open for the SDK's full timeout.
    """
    settings = Settings(
        nvidia_api_key="test-nvidia-key",
        embedding_timeout_seconds=12.5,
        embedding_max_retries=5,
    )

    embedder = OpenAICompatibleEmbedder.from_settings(settings)

    assert embedder._client.timeout == 12.5
    assert embedder._client.max_retries == 5


def test_from_settings_default_timeout_and_max_retries_match_settings_defaults() -> None:
    """The zero-env-var `Settings()` defaults (30.0s / 2 retries) round-trip onto the client too."""
    settings = Settings()

    embedder = OpenAICompatibleEmbedder.from_settings(settings)

    assert embedder._client.timeout == 30.0
    assert embedder._client.max_retries == 2


# ---- F2 (review round 1, finding M1): a truncated provider batch fails as EmbeddingFailedError --


def test_truncated_batch_response_raises_embedding_failed_error() -> None:
    """A provider returning fewer vectors than inputs submitted (a truncated/short batch) must
    raise `EmbeddingFailedError` here — at the seam that validates the response — instead of
    escaping as an unhandled `ValueError`/500 from `app.rag.pipeline`'s
    `zip(chunk_data, vectors, strict=True)` further down the pipeline.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _embedding_response([[0.1, 0.2, 0.3]])  # 1 vector back, 3 inputs sent below

    embedder = _embedder_with_transport(handler)

    with pytest.raises(EmbeddingFailedError) as exc_info:
        embedder.embed_texts(["one", "two", "three"], input_type="passage")

    message = str(exc_info.value)
    assert "1" in message
    assert "3" in message


def test_matching_batch_response_does_not_raise() -> None:
    """The happy path the F2 fix must not regress: a full-count response still returns cleanly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _embedding_response([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

    embedder = _embedder_with_transport(handler)

    vectors = embedder.embed_texts(["one", "two"], input_type="passage")

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


# ---- F5 (review round 1, finding M5): encoding_format="float" is on the wire request body ----


def test_request_body_carries_encoding_format_float_alongside_input_type_and_truncate() -> None:
    """The actual HTTP request body sent to the provider must pin `encoding_format: "float"`
    (never the SDK's silently-injected default `"base64"`) alongside the existing
    `input_type`/`truncate` NVIDIA NIM extras — a deterministic, provider-agnostic wire shape
    (PRD §7.2).
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _embedding_response([[0.1, 0.2, 0.3]])

    embedder = _embedder_with_transport(handler)

    embedder.embed_texts(["hello"], input_type="passage")

    body = captured["body"]
    assert isinstance(body, dict)
    assert body["encoding_format"] == "float"
    assert body["input_type"] == "passage"
    assert body["truncate"] == "END"


# ---- F6 (review round 1, finding M6): provider error text never reaches .message ----


def test_provider_error_yields_fixed_client_facing_message_not_raw_provider_text() -> None:
    """A raw provider failure (a non-2xx response) must not leak its detail into
    `EmbeddingFailedError`'s message — `app.routes.errors` renders `str(exc)` verbatim into the
    §9 envelope, and this same client is reused on phase-4's public chat path, where a caller
    should never see upstream provider internals.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"error": {"message": "sk-secret-detail-leak", "type": "server_error"}}
        )

    embedder = _embedder_with_transport(handler)

    with pytest.raises(EmbeddingFailedError) as exc_info:
        embedder.embed_texts(["hello"], input_type="passage")

    message = str(exc_info.value)
    assert message == "The embedding provider call failed."
    assert "sk-secret-detail-leak" not in message


def test_provider_error_is_logged_and_chained_via_from_exc(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The provider's raw detail isn't lost, just kept out of the client-facing message: it's
    logged (`logger.warning`) for operators, and the original exception is still chained
    (`raise ... from exc`) so it's visible on `__cause__`/in a traceback.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"error": {"message": "sk-secret-detail-leak", "type": "server_error"}}
        )

    embedder = _embedder_with_transport(handler)

    with caplog.at_level(logging.WARNING, logger="app.rag.embeddings"):
        with pytest.raises(EmbeddingFailedError) as exc_info:
            embedder.embed_texts(["hello"], input_type="passage")

    assert exc_info.value.__cause__ is not None
    assert "sk-secret-detail-leak" in str(exc_info.value.__cause__)
    warnings = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert any("sk-secret-detail-leak" in message for message in warnings)


# ---- F3 (review round 1, finding M2): the ndarray→list normalizer also covers "refresh" ----


def test_refresh_event_also_normalizes_chunk_embedding(db_session: Session) -> None:
    """`session.refresh(chunk)` (or any expired-attribute reload) fires SQLAlchemy's `"refresh"`
    event, a separate hook from `"load"` — the reviewer's probe found the original `"load"`-only
    listener never runs on this path, so a chunk re-read this way could keep a non-`list`
    `.embedding` despite the `"load"` guard. This app's real driver already happens to hand back
    plain `list[float]` on every read (documented in the phase-3 task-02 implementer report), so
    a real refresh here can't by itself distinguish "listener ran" from "driver never produced
    anything but a list anyway" — proven instead by spying on the shared
    `app.models.chunks._normalize_embedding` helper and asserting `session.refresh(chunk)`
    actually invokes it, mirroring the reviewer's probe.
    """
    content = Content(title="Embeddable Refresh", slug="embeddable-refresh")
    db_session.add(content)
    db_session.flush()

    chunk = Chunk(
        content_id=content.id,
        chunk_index=0,
        text="hello world",
        embedding=[(i % 100) / 100.0 for i in range(1024)],
    )
    db_session.add(chunk)
    db_session.flush()
    db_session.expire(chunk)

    with patch.object(
        chunks_module, "_normalize_embedding", wraps=chunks_module._normalize_embedding
    ) as spy:
        db_session.refresh(chunk)

    spy.assert_called()
    assert isinstance(chunk.embedding, list)
    assert len(chunk.embedding) == 1024


def test_refresh_listener_is_registered_on_the_chunk_class() -> None:
    """The `"refresh"` twin is actually wired to `Chunk` via `@event.listens_for` — a direct
    registration check alongside the behavioral proof above, so a future refactor that silently
    drops the decorator (while leaving the function itself intact) is still caught.
    """
    from sqlalchemy import event

    assert event.contains(Chunk, "refresh", chunks_module._normalize_embedding_on_refresh)
    assert event.contains(Chunk, "load", chunks_module._normalize_embedding_on_load)
