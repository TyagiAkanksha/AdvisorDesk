"""Per-`(user, client)` OAuth consent records (mcp-oauth plan, task 06;
docs/plans/mcp-oauth/task-06-consent-screen.md; docs/plans/mcp-oauth/DESIGN.md §"Google bridge +
consent").

`OAuthConsent` (`app.models.oauth`, mcp-oauth task 01) has a unique `(user_id, client_id)`
constraint — one row per pair, ever. This module is the only place that reads or writes that
table: `find_active_consent` is `/authorize/continue`'s consent gate ("has this admin already
approved this client?"); `record_consent` is `POST /authorize/decision`'s approve branch, with
revive-or-insert semantics so re-approving a pair updates the existing row's `scope` in place
rather than accumulating a second row for the same pair and tripping the unique constraint.
Consent revocation does not exist (chore-2026-09 closeout item 2): the admin "Disconnect" action
deletes the `OAuthClient` outright, cascading this row away with it
(`app.services.oauth_clients.delete_client`).

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
    """Return the `OAuthConsent` row for `(user_id, client_id)`, or `None` if none exists yet.

    Args:
        session: the caller's `Session`.
        user_id: the authenticated admin `User.id`.
        client_id: the registered `OAuthClient.client_id`.

    Returns:
        The `OAuthConsent` row for this pair, or `None` if this admin has never granted this
        client access — the consent gate reprompts in that case.
    """
    return session.execute(
        select(OAuthConsent).where(
            OAuthConsent.user_id == user_id,
            OAuthConsent.client_id == client_id,
        )
    ).scalar_one_or_none()


def record_consent(
    session: Session, *, user_id: uuid.UUID, client_id: str, scope: str, now: datetime
) -> OAuthConsent:
    """Record an approved consent for `(user_id, client_id)` — update an existing row, or insert.

    `OAuthConsent`'s unique `(user_id, client_id)` constraint means this pair can have AT MOST one
    row, ever — so approving the same pair twice (e.g. a re-authorization after the code/token
    from an earlier grant expired) updates the existing row's `scope` in place rather than
    inserting a second one, which would violate the constraint. `now` is accepted but not stored:
    `OAuthConsent` (`app.models.oauth`) carries `TimestampMixin`'s `created_at` ONLY — a DB-side
    `default now()` set once, at insert — and does NOT use the separate, application-maintained
    `UpdatedAtMixin` (fix round 1, review finding I-2: an earlier version of this docstring wrongly
    claimed an `updated_at` column "set by the DB itself on update"; no such column exists on this
    model). The `now` parameter exists only for symmetry with every other injectable-clock seam in
    this codebase (CONVENTIONS.md §10), so a caller need not special-case this one function — but
    nothing here stores it. Consequence: `created_at` always names the row's ORIGINAL grant, never
    a later re-grant. If a later task needs to show or audit "when was this (re-)granted", that
    needs a new column and migration — out of this task's scope; flagged for the owner, not fixed
    here.

    Args:
        session: the caller's `Session`. Flushed (never committed) so the caller's `get_session`
            dependency owns the commit (CONVENTIONS.md §3).
        user_id: the authenticated admin `User.id` granting consent.
        client_id: the registered `OAuthClient.client_id` being granted access.
        scope: the scope being granted (always `"mcp"` today — the pending request's own `scope`).
        now: the reference "current time" — unused by this function's own writes (see above);
            explicit for the same injectable-clock reasons as every other service in this plan.

    Returns:
        The persisted `OAuthConsent` row — either the existing row for this pair, updated, or a
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
        session.flush()
        return existing

    consent = OAuthConsent(user_id=user_id, client_id=client_id, scope=scope)
    session.add(consent)
    session.flush()
    return consent
