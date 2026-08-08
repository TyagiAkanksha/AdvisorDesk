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
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import AdminPrincipal
from app.models.api_tokens import ApiToken
from app.services.users import get_active_user

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


def resolve_bearer_token(session: Session, raw_token: str) -> AdminPrincipal | None:
    """Resolve a raw bearer token to the `AdminPrincipal` of the `User` who owns it, or `None`.

    Hashes `raw_token` the same way `mint_token()` does, looks up the `ApiToken` row by
    `token_hash` (never by comparing raw values), then loads the owning `User` through
    `app.services.users.get_active_user` — the same active-row re-check `require_admin` performs
    on every request from a cookie, so a soft-deleted admin's tokens stop authenticating the
    instant the account is deactivated, not just at next login (PRD §9).

    Never raises on an unknown/garbage/malformed token, and does the same amount of work
    (hash + one indexed lookup, short-circuiting only once a real row is or isn't found) whether
    `raw_token` matches a row or not — there is no separate "is this even shaped like a token"
    pre-check to skip.

    Args:
        session: an open `Session` the caller owns (opened/closed by the caller — this function
            never commits, rolls back, or closes it).
        raw_token: the bearer value as sent on the wire (no `"Bearer "` scheme prefix — the
            caller, `app.mcp.server`, strips that before calling this).

    Returns:
        The owning user's `AdminPrincipal`, or `None` if `raw_token` doesn't match any
        `ApiToken.token_hash`, or matches one whose owning `User` is missing or soft-deleted.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token = session.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if token is None:
        return None

    user = get_active_user(session, token.user_id)
    if user is None:
        return None

    return AdminPrincipal(user_id=user.id, email=user.email, name=user.name)
