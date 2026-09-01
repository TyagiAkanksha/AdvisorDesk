"""User services — Google OAuth upsert and the active-user lookup (PRD §4.1, §5.1, §9).

CONVENTIONS.md §2: `app.services` is the only layer that touches the ORM —
`get_active_user` exists so `app.auth.deps.require_admin` and
`app.routes.auth_routes.auth_me` (the two call sites that used to run
`active_select` directly) go through the service layer instead
(phase-2 task-01 review round 1, finding I4).

`bump_session_epoch` (phase-6 task-05, PRD §9 logout revocation) is the write side of the same
pattern: `app.routes.auth_routes.auth_logout` calls it instead of touching `User.session_epoch`
directly, keeping the ORM confined to this layer.

`get_user_by_id` (phase-6 remediation task-03, WR-05 audit logging) exists so
`app.auth.deps.require_admin` can recover the email of a row `get_active_user` just excluded
(soft-deleted rows are invisible to `active_select`) without reaching into the ORM itself — the
one piece of new plumbing this task's "login rejected (soft-deleted)" audit event needs.
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


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    """Return the `User` row for `user_id` regardless of soft-delete state, or `None` if no row
    exists with that id at all.

    Phase-6 remediation task-03 (WR-05 audit logging): `app.auth.deps.require_admin` calls this
    ONLY after `get_active_user` has already returned `None` for the same `user_id`, to recover
    the email of a row that's soft-deleted (not one that never existed) so the "login rejected"
    WARNING can name who was rejected. Deliberately queries with no `active_select` filter —
    mirroring the reasoning `bump_session_epoch` below has always applied to its own lookup
    (which this same change made `bump_session_epoch` delegate to this function, rather than
    running a second, separate copy of the query) — since the whole point is to see the row
    `active_select` was built to hide.

    Args:
        session: the caller's `Session`.
        user_id: the `User.id` to look up.

    Returns:
        The `User` row whether active or soft-deleted, or `None` if no row with this id exists.
    """
    return session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


def bump_session_epoch(session: Session, user_id: uuid.UUID, cookie_epoch: int) -> bool:
    """Increment `User.session_epoch` by 1 for `user_id`, but ONLY if `cookie_epoch` is CURRENT.

    Phase-6 task-05 (PRD §9 logout revocation, review finding t01-M6): every session cookie is
    signed with the `session_epoch` value in effect at issuance
    (`app.auth.sessions.issue_cookie`); once this row moves to N+1, `app.auth.deps.require_admin`
    rejects any cookie still signed at N — including a captured/stolen one — without needing a
    server-side session-store table.

    Fix round 1 (review finding I-1) — WHY the `cookie_epoch == user.session_epoch` guard exists:
    before this fix, `app.routes.auth_routes.auth_logout` bumped the epoch for ANY cookie that
    merely passed `read_session`'s shape/signature checks, with no comparison against the row's
    live epoch at all. That let an already-revoked cookie — one `require_admin` already rejects
    everywhere else as a 401 — retain exactly one privileged, destructive server-side effect: POST
    it to `/auth/logout` again and it silently kills whatever session the admin is CURRENTLY
    using, for the remainder of the stale cookie's 30-day signed lifetime (no browser needed, since
    the cookie value is sent directly and `SameSite=Lax` is not an obstacle to a same-site POST
    replay). A revoked cookie must be as inert here as it is everywhere else. The guard makes that
    literal: only a cookie whose `epoch` still equals the row's CURRENT `session_epoch` — i.e. a
    cookie that is still a live, currently-valid session — is allowed to advance the counter; a
    stale/already-revoked cookie is silently ignored, same as a missing or malformed one.

    A no-op if `user_id` matches no row: `app.routes.auth_routes.auth_logout` calls this
    best-effort from a cookie that already passed `read_session`'s shape checks but whose
    referenced user may since have been hard-deleted or never existed (e.g. a forged-but-validly-
    shaped cookie for an id that never had a row) — logout must stay idempotent-200 either way,
    so this function absorbs that case rather than pushing an existence check onto every caller.
    Deliberately queries by `User.id` with no `active_select` filter (like
    `upsert_from_google`'s lookup): a soft-deleted user's outstanding cookies should still be
    revoked, not silently skipped because the row is hidden from normal reads.

    CONVENTIONS.md §3: `updated_at` is application-maintained, not a DB trigger — touched here
    alongside the epoch bump, same as every other row mutation in this module.

    Phase-6 remediation task-03 (WR-05 audit logging): now returns whether the epoch was actually
    bumped, so `app.routes.auth_routes.auth_logout` can log the outcome (`epoch_bumped=True` /
    `epoch_bumped=False`) without re-deriving the guard's own decision itself.

    Args:
        session: the request-scoped `Session` (`/auth/logout`'s `Depends(get_session)`).
        user_id: the `User.id` read from the (already shape-verified) session cookie.
        cookie_epoch: the `epoch` read from that SAME cookie (`read_session`'s second tuple
            element) — the bump is skipped unless this still equals the row's live
            `session_epoch`.

    Returns:
        `True` if `user_id` matched a row whose `session_epoch` was still `cookie_epoch` (the
        bump happened); `False` if there was no such row, or its epoch had already moved past
        `cookie_epoch` (a stale/already-revoked cookie — the bump is skipped).
    """
    user = get_user_by_id(session, user_id)
    if user is None or user.session_epoch != cookie_epoch:
        return False
    user.session_epoch += 1
    user.updated_at = datetime.now(UTC)
    session.flush()
    return True
