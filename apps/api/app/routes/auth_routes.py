"""Auth routes (PRD §5.1): Google OAuth login/callback, logout, `/auth/me`.

CONVENTIONS.md §4: no `try/except` here — `ForbiddenError`/`AuthRequiredError`
(raised below and by `require_admin`) flow to
`app.routes.errors::register_error_handlers`, which builds the PRD §9
envelope; routes never construct error responses themselves.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import AdminPrincipal, require_admin
from app.auth.oauth import GoogleOAuthClient
from app.auth.sessions import clear_cookie, issue_cookie
from app.config import Settings
from app.models import User
from app.models.schemas.auth import MeResponse
from app.routes.deps import get_oauth_client, get_session, get_settings
from app.services.errors import ForbiddenError
from app.services.queries import active_select
from app.services.users import upsert_from_google

router = APIRouter()


@router.get("/auth/login", operation_id="auth_login")
def auth_login(
    oauth_client: GoogleOAuthClient = Depends(get_oauth_client),
) -> RedirectResponse:
    """PRD §5.1: redirect (307) to Google's OAuth consent screen."""
    state = secrets.token_urlsafe(16)
    return RedirectResponse(oauth_client.authorization_url(state), status_code=307)


@router.get("/auth/callback", operation_id="auth_callback")
def auth_callback(
    code: str,
    state: str,
    oauth_client: GoogleOAuthClient = Depends(get_oauth_client),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> Response:
    """PRD §5.1: exchange `code`, reject non-allowlisted emails, upsert, set the session cookie.

    `state` is accepted (Google always sends back what `/auth/login`
    generated) but not cryptographically verified against a stored value —
    PRD §9 pins the allowlist/session-cookie/soft-delete behaviors, not a
    CSRF `state` round-trip, so this stays minimal.

    Raises:
        ForbiddenError: `identity["email"]` is not in `ADMIN_EMAILS` — the
            check runs before any row write (PRD §5.1/§9).
    """
    identity = oauth_client.exchange_code(code)
    if identity["email"].strip().lower() not in settings.admin_email_set:
        raise ForbiddenError(f"{identity['email']} is not an allowlisted admin.")

    user = upsert_from_google(session, identity)

    response = Response(status_code=200)
    issue_cookie(response, user.id, settings)
    return response


@router.post("/auth/logout", operation_id="auth_logout")
def auth_logout() -> Response:
    """PRD §5.1: clear the session cookie."""
    response = Response(status_code=200)
    clear_cookie(response)
    return response


@router.get("/auth/me", operation_id="auth_me", response_model=MeResponse)
def auth_me(
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MeResponse:
    """PRD §5.1: the current admin's identity (`require_admin` raises 401 otherwise).

    Looks up `avatar_url` via a fresh `active_select` read rather than
    carrying it on `AdminPrincipal` — the task-01 brief pins
    `AdminPrincipal` to exactly `user_id, email, name` (later tasks match
    that shape), so the one field `/auth/me` alone needs is fetched here.
    """
    user = session.execute(active_select(User).where(User.id == principal.user_id)).scalar_one()
    return MeResponse(id=user.id, email=user.email, name=user.name, avatar_url=user.avatar_url)
