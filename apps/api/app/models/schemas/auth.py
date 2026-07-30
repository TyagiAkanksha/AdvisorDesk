"""Auth-domain schemas: `/auth/me`'s wire DTO, and the Google-identity shape (PRD §5.1).

`GoogleIdentity` is defined here rather than in `app.auth.oauth` so that
`app.services.users.upsert_from_google` can depend on its shape without
importing `app.auth` — CONVENTIONS.md §2 restricts `app.services` to
`app.models`/`app.config` imports only, while `app.auth` may import
`app.models`. `app.auth.oauth` imports and re-exports `GoogleIdentity` so
`from app.auth.oauth import GoogleIdentity` (the `GoogleOAuthClient`
protocol's declared return type, and the test seam's import in
`tests/auth_helpers.py`) keeps working with a single, non-duplicated
definition.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from pydantic import BaseModel


class GoogleIdentity(TypedDict):
    """The subset of a Google user's profile AdvisorDesk needs (PRD §5.1 callback exchange)."""

    email: str
    name: str | None
    avatar_url: str | None


class MeResponse(BaseModel):
    """`GET /auth/me`'s success body (PRD §5.1): the current admin's identity."""

    id: uuid.UUID
    email: str
    name: str | None
    avatar_url: str | None
