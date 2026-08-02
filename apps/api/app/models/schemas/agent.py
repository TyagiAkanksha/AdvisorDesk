"""`POST /agent/chat`'s request DTO — the wire shape the admin frontend sends (PRD §5.4).

`AgentChatRequest.messages` is the client-resent conversation history, oldest first, the last
element being the new user turn (§5.4: "the admin frontend holds conversation history in
component state and resends it each request"). Unlike `app.models.schemas.chat.ChatRequest`
(client chat), there is no `session_id` here at all — the endpoint is stateless by design (§5.4,
§12): the server persists nothing, so there is no session to reference.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    """One turn in the resent history: `role` is `"user"` or `"assistant"` (§5.4 exact shape)."""

    role: Literal["user", "assistant"]
    content: str


class AgentChatRequest(BaseModel):
    """`POST /agent/chat`'s request body (PRD §5.4): `{messages: [{role, content}]}`.

    `messages` requires at least one element — the new user turn `run_agent` (`app.agent.loop`)
    answers.
    """

    messages: list[AgentMessage] = Field(min_length=1)
