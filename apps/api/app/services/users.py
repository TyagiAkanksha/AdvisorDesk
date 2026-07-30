"""User upsert-by-email service — Google OAuth login lands here (PRD §4.1, §5.1)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.models.schemas.auth import GoogleIdentity


def upsert_from_google(session: Session, identity: GoogleIdentity) -> User:
    """Insert or update a `User` row by email from a Google OAuth `identity`.

    PRD §4.1: soft delete is a tombstone, not a ban — a soft-deleted row
    matching `identity["email"]` is reactivated (`is_deleted` flips back to
    `False`) on the SAME row id rather than inserting a duplicate. Either
    way, `name`/`avatar_url` are refreshed from the fresh identity.

    Deliberately queries by email with no `active_select` filter (unlike
    every other read of `User`): this lookup must see a soft-deleted row so
    it can reactivate it, not hide it (CONVENTIONS.md §3 active_select is
    for "invisible in normal reads" — this is the one legitimate exception,
    by design).

    Flushes to assign a fresh row's id / surface constraint errors eagerly,
    but never commits — the HTTP session dependency (`get_session`) owns
    the transaction boundary (CONVENTIONS.md §3).

    Args:
        session: the request-scoped `Session`.
        identity: the identity Google's OAuth exchange returned.

    Returns:
        The (possibly newly-created) `User` row for `identity["email"]`.
    """
    user = session.execute(select(User).where(User.email == identity["email"])).scalar_one_or_none()
    if user is None:
        user = User(email=identity["email"])
        session.add(user)

    user.name = identity["name"]
    user.avatar_url = identity["avatar_url"]
    user.is_deleted = False
    user.updated_at = datetime.now(UTC)

    session.flush()
    return user
