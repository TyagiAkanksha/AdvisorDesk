"""Task C1 (final review I2): the public chat `message` is capped at 4000 characters.

The local embedder truncates silently, so without a cap an arbitrarily large message is tokenised
inside the embedder lock and sent to the chat model. 4000 accepted, 4001 rejected (422, before any
embedder/LLM call). The route test is DB-backed and skips locally without `TEST_DATABASE_URL`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine

from app.db import make_session_factory
from app.factory import create_app
from app.models.schemas.chat import ChatRequest

_CAP = 4000


def test_schema_accepts_message_of_exactly_4000_chars() -> None:
    assert len(ChatRequest(message="a" * _CAP).message) == _CAP


def test_schema_rejects_message_of_4001_chars() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(message="a" * (_CAP + 1))
    assert any(err["loc"] == ("message",) for err in exc_info.value.errors())


def test_schema_declares_max_length_4000_on_message() -> None:
    schema = ChatRequest.model_json_schema()
    assert schema["properties"]["message"]["maxLength"] == _CAP


class _CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls += 1
        return [[1.0] + [0.0] * 1023 for _ in texts]


class _CountingChatLLM:
    def __init__(self) -> None:
        self.calls = 0

    def stream_answer(self, system: str, question: str, sources: Sequence[object]) -> Iterator[str]:
        self.calls += 1
        yield "unused"


def test_route_rejects_4001_char_message_with_422_before_any_embed_or_llm_call(
    tmp_engine: Engine,
) -> None:
    embedder = _CountingEmbedder()
    chat_llm = _CountingChatLLM()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        chat_llm=chat_llm,
        embedder=embedder,
    )
    client = TestClient(app)

    response = client.post("/api/v1/public/chat", json={"message": "a" * (_CAP + 1)})

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"
    assert embedder.calls == 0
    assert chat_llm.calls == 0
