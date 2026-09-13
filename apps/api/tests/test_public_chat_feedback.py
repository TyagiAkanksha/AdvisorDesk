"""`POST /public/chat/{message_id}/feedback` pins (phase-9 task-02, DESIGN §A/D2)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import make_session_factory
from app.factory import create_app
from app.models import ChatMessage, ChatSession

_PATH = "/api/v1/public/chat/{message_id}/feedback"


def _build_client(tmp_engine: Engine) -> TestClient:
    return TestClient(create_app(session_factory=make_session_factory(tmp_engine)))


def _seed_exchange(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert one user + one assistant row; return `(assistant_id, user_id)`."""
    chat_session = ChatSession()
    session.add(chat_session)
    session.flush()
    user = ChatMessage(session_id=chat_session.id, role="user", content="What about RSUs?")
    assistant = ChatMessage(
        session_id=chat_session.id,
        role="assistant",
        content="RSUs are taxed as ordinary income at vest.",
        citations=[],
        retrieval_found=True,
        top_similarity=0.8,
    )
    session.add_all([user, assistant])
    session.flush()
    session.commit()
    return assistant.id, user.id


def test_thumbs_up_returns_204_and_persists_plus_one(
    tmp_engine: Engine, db_session: Session
) -> None:
    assistant_id, _user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    response = client.post(_PATH.format(message_id=assistant_id), json={"value": 1})

    assert response.status_code == 204
    assert response.content == b""
    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, assistant_id)
        assert row is not None and row.feedback == 1


def test_thumbs_down_then_up_keeps_the_last_value(tmp_engine: Engine, db_session: Session) -> None:
    assistant_id, _user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    assert client.post(_PATH.format(message_id=assistant_id), json={"value": -1}).status_code == 204
    assert client.post(_PATH.format(message_id=assistant_id), json={"value": 1}).status_code == 204

    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, assistant_id)
        assert row is not None and row.feedback == 1


def test_unknown_message_id_returns_404_envelope(tmp_engine: Engine) -> None:
    client = _build_client(tmp_engine)

    response = client.post(_PATH.format(message_id=uuid.uuid4()), json={"value": 1})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_user_role_message_id_returns_404_and_writes_nothing(
    tmp_engine: Engine, db_session: Session
) -> None:
    _assistant_id, user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    response = client.post(_PATH.format(message_id=user_id), json={"value": -1})

    assert response.status_code == 404
    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, user_id)
        assert row is not None and row.feedback is None


def test_values_other_than_plus_or_minus_one_are_422(
    tmp_engine: Engine, db_session: Session
) -> None:
    assistant_id, _user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    for body in ({"value": 0}, {"value": 5}, {"value": "up"}, {}):
        response = client.post(_PATH.format(message_id=assistant_id), json=body)
        assert response.status_code == 422, body

    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, assistant_id)
        assert row is not None and row.feedback is None


def test_non_uuid_message_id_is_422(tmp_engine: Engine) -> None:
    client = _build_client(tmp_engine)

    response = client.post("/api/v1/public/chat/not-a-uuid/feedback", json={"value": 1})

    assert response.status_code == 422
