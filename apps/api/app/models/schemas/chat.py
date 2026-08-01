"""`POST /public/chat`'s request DTO — the wire shape the client sends (PRD §5.3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """`POST /public/chat`'s request body (PRD §5.3, exact field set).

    `session_id` absent or referencing an unknown session both mean "start a new session" (§5.3)
    — `app.services.chat.get_or_create_session` handles both cases identically once this schema
    has parsed a syntactically valid UUID (or `None`) out of the request body.
    """

    session_id: uuid.UUID | None = None
    message: str
