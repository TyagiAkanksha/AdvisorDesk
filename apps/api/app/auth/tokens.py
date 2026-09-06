"""Bearer-token minting and resolution for MCP connector auth (PRD §3, §9; phase-6 task-04).

A deployed Claude connector can send an `Authorization: Bearer <token>` header but never the
admin session cookie `app.auth.sessions`/`app.auth.deps.require_admin` rely on — this module is
the bearer-side counterpart: `mint_token()` is the one place a raw token/hash pair is ever
generated (`scripts/mint_mcp_token.py` is the only caller, at token-creation time);
`resolve_bearer_token()` is the one place a raw token from an incoming request is turned back
into the SAME `AdminPrincipal` shape `require_admin` produces from a cookie, so every downstream
consumer (actor stamping on write tools, PRD §4.1) stays ignorant of which auth path a request
came in on.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import AdminPrincipal
from app.config import Settings
from app.models.api_tokens import ApiToken
from app.services.users import get_active_user

logger = logging.getLogger(__name__)

_TOKEN_PREFIX = "adk_"


def mint_token() -> tuple[str, str]:
    """Generate one new bearer token: `(raw_token, token_hash)`.

    `raw_token` is exactly `"adk_" + secrets.token_urlsafe(32)` (task-04 brief's pinned format) —
    `secrets.token_urlsafe` is CSPRNG-backed, the same guarantee session cookies already rely on
    (`app.auth.sessions`). `token_hash` is `hashlib.sha256(raw_token.encode()).hexdigest()`: the
    ONLY form ever persisted (`ApiToken.token_hash`) — the raw value is the caller's
    responsibility to store (the mint script prints it once and never again); this module itself
    never writes it anywhere.

    Returns:
        `(raw_token, token_hash)` — the caller decides what to do with each: `raw_token` is shown
        to the operator once, `token_hash` is the row's persisted value.
    """
    raw_token = _TOKEN_PREFIX + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def resolve_bearer_token(
    session: Session, raw_token: str, settings: Settings
) -> AdminPrincipal | None:
    """Resolve a raw bearer token to the `AdminPrincipal` of the `User` who owns it, or `None`.

    Hashes `raw_token` the same way `mint_token()` does, looks up the `ApiToken` row by
    `token_hash` (never by comparing raw values), then loads the owning `User` through
    `app.services.users.get_active_user` — the same active-row re-check `require_admin` performs
    on every request from a cookie, so a soft-deleted admin's tokens stop authenticating the
    instant the account is deactivated, not just at next login (PRD §9).

    Phase-6 remediation task-03 (WR-02, migration 0005): also rejects (returns `None`, exactly
    like an unknown token — see below) a well-formed, known token whose `session_epoch` no longer
    matches its owner's CURRENT `User.session_epoch` — i.e. one revoked by a since-run
    `/auth/logout` (`app.services.users.bump_session_epoch`). The epoch compare stays INSIDE this
    function's existing "never raises, returns `None`" contract rather than raising directly, so
    the caller (`app.mcp.server._resolve_bearer_principal`'s existing `if principal is None: raise
    AuthRequiredError(...)`) produces the byte-identical 401 envelope for "revoked" as it already
    does for "unknown" — no new wire surface, no oracle distinguishing the two from outside.

    Phase-6 remediation task-09 (WR-02 residual, migration 0006): also rejects a token whose
    `expires_at` is not `NULL` and is in the past (reason `expired`) — a `NULL` `expires_at`
    (every pre-migration-0006 row, forever) still authenticates normally, no matter how old.

    Phase-6 remediation task-09 (WR-02 residual): also re-checks the resolved user's normalized
    email against the CURRENT `ADMIN_EMAILS` allowlist (reason `not-allowlisted`) — the SAME
    `settings.admin_email_set` property `app.routes.auth_routes.auth_callback` consults at login,
    recomputed from `settings.admin_emails` on every access rather than cached, so an operator who
    edits `ADMIN_EMAILS` and the running process picks it up kills a since-offboarded admin's
    outstanding bearer tokens on their very next call, not just at next login. The one real caller,
    `app.mcp.server._resolve_bearer_principal`, always passes `request.app.state.settings` — the
    LIVE instance, not one captured at process/request-factory-build time — so this check is
    accurate the instant `ADMIN_EMAILS` changes underneath a running process.

    P7 remediation (fresh-review M2): `settings` is now REQUIRED (no default) — it used to default
    to `None`, which SKIPPED the allowlist re-check entirely, a fail-OPEN default on the highest-
    value gate in this module (WR-02's actual revocation mechanism). Today's one production caller
    already always passed a live `Settings`, so this was latent, not live — but a fail-open default
    is a foot-gun for any FUTURE caller (a new script, a test copied as a template, a second MCP
    mount) that might call the 2-arg form and silently lose allowlist revocation while keeping full
    write access. Every caller must now supply the live `Settings` explicitly; there is no way to
    opt out of the allowlist re-check.

    Phase-6 remediation task-03/task-09 (WR-05, audit logging): logs exactly one line per call —
    INFO with the token row id ONLY on success, WARNING with a reason keyword (`unknown` /
    `revoked` / `inactive-user` / `expired` / `not-allowlisted`) on rejection. Never logs
    `raw_token`, `token_hash`, or the owner's email.

    Never raises on an unknown/garbage/malformed/revoked/expired/not-allowlisted token, and does
    the same amount of work (hash + one indexed lookup, short-circuiting only once a real row is
    or isn't found) whether `raw_token` matches a row or not — there is no separate "is this even
    shaped like a token" pre-check to skip.

    Args:
        session: an open `Session` the caller owns (opened/closed by the caller — this function
            never commits, rolls back, or closes it).
        raw_token: the bearer value as sent on the wire (no `"Bearer "` scheme prefix — the
            caller, `app.mcp.server`, strips that before calling this).
        settings: the live `Settings` instance to re-check the resolved user's email against
            (`settings.admin_email_set`) — required (P7 remediation M2); see the allowlist
            paragraph above.

    Returns:
        The owning user's `AdminPrincipal`, or `None` if `raw_token` doesn't match any
        `ApiToken.token_hash`, matches one whose owning `User` is missing or soft-deleted, matches
        one whose `session_epoch` is stale relative to the owner's current one, matches one whose
        `expires_at` has passed, or matches one whose owner's email is no longer in
        `settings.admin_email_set`.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token = session.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if token is None:
        logger.warning("Bearer token rejected: reason=unknown")
        return None

    user = get_active_user(session, token.user_id)
    if user is None:
        logger.warning("Bearer token rejected: token_id=%s reason=inactive-user", token.id)
        return None

    if token.session_epoch != user.session_epoch:
        logger.warning("Bearer token rejected: token_id=%s reason=revoked", token.id)
        return None

    if token.expires_at is not None and token.expires_at < datetime.now(UTC):
        logger.warning("Bearer token rejected: token_id=%s reason=expired", token.id)
        return None

    if user.email.strip().lower() not in settings.admin_email_set:
        logger.warning("Bearer token rejected: token_id=%s reason=not-allowlisted", token.id)
        return None

    logger.info("Bearer token resolved: token_id=%s", token.id)
    return AdminPrincipal(user_id=user.id, email=user.email, name=user.name)
