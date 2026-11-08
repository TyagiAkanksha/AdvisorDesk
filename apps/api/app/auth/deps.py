"""`require_admin` — the FastAPI dependency guarding every admin route (PRD §5.1, §9).

Deliberately reads `request.app.state` directly (settings + session
factory) rather than depending on `app.routes.deps.get_session`/
`get_settings`: CONVENTIONS.md §2 restricts `app.auth` to importing
`app.services`/`app.models`/`app.config`, not `app.routes` — this keeps
`app.auth` a sibling of `app.routes`/`app.mcp`/`app.agent` rather than a
dependent of `app.routes`. The small cost is a second, ad hoc, read-only
session per admin request (distinct from the route handler's own
`Depends(get_session)`), which is fine since this dependency never writes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.auth.sessions import read_session
from app.config import Settings
from app.services.errors import AuthRequiredError
from app.services.users import get_active_user, get_user_by_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdminPrincipal:
    """The authenticated admin identity `require_admin` attaches to a request (PRD §5.1).

    Consumed by every admin route, `/agent/chat` (phase-5 task-03), and MCP
    actor stamping (phase-5 task-01) to know which `User` is acting.
    """

    user_id: uuid.UUID
    email: str
    name: str | None


def resolve_admin(request: Request) -> AdminPrincipal | None:
    """Resolve the signed session cookie into an `AdminPrincipal`, or `None` if it doesn't.

    Everything `require_admin` does (PRD §9: 401s when there is no/invalid/expired session
    cookie, or when the session's `User` row is soft-deleted — re-checked on **every** request via
    `app.services.users.get_active_user`, never a row cached from login time, so a mid-session
    deactivation takes effect on the very next request; phase-6 task-05 logout revocation, review
    finding t01-M6: also rejects a cookie whose signed `epoch` no longer matches
    `User.session_epoch`), returning `None` instead of raising — same WARNING logs, same reasons
    (`reason=soft-deleted`, `reason=revoked-cookie`; phase-6 remediation task-03, WR-05 audit
    logging; P7 remediation fresh-review M1), unchanged.

    mcp-oauth plan, task 05: split out of `require_admin` so `GET /oauth/authorize/continue` can
    branch on "no admin session yet" (bridge to Google login) without treating that as an error
    the way `require_admin`'s raise would; `app.mcp.server._require_admin_with_challenge` also
    calls this directly, replacing its earlier `try/except AuthRequiredError` wrapper around
    `require_admin`.

    Args:
        request: the incoming request; reads
            `app.state.settings` and
            `app.state.session_factory` directly (see module docstring).

    Returns:
        The resolved `AdminPrincipal`, or `None` if there is no/invalid/expired cookie, the
        user id is unknown, the user row is soft-deleted, or the cookie's epoch is stale
        relative to `User.session_epoch`.

    Raises:
        RuntimeError: the app was built without a `session_factory` (a
            DB-less `create_app()`) — this dependency must fail loudly
            rather than silently skip the auth check.
    """
    settings = cast(Settings, request.app.state.settings)
    session_data = read_session(request, settings)
    if session_data is None:
        return None
    user_id, cookie_epoch = session_data

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "resolve_admin() requires app.state.session_factory, but none was "
            "configured — this app was built by create_app() without a "
            "session_factory (DB-less mode). Only app/main.py wires a real one."
        )

    session = session_factory()
    try:
        user = get_active_user(session, user_id)
        if user is None:
            # `get_active_user` excludes soft-deleted rows — recover the email straight from the
            # (still-open) session before it closes, so the audit line below can name who was
            # rejected. `stale_user is None` means the id never had a row at all (nothing to
            # attribute the rejection to); `stale_user` present means it exists but is
            # soft-deleted (the only way `get_active_user` could have excluded it).
            stale_user = get_user_by_id(session, user_id)
            if stale_user is not None:
                logger.warning("Login rejected: email=%s reason=soft-deleted", stale_user.email)
    finally:
        session.close()

    if user is None:
        return None

    if cookie_epoch != user.session_epoch:
        logger.warning("Login rejected: user_id=%s reason=revoked-cookie", user.id)
        return None

    return AdminPrincipal(user_id=user.id, email=user.email, name=user.name)


def resolve_allowlisted_admin(request: Request) -> AdminPrincipal | None:
    """`resolve_admin`, plus a re-check of the LIVE `ADMIN_EMAILS` allowlist on every request.

    A session cookie lives for days, so it can outlast its owner's removal from `ADMIN_EMAILS`.
    `resolve_admin` only proves the session is valid (signature, user row, epoch); this also
    proves the owner is STILL allowlisted, the same rule `resolve_bearer_token` applies to the MCP
    bearer path. Every cookie-gated surface that acts as an admin (`require_admin`, so every REST
    admin route and `/agent/chat`, plus the MCP endpoint's cookie path) goes through here, so
    removing an admin takes effect on their very next request.

    The OAuth authorize routes keep calling `resolve_admin` directly on purpose: they run their
    own allowlist check so a de-listed admin gets an OAuth `access_denied` redirect back to the
    connecting client rather than a bare 401.

    Args:
        request: the incoming request; forwarded to `resolve_admin` unchanged.

    Returns:
        The principal, or `None` when `resolve_admin` returns `None` or the principal's email is
        no longer in `settings.admin_email_set`.
    """
    principal = resolve_admin(request)
    if principal is None:
        return None
    settings = cast(Settings, request.app.state.settings)
    if principal.email.strip().lower() not in settings.admin_email_set:
        logger.warning("Login rejected: user_id=%s reason=not-allowlisted", principal.user_id)
        return None
    return principal


def require_admin(request: Request) -> AdminPrincipal:
    """Resolve the signed session cookie into an `AdminPrincipal`, or raise `AuthRequiredError`.

    mcp-oauth plan, task 05: now a thin wrapper over `resolve_admin` — every REST admin route
    depends on this exact raise-on-failure contract, so `resolve_admin`'s `None` is turned into
    the same `AuthRequiredError("Sign in required.")` this function has always raised. See
    `resolve_admin`'s own docstring for the full set of rejection reasons and their audit-log
    lines.

    Args:
        request: the incoming request; forwarded to `resolve_admin` unchanged.

    Raises:
        AuthRequiredError: no/invalid/expired cookie, unknown user id, a
            soft-deleted user row, or a cookie epoch stale relative to
            `User.session_epoch` (revoked by a since-run `/auth/logout`), or an
            owner who is no longer in `ADMIN_EMAILS` (`resolve_allowlisted_admin`).
        RuntimeError: the app was built without a `session_factory` (a
            DB-less `create_app()`) — this dependency must fail loudly
            rather than silently skip the auth check.
    """
    principal = resolve_allowlisted_admin(request)
    if principal is None:
        raise AuthRequiredError("Sign in required.")
    return principal
