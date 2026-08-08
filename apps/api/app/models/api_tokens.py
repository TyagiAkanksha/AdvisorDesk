"""`ApiToken` ORM model — bearer tokens for the MCP endpoint (PRD §3, §9; phase-6 task-04).

A deployed Claude connector can send an `Authorization: Bearer <token>` header but never the
admin session cookie — `scripts/mint_mcp_token.py` mints rows here, `app.auth.tokens.
resolve_bearer_token` resolves them back to the same `AdminPrincipal` shape `require_admin`
produces from a cookie (`app.mcp.server._AdminGatedMcpApp.__call__` gates on either).

Task-04 brief, design ruling: composes ONLY `TimestampMixin`, like the append-only tables
(`content_tags`, `chunks`, `chat_sessions`, `chat_messages`) — PRD §4.1 scopes `SoftDeleteMixin`
to `users`/`content`/`tags` specifically, and revocation here is an honest hard `DELETE` via
`scripts/mint_mcp_token.py --revoke`, with no restore path (unlike a soft-deleted `User`/
`Content`/`Tag` row, a revoked token is gone for good).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class ApiToken(Base, TimestampMixin):
    """A bearer token minted for one `User` (the token's owner/actor for every MCP call it makes).

    `token_hash` is the ONLY thing ever stored — `hashlib.sha256(raw.encode()).hexdigest()` of
    the full `"adk_" + secrets.token_urlsafe(32)` raw token (`app.auth.tokens.mint_token`). The
    raw token itself exists only transiently, in the mint script's one-time stdout output — never
    written to any row, log, or column here.
    """

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
