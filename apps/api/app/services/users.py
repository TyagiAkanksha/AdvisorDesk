"""User services — Google OAuth upsert and the active-user lookup (PRD §4.1, §5.1, §9).

CONVENTIONS.md §2: `app.services` is the only layer that touches the ORM —
`get_active_user` exists so `app.auth.deps.require_admin` and
`app.routes.auth_routes.auth_me` (the two call sites that used to run
`active_select` directly) go through the service layer instead
(phase-2 task-01 review round 1, finding I4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.models.schemas.auth import GoogleIdentity
from app.services.queries import active_select


def upsert_from_google(session: Session, identity: GoogleIdentity) -> User:
    """Insert or update a `User` row by (normalized) email from a Google OAuth `identity`.

    PRD §4.1: soft delete is a tombstone, not a ban — a soft-deleted row
    matching the normalized email is reactivated (`is_deleted` flips back to
    `False`) on the SAME row id rather than inserting a duplicate. Either
    way, `name`/`avatar_url` are refreshed from the fresh identity.

    Email normalization (phase-2 task-01 review round 1, finding I3):
    `identity["email"]` is normalized (`strip().lower()`) here, unconditionally,
    before it is used for the lookup or a new row's `email`. `app.routes.auth_routes
    .auth_callback` already normalizes the same way for its allowlist check and
    passes the normalized value through — this second normalization is
    defense-in-depth so `upsert_from_google` stays correct (one canonical row
    per email, never a case-variant duplicate) even if a future caller passes
    a raw, differently-cased identity. `name`/`avatar_url` are stored exactly
    as the identity provided them — only the row-identity key (`email`) is
    canonicalized.

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
        The (possibly newly-created) `User` row for the normalized email.
    """
    email = identity["email"].strip().lower()
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email)
        session.add(user)

    user.name = identity["name"]
    user.avatar_url = identity["avatar_url"]
    user.is_deleted = False
    user.updated_at = datetime.now(UTC)

    session.flush()
    return user


def get_active_user(session: Session, user_id: uuid.UUID) -> User | None:
    """Return the active (non-soft-deleted) `User` row for `user_id`, or `None`.

    The shared point-lookup both `app.auth.deps.require_admin` and
    `GET /auth/me` (`app.routes.auth_routes.auth_me`) need — re-run on every
    request via `active_select` so a soft-deleted admin's session cookie
    stops authorizing immediately (PRD §9), never cached from login time.
    Lives here rather than being inlined at either call site because
    CONVENTIONS.md §2 makes `app.services` the only layer that touches the
    ORM.

    Args:
        session: the caller's `Session` — a request-scoped one in `auth_me`,
            a short-lived ad hoc one in `require_admin` (see that module's
            docstring for why it can't share `auth_me`'s).
        user_id: the `User.id` to look up.

    Returns:
        The `User` row if it exists and is not soft-deleted, else `None`.
    """
    return session.execute(active_select(User).where(User.id == user_id)).scalar_one_or_none()
