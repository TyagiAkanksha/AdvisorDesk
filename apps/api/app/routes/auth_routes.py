"""Auth routes (PRD §5.1): Google OAuth login/callback, logout, `/auth/me`.

CONVENTIONS.md §4: no `try/except` here — `AuthRequiredError` (raised by
`require_admin`) flows to `app.routes.errors::register_error_handlers`, which
builds the PRD §9 envelope; routes never construct error responses
themselves. `auth_callback`'s own failure branches are the exception (phase-8
C0): they `return` a `RedirectResponse` to the admin app's sign-in page
directly, rather than raising, so a failed login never dead-ends on a JSON
error page on the API origin.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import AdminPrincipal, require_admin
from app.auth.oauth import GoogleOAuthClient
from app.auth.oauth_request import AUTHORIZE_COOKIE_NAME
from app.auth.sessions import clear_cookie, issue_cookie, read_session
from app.auth.state import STATE_COOKIE_NAME, STATE_MAX_AGE_SECONDS, mint_state, verify_state
from app.config import Settings
from app.models.schemas.auth import GoogleIdentity, MeResponse
from app.models.schemas.common import ErrorEnvelope
from app.routes.deps import get_oauth_client, get_session, get_settings
from app.services.errors import AuthRequiredError
from app.services.users import bump_session_epoch, get_active_user, upsert_from_google

logger = logging.getLogger(__name__)

router = APIRouter()


def _sign_in_error_redirect(
    settings: Settings, reason: Literal["state", "forbidden"]
) -> RedirectResponse:
    """Phase-8 C0: land a failed callback on the admin sign-in page with a machine-readable
    reason (`state` | `forbidden`) instead of a JSON 403 on the API origin. Never carries the
    email or the state value. `admin_app_url` is rstripped of a trailing slash so a configured
    value with one doesn't produce a doubled slash in the redirect target."""
    admin_app_url = settings.admin_app_url.rstrip("/")
    return RedirectResponse(f"{admin_app_url}/signin?error={reason}", status_code=303)


@router.get("/auth/login", operation_id="auth_login")
def auth_login(
    oauth_client: GoogleOAuthClient = Depends(get_oauth_client),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """PRD §5.1: redirect (307) to Google's OAuth consent screen.

    Phase-6 task-05 (PRD §9 OAuth state CSRF, review finding t01-M7): `state` is now a signed,
    timestamped token (`app.auth.state.mint_state`) instead of an unsigned random string, AND is
    set as a double-submit cookie (`advisordesk_oauth_state`) on this SAME redirect response.
    The signature alone would not stop login-CSRF — an attacker can mint their own validly-signed
    state from their own `/auth/login` call — so `/auth/callback` requires BOTH the signature and
    an exact match against this cookie, which only THIS browser received.
    """
    state = mint_state(settings)
    response = RedirectResponse(oauth_client.authorization_url(state), status_code=307)
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        max_age=STATE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=not settings.is_dev,
    )
    return response


@router.get(
    "/auth/callback",
    operation_id="auth_callback",
    status_code=303,
    response_class=RedirectResponse,
    responses={
        303: {
            "description": (
                "Session cookie set and redirect to the admin app; or, on a state/allowlist "
                "failure, redirect to {admin_app_url}/signin?error=state|forbidden with no "
                "cookie."
            ),
        },
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
    },
)
def auth_callback(
    request: Request,
    code: str,
    state: str,
    oauth_client: GoogleOAuthClient = Depends(get_oauth_client),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """PRD §5.1: exchange `code`, reject non-allowlisted emails, upsert, set the session cookie.

    OAuth state CSRF (phase-6 task-05, PRD §9, review finding t01-M7): `state` is now
    cryptographically verified — BOTH a valid `app.auth.state.verify_state` signature/age AND an
    exact match against the `advisordesk_oauth_state` double-submit cookie `/auth/login` set —
    BEFORE `exchange_code` is ever called, so a forged or replayed-cross-browser callback never
    even reaches Google.

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

    Review round 1, finding F2: `responses=` declared a 403 for the allowlist/state failures
    below (superseded by phase-8 C0, which redirects instead of raising — see `Returns:` below)
    plus the 422 a missing/malformed `code`/`state` query param produces (rendered as
    `ErrorEnvelope` by `register_error_handlers`, never FastAPI's own default validation-error
    schema) — this route has no `require_admin` dependency, so, unlike the admin routes in
    `app.routes.content_routes`, no 401 applies here. Final review, finding
    C-3 / t01 M14: 502 added for `oauth_client.exchange_code`'s
    `OAuthExchangeError` (a reused/expired `code`, or a Google-side
    failure) — previously an unhandled 500 with a plain-text body.

    Callback landing (task-01 review M8 resolution, amended before task-04):
    success now 303-redirects to `settings.admin_app_url` with the session
    cookie set on that SAME `RedirectResponse` — a bodyless 200 dead-ended
    the browser on the API's own origin after Google sign-in, since nothing
    in the admin SPA runs there to pick the flow back up.
    `status_code=303`/`response_class=RedirectResponse` on the decorator
    (rather than leaving FastAPI's implicit 200 default) makes the OpenAPI
    baseline's success entry both the true status code and correctly
    body-less (`RedirectResponse.media_type` is `None`, unlike the default
    `JSONResponse`) — `responses=`'s `422` arm is untouched by this and still
    renders as `ErrorEnvelope` (the `403` arm no longer applies: phase-8 C0
    below redirects instead of raising on both former-403 branches).

    Returns:
        A `303` `RedirectResponse` in every case (phase-8 C0): on success, to
            `landing_url` with the session cookie set; if `state` fails
            `verify_state` (bad signature/expired) or does not match the
            `advisordesk_oauth_state` cookie (phase-6 task-05, PRD §9
            login-CSRF, checked first, before `exchange_code`), to
            `{admin_app_url}/signin?error=state`; if the normalized email is
            not in `ADMIN_EMAILS` (checked before any row write, PRD §5.1/§9),
            to `{admin_app_url}/signin?error=forbidden`. Neither failure
            redirect sets a cookie, and neither carries the email or the
            `state` value — only the machine-readable `reason`.
    """
    # Audit logging (phase-6 remediation task-03, WR-05, kept OUT of this docstring so
    # CONVENTIONS.md §8's openapi.json baseline — which embeds this docstring verbatim as the
    # operation's `description` — stays byte-stable): a successful login logs INFO with the
    # email; a state-verification failure and a non-allowlisted email each log WARNING (the
    # latter with reason `allowlist`) — never the `code`/`state` values themselves.
    state_cookie = request.cookies.get(STATE_COOKIE_NAME)
    if not verify_state(state, settings) or state != state_cookie:
        # Phase-6 remediation task-03 (WR-05): WARNING only — never `state`/`state_cookie`
        # themselves (a forged/replayed state value must never reach any log line).
        logger.warning("OAuth state verification failed")
        return _sign_in_error_redirect(settings, "state")

    identity = oauth_client.exchange_code(code)
    normalized_email = identity["email"].strip().lower()
    if normalized_email not in settings.admin_email_set:
        logger.warning("Login rejected: email=%s reason=allowlist", normalized_email)
        return _sign_in_error_redirect(settings, "forbidden")

    normalized_identity: GoogleIdentity = {
        "email": normalized_email,
        "name": identity["name"],
        "avatar_url": identity["avatar_url"],
    }
    user = upsert_from_google(session, normalized_identity)
    logger.info("Login succeeded: email=%s", user.email)

    # mcp-oauth plan, task 05: a pending `/oauth/authorize` request (the Google-bridge detour,
    # DESIGN.md §"Google bridge + consent") lands the login back at `/oauth/authorize/continue`
    # instead of the admin app, so the parked authorization request can resume; a plain login (no
    # pending cookie) is unaffected and still lands at `settings.admin_app_url`.
    landing_url = (
        "/api/v1/oauth/authorize/continue"
        if request.cookies.get(AUTHORIZE_COOKIE_NAME) is not None
        else settings.admin_app_url
    )
    response = RedirectResponse(landing_url, status_code=303)
    issue_cookie(response, user.id, user.session_epoch, settings)
    # The state cookie is single-use: delete it on the same response that lands the session
    # cookie (Interfaces §ii) so a captured/replayed callback URL can't be re-submitted with a
    # still-valid double-submit cookie sitting in the browser's jar.
    response.delete_cookie(STATE_COOKIE_NAME, httponly=True, samesite="lax")
    return response


@router.post(
    "/auth/logout",
    operation_id="auth_logout",
)
def auth_logout(
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> Response:
    """PRD §5.1: clear the session cookie; best-effort revoke it server-side too.

    No error responses are declared: this route has no `require_admin`
    dependency and no request fields — logout intentionally clears the
    cookie regardless of whether the caller has a valid session, returning
    200 idempotently (re-review ruling on the task-03 round-1 baseline).

    Phase-6 task-05 (PRD §9 logout revocation, review finding t01-M6): a bare cookie clear only
    ever protected the calling browser — a captured/stolen cookie kept working for the rest of
    its 30-day signed lifetime. `read_session` reads the (already shape-verified) cookie's owner
    and epoch; if present, `bump_session_epoch` revokes every outstanding cookie for that user (a
    no-op if the row no longer exists). A missing or malformed cookie is simply skipped —
    best-effort, never surfaced as an error — so the idempotent-200 contract holds unconditionally,
    same as before this task.

    Fix round 1 (review finding I-1) — WHY the epoch equality guard exists: `bump_session_epoch`
    only bumps when the cookie's `epoch` still equals the row's CURRENT `session_epoch`. Without
    that guard, an already-revoked cookie (one `require_admin` already rejects as a 401
    everywhere else) retained one privileged server-side effect: replaying it here would bump the
    epoch again, silently killing whatever session the admin logged back into since. A revoked
    cookie must not retain ANY server-side effect — it must be as inert here as it is everywhere
    else — so only a CURRENTLY-valid cookie is allowed to advance the counter. This route's own
    response is unaffected either way: 200 with the cookie cleared, unconditionally.
    """
    # Audit logging (phase-6 remediation task-03, WR-05, kept OUT of the docstring above so
    # CONVENTIONS.md §8's openapi.json baseline — which embeds that docstring verbatim as the
    # operation's `description` — stays byte-stable): when a session cookie was present, logs
    # INFO with the user id and whether the epoch was actually bumped (`bump_session_epoch`'s
    # own return value — `True` for a live cookie, `False` for a stale/already-revoked one). A
    # missing or malformed cookie logs nothing, same as it triggers no revocation.
    session_data = read_session(request, settings)
    if session_data is not None:
        user_id, cookie_epoch = session_data
        bumped = bump_session_epoch(session, user_id, cookie_epoch)
        logger.info("Logout: user_id=%s epoch_bumped=%s", user_id, bumped)

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
