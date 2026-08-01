"""`POST /public/chat`'s request DTO — the wire shape the client sends (PRD §5.3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """`POST /public/chat`'s request body (PRD §5.3, exact field set).

    `session_id` absent or referencing an unknown session both mean "start a new session" (§5.3)
    — `app.services.chat.get_or_create_session` handles both cases identically once this schema
    has parsed a syntactically valid UUID (or `None`) out of the request body.

    `message` is `min_length=1` plus a whitespace-only rejection (review round 1, finding M-5) —
    mirrors `app.models.schemas.content.ContentCreate.title`'s established two-guard pattern
    exactly: `min_length=1` alone still lets a whitespace-only string (`"   "`) through, since
    Pydantic's length check counts characters, not content. An empty/blank message would otherwise
    still burn an LLM call and a §9 rate-limit slot, and poison phase-7's `report_content_gaps`
    with empty "questions" (probe P7).
    """

    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def _message_not_whitespace_only(cls, value: str) -> str:
        """Reject a message that is empty once leading/trailing whitespace is stripped."""
        if not value.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return value
