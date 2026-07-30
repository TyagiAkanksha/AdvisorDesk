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
from app.models.schemas.auth import GoogleIdentity, MeResponse
from app.models.schemas.common import ErrorEnvelope
from app.routes.deps import get_oauth_client, get_session, get_settings
from app.services.errors import AuthRequiredError, ForbiddenError
from app.services.users import get_active_user, upsert_from_google

router = APIRouter()


@router.get("/auth/login", operation_id="auth_login")
def auth_login(
    oauth_client: GoogleOAuthClient = Depends(get_oauth_client),
) -> RedirectResponse:
    """PRD §5.1: redirect (307) to Google's OAuth consent screen."""
    state = secrets.token_urlsafe(16)
    return RedirectResponse(oauth_client.authorization_url(state), status_code=307)


@router.get(
    "/auth/callback",
    operation_id="auth_callback",
    status_code=303,
    response_class=RedirectResponse,
    responses={
        303: {
            "description": (
                "Session cookie set; redirects to the admin app (settings.admin_app_url)."
            ),
        },
        403: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
def auth_callback(
    code: str,
    state: str,
    oauth_client: GoogleOAuthClient = Depends(get_oauth_client),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """PRD §5.1: exchange `code`, reject non-allowlisted emails, upsert, set the session cookie.

    `state` is accepted (Google always sends back what `/auth/login`
    generated) but not cryptographically verified against a stored value —
    PRD §9 pins the allowlist/session-cookie/soft-delete behaviors, not a
    CSRF `state` round-trip, so this stays minimal.

    Email normalization (phase-2 task-01 review round 1, finding I3):
    `identity["email"]` is normalized (`strip().lower()`) exactly once, here,
    and the SAME normalized value is used both for the allowlist check and
    for persistence — passing a raw, differently-cased email through to
    `upsert_from_google` would let e.g. `'Admin@Example.com'` and
    `'admin@example.com'` create two distinct `User` rows, splitting the
    admin's identity and breaking the PRD §4.1 same-row reactivation
    guarantee. `upsert_from_google` also normalizes defensively (belt and
    suspenders for any future caller), but this route is the canonical place
    the normalization is decided, since it is also what the allowlist check
    must agree with. `name`/`avatar_url` are passed through unchanged.

    Review round 1, finding F2: `responses=` declares the 403 `ForbiddenError`
    raises below plus the 422 a missing/malformed `code`/`state` query param
    produces (both rendered as `ErrorEnvelope` by `register_error_handlers`,
    never FastAPI's own default validation-error schema) — this route has
    no `require_admin` dependency, so, unlike the admin routes in
    `app.routes.content_routes`, no 401 applies here.

    Callback landing (task-01 review M8 resolution, amended before task-04):
    success now 303-redirects to `settings.admin_app_url` with the session
    cookie set on that SAME `RedirectResponse` — a bodyless 200 dead-ended
    the browser on the API's own origin after Google sign-in, since nothing
    in the admin SPA runs there to pick the flow back up.
    `status_code=303`/`response_class=RedirectResponse` on the decorator
    (rather than leaving FastAPI's implicit 200 default) makes the OpenAPI
    baseline's success entry both the true status code and correctly
    body-less (`RedirectResponse.media_type` is `None`, unlike the default
    `JSONResponse`) — `responses=`'s `403`/`422` arms are untouched by this
    and still render as `ErrorEnvelope`. Error paths never construct a
    response at all (they raise), so they are unaffected by this route
    always building a `RedirectResponse` on the success path.

    Raises:
        ForbiddenError: the normalized email is not in `ADMIN_EMAILS` — the
            check runs before any row write (PRD §5.1/§9).
    """
    identity = oauth_client.exchange_code(code)
    normalized_email = identity["email"].strip().lower()
    if normalized_email not in settings.admin_email_set:
        raise ForbiddenError(f"{identity['email']} is not an allowlisted admin.")

    normalized_identity: GoogleIdentity = {
        "email": normalized_email,
        "name": identity["name"],
        "avatar_url": identity["avatar_url"],
    }
    user = upsert_from_google(session, normalized_identity)

    response = RedirectResponse(settings.admin_app_url, status_code=303)
    issue_cookie(response, user.id, settings)
    return response


@router.post(
    "/auth/logout",
    operation_id="auth_logout",
)
def auth_logout() -> Response:
    """PRD §5.1: clear the session cookie.

    No error responses are declared: this route has no `require_admin`
    dependency and no request fields — logout intentionally clears the
    cookie regardless of whether the caller has a valid session, returning
    200 idempotently (re-review ruling on the task-03 round-1 baseline).
    """
    response = Response(status_code=200)
    clear_cookie(response)
    return response


@router.get(
    "/auth/me",
    operation_id="auth_me",
    response_model=MeResponse,
    responses={401: {"model": ErrorEnvelope}},
)
def auth_me(
    principal: AdminPrincipal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MeResponse:
    """PRD §5.1: the current admin's identity (`require_admin` raises 401 otherwise).

    Looks up `avatar_url` via a fresh `get_active_user` read (phase-2
    task-01 review round 1, finding I4: routes never touch the ORM
    directly) rather than carrying it on `AdminPrincipal` — the task-01
    brief pins `AdminPrincipal` to exactly `user_id, email, name` (later
    tasks match that shape), so the one field `/auth/me` alone needs is
    fetched here.

    This is a second point read of the same row `require_admin` just
    validated moments ago, on a second, independent `Session`
    (`require_admin` cannot share `app.routes.deps.get_session`'s per the
    layering rule in its own module docstring). Avoiding it cheaply would
    mean growing `AdminPrincipal`'s pinned shape or smuggling the row
    through `Request.state` behind an undocumented, untyped side channel —
    both worse than one extra indexed point lookup, so it is left as is.

    Raises:
        AuthRequiredError: the row `require_admin` just validated is gone
            or was soft-deleted in the (vanishingly small) window between
            that check and this one — treated identically to "no session"
            rather than surfacing as an unhandled 500.
    """
    user = get_active_user(session, principal.user_id)
    if user is None:
        raise AuthRequiredError("Sign in required.")
    return MeResponse(id=user.id, email=user.email, name=user.name, avatar_url=user.avatar_url)
