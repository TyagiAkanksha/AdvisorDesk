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


def require_admin(request: Request) -> AdminPrincipal:
    """Resolve the signed session cookie into an `AdminPrincipal`, or raise `AuthRequiredError`.

    PRD §9: 401s when there is no/invalid/expired session cookie, or when
    the session's `User` row is soft-deleted — re-checked on **every**
    request via `app.services.users.get_active_user` (never a row cached
    from login time), so a mid-session deactivation takes effect on the
    very next request.

    Phase-6 task-05 (logout revocation, review finding t01-M6): also 401s when the cookie's
    signed `epoch` no longer matches `User.session_epoch` — `/auth/logout` bumps that counter
    (`app.services.users.bump_session_epoch`), so every cookie signed before the bump is dead
    on its very next use, not just cleared from the browser that logged out.

    Phase-6 remediation task-03 (WR-05, audit logging): when `get_active_user` excludes a row
    (the "soft-deleted" branch below — an UNKNOWN user id has no row to look up at all, so it
    logs nothing), a second, non-`active_select` lookup (`app.services.users.get_user_by_id`)
    recovers that row's email so the WARNING can name who was rejected — `get_active_user` alone
    cannot, since it excludes the very row this needs.

    P7 remediation (fresh-review M1): the cookie-epoch-stale branch below now ALSO logs a WARNING
    (`reason=revoked-cookie`) — this task's own six pinned audit events predate WR-02's bearer-side
    epoch revocation (`app.auth.tokens.resolve_bearer_token`'s `reason=revoked` line), which left
    the cookie path as the one authentication-failure branch with no audit trail at all: a
    captured/stolen admin cookie replayed after `/auth/logout` correctly 401s but previously left
    zero trace in `docker logs`. The WARNING carries `user.id` only — never the raw cookie value or
    its signature — mirroring the bearer path's log hygiene (`resolve_bearer_token` never logs
    `raw_token`/`token_hash`).

    Args:
        request: the incoming request; reads `app.state.settings` and
            `app.state.session_factory` directly (see module docstring).

    Raises:
        AuthRequiredError: no/invalid/expired cookie, unknown user id, a
            soft-deleted user row, or a cookie epoch stale relative to
            `User.session_epoch` (revoked by a since-run `/auth/logout`).
        RuntimeError: the app was built without a `session_factory` (a
            DB-less `create_app()`) — this dependency must fail loudly
            rather than silently skip the auth check.
    """
    settings = cast(Settings, request.app.state.settings)
    session_data = read_session(request, settings)
    if session_data is None:
        raise AuthRequiredError("Sign in required.")
    user_id, cookie_epoch = session_data

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "require_admin() requires app.state.session_factory, but none was "
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
        raise AuthRequiredError("Sign in required.")

    if cookie_epoch != user.session_epoch:
        logger.warning("Login rejected: user_id=%s reason=revoked-cookie", user.id)
        raise AuthRequiredError("Sign in required.")

    return AdminPrincipal(user_id=user.id, email=user.email, name=user.name)
