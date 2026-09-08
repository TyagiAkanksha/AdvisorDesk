"""Per-`(user, client)` OAuth consent records (mcp-oauth plan, task 06;
docs/plans/mcp-oauth/task-06-consent-screen.md; docs/plans/mcp-oauth/DESIGN.md §"Google bridge +
consent").

`OAuthConsent` (`app.models.oauth`, mcp-oauth task 01) has a unique `(user_id, client_id)`
constraint — one row per pair, ever. This module is the only place that reads or writes that
table: `find_active_consent` is `/authorize/continue`'s consent gate ("has this admin already
approved this client?"); `record_consent` is `POST /authorize/decision`'s approve branch, with
revive-or-insert semantics so a REVOKED consent (a later "revoke this app's access" action, not
built by this task) reprompts once and then resumes skipping the page, rather than accumulating a
second row for the same pair and tripping the unique constraint.

CONVENTIONS.md §3: session-first, `flush()` — never `commit()` — the caller (the route's
`get_session` dependency) owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oauth import OAuthConsent


def find_active_consent(
    session: Session, *, user_id: uuid.UUID, client_id: str
) -> OAuthConsent | None:
    """Return the ACTIVE (`revoked_at IS NULL`) `OAuthConsent` row for `(user_id, client_id)`.

    A revoked row (`revoked_at` set) is deliberately NOT returned here — it means "this admin
    granted access once, but no longer has an active grant", which the consent gate treats
    identically to "never granted at all": the page reprompts.

    Args:
        session: the caller's `Session`.
        user_id: the authenticated admin `User.id`.
        client_id: the registered `OAuthClient.client_id`.

    Returns:
        The active `OAuthConsent` row, or `None` if no row exists for this pair or the only one
        that does has been revoked.
    """
    return session.execute(
        select(OAuthConsent).where(
            OAuthConsent.user_id == user_id,
            OAuthConsent.client_id == client_id,
            OAuthConsent.revoked_at.is_(None),
        )
    ).scalar_one_or_none()


def record_consent(
    session: Session, *, user_id: uuid.UUID, client_id: str, scope: str, now: datetime
) -> OAuthConsent:
    """Record an approved consent for `(user_id, client_id)` — revive an existing row, or insert.

    `OAuthConsent`'s unique `(user_id, client_id)` constraint means this pair can have AT MOST one
    row, ever — so approving a client this admin previously revoked must REVIVE that same row
    (`revoked_at` cleared back to `None`, `scope` refreshed) rather than inserting a second one,
    which would violate the constraint. `now` is accepted but not stored: `OAuthConsent` carries no
    separate "approved at" column, only `TimestampMixin`'s own `created_at`/`updated_at` (set by
    the DB itself on insert/update) — the parameter exists for symmetry with every other
    injectable-clock seam in this codebase (CONVENTIONS.md §10) and so a caller need not special-
    case this one function.

    Args:
        session: the caller's `Session`. Flushed (never committed) so the caller's `get_session`
            dependency owns the commit (CONVENTIONS.md §3).
        user_id: the authenticated admin `User.id` granting consent.
        client_id: the registered `OAuthClient.client_id` being granted access.
        scope: the scope being granted (always `"mcp"` today — the pending request's own `scope`).
        now: the reference "current time" — unused by this function's own writes (see above);
            explicit for the same injectable-clock reasons as every other service in this plan.

    Returns:
        The persisted `OAuthConsent` row — either the existing row for this pair, revived, or a
        freshly inserted one.
    """
    del now  # No dedicated timestamp column to stamp; see docstring.

    existing = session.execute(
        select(OAuthConsent).where(
            OAuthConsent.user_id == user_id, OAuthConsent.client_id == client_id
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.scope = scope
        existing.revoked_at = None
        session.flush()
        return existing

    consent = OAuthConsent(user_id=user_id, client_id=client_id, scope=scope, revoked_at=None)
    session.add(consent)
    session.flush()
    return consent
