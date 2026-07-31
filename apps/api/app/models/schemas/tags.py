"""Tag DTOs — `GET /tags`'s wire shape (PRD §5.2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class TagWithCount(BaseModel):
    """One non-deleted tag plus its usage count over non-deleted content (PRD §5.2)."""

    id: uuid.UUID
    name: str
    count: int
