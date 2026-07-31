"""SQLAlchemy ORM models and Pydantic DTO schemas — a pure leaf (CONVENTIONS.md §2).

Importing this package registers every PRD §4 table on `Base.metadata` —
`alembic/env.py` targets `app.models.Base.metadata` and relies on this
package having been imported first so all seven tables are present.
"""

from __future__ import annotations

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin, uuid_pk
from app.models.chat import ChatMessage, ChatSession
from app.models.chunks import Chunk, embedding_column_dims
from app.models.content import Content, ContentTag, Tag
from app.models.users import User

__all__ = [
    "Base",
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "Content",
    "ContentTag",
    "SoftDeleteMixin",
    "Tag",
    "TimestampMixin",
    "UpdatedAtMixin",
    "User",
    "uuid_pk",
    "embedding_column_dims",
]
