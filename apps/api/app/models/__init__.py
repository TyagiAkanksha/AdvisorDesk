"""SQLAlchemy ORM models and Pydantic DTO schemas — a pure leaf (CONVENTIONS.md §2).

Importing this package registers every PRD §4 table, plus `api_tokens`
(phase-6 task-04, MCP bearer auth — not a PRD §4 table itself) and the four
mcp-oauth plan tables (task-01: `oauth_clients`, `oauth_authorization_codes`,
`oauth_refresh_tokens`, `oauth_consents` — also not PRD §4 tables), on
`Base.metadata` — `alembic/env.py` targets `app.models.Base.metadata` and
relies on this package having been imported first so all twelve tables are
present.
"""

from __future__ import annotations

from app.models.api_tokens import ApiToken
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin, uuid_pk
from app.models.chat import ChatMessage, ChatSession
from app.models.chunks import Chunk, embedding_column_dims
from app.models.content import Content, ContentTag, Tag
from app.models.oauth import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthRefreshToken,
)
from app.models.users import User

__all__ = [
    "ApiToken",
    "Base",
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "Content",
    "ContentTag",
    "OAuthAuthorizationCode",
    "OAuthClient",
    "OAuthConsent",
    "OAuthRefreshToken",
    "SoftDeleteMixin",
    "Tag",
    "TimestampMixin",
    "UpdatedAtMixin",
    "User",
    "uuid_pk",
    "embedding_column_dims",
]
