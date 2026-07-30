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

import uuid
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.auth.sessions import read_user_id
from app.config import Settings
from app.models import User
from app.services.errors import AuthRequiredError
from app.services.queries import active_select


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
    request via `active_select` (never a row cached from login time), so a
    mid-session deactivation takes effect on the very next request.

    Args:
        request: the incoming request; reads `app.state.settings` and
            `app.state.session_factory` directly (see module docstring).

    Raises:
        AuthRequiredError: no/invalid/expired cookie, unknown user id, or a
            soft-deleted user row.
        RuntimeError: the app was built without a `session_factory` (a
            DB-less `create_app()`) — this dependency must fail loudly
            rather than silently skip the auth check.
    """
    settings = cast(Settings, request.app.state.settings)
    user_id = read_user_id(request, settings)
    if user_id is None:
        raise AuthRequiredError("Sign in required.")

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "require_admin() requires app.state.session_factory, but none was "
            "configured — this app was built by create_app() without a "
            "session_factory (DB-less mode). Only app/main.py wires a real one."
        )

    session = session_factory()
    try:
        user = session.execute(active_select(User).where(User.id == user_id)).scalar_one_or_none()
    finally:
        session.close()

    if user is None:
        raise AuthRequiredError("Sign in required.")

    return AdminPrincipal(user_id=user.id, email=user.email, name=user.name)
