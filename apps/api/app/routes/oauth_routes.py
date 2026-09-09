"""RFC 7591 dynamic client registration route — `POST /oauth/register` (mcp-oauth plan, task 04);
`GET /oauth/authorize` + `GET /oauth/authorize/continue` (mcp-oauth plan, task 05; RFC 6749 §4.1,
RFC 7636 PKCE); `POST /oauth/token` (mcp-oauth plan, task 07; RFC 6749 §4.1.3/§4.1.4 code grant,
§6 refresh grant); the consent screen + `POST /oauth/authorize/decision` (mcp-oauth plan, task 06;
docs/plans/mcp-oauth/task-06-consent-screen.md); `POST /oauth/revoke` (mcp-oauth plan, task 08;
RFC 7009 token revocation; docs/plans/mcp-oauth/task-08-revoke-admin-api.md). The sibling admin
"Connected apps" router (`GET`/`DELETE /oauth/clients...`) lives in `app.routes.oauth_admin_routes`
instead — those two are cookie-gated (`require_admin`), not `/oauth/*`'s own bare-OAuth-error/
rate-limited shape, so they get their own router rather than living here.

docs/plans/mcp-oauth/DESIGN.md §"End-to-end flow" step 4: "Claude -> POST /register (DCR) with
its redirect_uris + name -> { client_id, ... } (public client, no secret)". CONVENTIONS.md §4:
this route contains no `try/except` — every `OAuthError`/`RateLimitedError` raised below flows to
its registered handler (`app.routes.errors`), which builds the response.

Validation order (task brief Interfaces block, pinned exactly — DESIGN.md §"Security / threat
model": "DCR is open per MCP, so cap client creation + prune stale/unused clients"):
`limiter.check_oauth_request` -> `prune_stale_clients` -> metadata validation -> the
`oauth_max_clients` cap check -> `register_client`. Rate-limiting first means a flood of bad
requests never even reaches the DB; pruning before validation means a legitimate registration
that would otherwise trip the cap gets the benefit of space just freed by stale clients.

`responses={..., 422: {"model": ErrorEnvelope}, ...}` on the route decorator below is additive to
the task brief's own `responses=` block (which named only 400/429): `client_name`'s
`Field(max_length=200)` (`app.models.schemas.oauth.ClientRegistrationRequest`) can fail FastAPI's
body validation before this function ever runs, rendering the generic PRD §9 `ErrorEnvelope`
shape via `app.routes.errors._validation_error_handler` — NOT the bare `OAuthError` shape. Every
other body-taking route in this codebase (`app.routes.content_routes`, `app.routes.auth_routes`)
overrides FastAPI's default 422 `HTTPValidationError` schema the exact same way, and
`tests/test_routes_errors.py::
test_openapi_baseline_declares_error_envelope_not_the_fastapi_default` pins that
`HTTPValidationError` never appears anywhere in the committed OpenAPI baseline — leaving 422
undeclared here would reintroduce it just for this one route.
"""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import AdminPrincipal, require_admin, resolve_admin
from app.auth.oauth_authorize import validate_authorize_request
from app.auth.oauth_request import (
    AUTHORIZE_COOKIE_NAME,
    PendingAuthorization,
    clear_pending_cookie,
    mint_pending_authorization,
    read_pending_authorization,
    set_pending_cookie,
)
from app.config import Settings
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.oauth import (
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    TokenResponse,
)
from app.routes.deps import get_oauth_token_session, get_rate_limiter, get_session, get_settings
from app.routes.oauth_consent_html import consent_csp, render_consent_page
from app.routes.ratelimit import RateLimiter
from app.services.errors import OAuthError, OAuthRedirectError
from app.services.oauth_clients import (
    count_clients,
    get_client,
    prune_stale_clients,
    register_client,
    validate_redirect_uri,
)
from app.services.oauth_codes import issue_authorization_code
from app.services.oauth_consents import find_active_consent, record_consent
from app.services.oauth_tokens import redeem_authorization_code, revoke_token, rotate_refresh_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

_UNNAMED_CLIENT = "Unnamed client"
_ALLOWED_GRANT_TYPES = {"authorization_code", "refresh_token"}
_ALLOWED_RESPONSE_TYPES = {"code"}
_DEFAULT_GRANT_TYPES = ["authorization_code", "refresh_token"]
_DEFAULT_RESPONSE_TYPES = ["code"]


@router.post(
    "/register",
    operation_id="oauth_register",
    status_code=201,
    response_model=ClientRegistrationResponse,
    responses={
        400: {
            "description": "OAuth error",
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_client_metadata",
                        "error_description": "…",
                    }
                }
            },
        },
        422: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
    },
)
def oauth_register(
    body: ClientRegistrationRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ClientRegistrationResponse:
    """Register a new OAuth client (RFC 7591 §3.1 request / §3.2.1 response).

    After this call, `claude.ai` (or any other MCP client) holds a `client_id` it can use to
    start the authorization-code flow a later mcp-oauth task implements; nothing here can
    authorize a user or mint a token.
    """
    client_ip = request.client.host if request.client is not None else "unknown"
    limiter.check_oauth_request(client_ip)

    prune_stale_clients(session, now=datetime.now(UTC))

    redirect_uris = body.redirect_uris
    if not redirect_uris:
        raise OAuthError(
            "invalid_client_metadata", "redirect_uris is required and must not be empty."
        )
    for uri in redirect_uris:
        validate_redirect_uri(uri)

    if body.token_endpoint_auth_method not in (None, "none"):
        raise OAuthError(
            "invalid_client_metadata",
            'token_endpoint_auth_method must be "none" — this server issues public clients only.',
        )

    if body.grant_types is not None and not set(body.grant_types) <= _ALLOWED_GRANT_TYPES:
        raise OAuthError(
            "invalid_client_metadata",
            f"grant_types must be a subset of {sorted(_ALLOWED_GRANT_TYPES)}.",
        )

    if body.response_types is not None and not set(body.response_types) <= _ALLOWED_RESPONSE_TYPES:
        raise OAuthError(
            "invalid_client_metadata",
            f"response_types must be a subset of {sorted(_ALLOWED_RESPONSE_TYPES)}.",
        )

    if body.scope is not None and body.scope != "mcp":
        raise OAuthError("invalid_scope", 'scope must be "mcp".')

    if count_clients(session) >= settings.oauth_max_clients:
        raise OAuthError("invalid_client_metadata", "Too many registered clients; try again later.")

    client_name = (body.client_name or "").strip() or _UNNAMED_CLIENT
    client = register_client(session, redirect_uris=redirect_uris, client_name=client_name)

    return ClientRegistrationResponse(
        client_id=client.client_id,
        client_id_issued_at=int(client.created_at.timestamp()),
        client_name=client.client_name,
        redirect_uris=client.redirect_uris,
        grant_types=_DEFAULT_GRANT_TYPES,
        response_types=_DEFAULT_RESPONSE_TYPES,
    )


@router.get(
    "/authorize",
    operation_id="oauth_authorize",
    status_code=303,
    response_class=RedirectResponse,
    responses={
        302: {
            "description": (
                "Request validation failed (past the client_id/redirect_uri check): redirects "
                "to the client's own redirect_uri with error/error_description/state (RFC 6749 "
                "§4.1.2.1)."
            ),
        },
        400: {
            "description": (
                "OAuth error — unknown client_id or unregistered redirect_uri. Never redirected "
                "(RFC 6749 §4.1.2.1: neither is safe to redirect to)."
            ),
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_client",
                        "error_description": "…",
                    }
                }
            },
        },
        422: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
    },
)
def oauth_authorize(
    request: Request,
    response_type: str | None = None,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    scope: str | None = None,
    resource: str | None = None,
    state: str | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> RedirectResponse:
    """Validate an OAuth 2.1 authorization request, then park it pending the Google-login bridge
    (RFC 6749 §4.1.1; DESIGN.md §"End-to-end flow" step 5).

    `validate_authorize_request` (`app.auth.oauth_authorize`) does the actual validation, in its
    own pinned order — an unknown client or unregistered redirect_uri answers 400 JSON and never
    redirects (RFC 6749 §4.1.2.1); every later failure (unsupported response_type, missing/invalid
    PKCE challenge, unsupported scope/resource) redirects to the now-verified redirect_uri with
    `error`/`error_description`/`state`. A fully valid request 303s to `/authorize/continue` with
    the validated request signed into an `HttpOnly` pending-authorization cookie — no admin
    identity is resolved or consulted here; that happens on `continue`, after (if needed) the
    Google-login detour.

    No consent screen yet (mcp-oauth task 06 inserts it into `/authorize/continue`).
    """
    client_ip = request.client.host if request.client is not None else "unknown"
    limiter.check_oauth_request(client_ip)

    pending = validate_authorize_request(
        session,
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_type=response_type,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
        resource=resource,
        state=state,
        settings=settings,
    )

    response = RedirectResponse("/api/v1/oauth/authorize/continue", status_code=303)
    set_pending_cookie(response, mint_pending_authorization(pending, settings), settings)
    return response


def _redirect_with_params(redirect_uri: str, params: dict[str, str]) -> str:
    """Append `params` to `redirect_uri` as a query string, `&`-joining onto an existing one.

    mcp-oauth task 06 (t05 review finding M-4): a registered `redirect_uri` may already carry its
    own query string (e.g. a multi-tenant client's `?tenant=x`) — appending with a bare `?` in
    that case would produce a second, malformed `?` rather than joining onto the first. Shared by
    `_issue_code_and_redirect`'s success redirect and `oauth_authorize_decision`'s deny redirect
    below, so both success and error paths use the identical separator logic (duplication is the
    thing t05's review flagged, not the existence of two call sites).
    """
    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{urlencode(params)}"


def _issue_code_and_redirect(
    session: Session,
    pending: PendingAuthorization,
    principal: AdminPrincipal,
    settings: Settings,
) -> RedirectResponse:
    """Mint a single-use authorization code for `pending`/`principal` and 302-redirect with it.

    Module-level (not a route) so mcp-oauth task 06's consent-approval endpoint can reuse this
    exact issuance-and-redirect step once a consent decision has been recorded, without
    duplicating it. Task 06 controller carry-over (t05 review I-1): for a client WITHOUT an active
    consent, this function is now reachable ONLY from `oauth_authorize_decision`'s approve branch —
    `oauth_authorize_continue` calls it directly ONLY when `find_active_consent` already found one.

    Clears the pending-authorization cookie on the SAME response (single-use — the parked request
    this helper just consumed can never be replayed to mint a second code).
    """
    now = datetime.now(UTC)
    code = issue_authorization_code(
        session,
        client_id=pending.client_id,
        user_id=principal.user_id,
        redirect_uri=pending.redirect_uri,
        code_challenge=pending.code_challenge,
        resource=pending.resource,
        scope=pending.scope,
        now=now,
        ttl_seconds=settings.oauth_auth_code_ttl_seconds,
    )
    params: dict[str, str] = {"code": code}
    if pending.state is not None:
        params["state"] = pending.state
    response = RedirectResponse(
        _redirect_with_params(pending.redirect_uri, params),
        status_code=302,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    clear_pending_cookie(response)
    return response


@router.get(
    "/authorize/continue",
    operation_id="oauth_authorize_continue",
    responses={
        200: {
            "description": (
                "The consent page: the FIRST authorization for this (user, client) pair "
                "(mcp-oauth task 06) — the admin must Approve or Deny via "
                "POST /api/v1/oauth/authorize/decision before a code is issued."
            ),
            "content": {"text/html": {}},
        },
        307: {
            "description": (
                "No admin session yet — redirects to /api/v1/auth/login (the Google-login "
                "bridge); the pending-authorization cookie is left in place."
            ),
        },
        302: {
            "description": (
                "Either a single-use authorization code was issued (redirects to the client's "
                "own redirect_uri with code/state, when consent is already on file), or the "
                "resolved admin is not allowlisted (redirects with error=access_denied/state)."
            ),
        },
        400: {
            "description": (
                "OAuth error — no (or an invalid/expired/tampered) pending-authorization cookie, "
                "or the pending request's own client was deleted mid-flow."
            ),
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_request",
                        "error_description": "…",
                    }
                }
            },
        },
        429: {"model": ErrorEnvelope},
    },
)
def oauth_authorize_continue(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> Response:
    """Resume a parked `/authorize` request: bridge to Google login, then gate on consent.

    DESIGN.md §"End-to-end flow" steps 5-6, §"Google bridge + consent": reads the signed
    pending-authorization cookie `/authorize` set. No cookie (missing, tampered, or expired) is a
    400 `invalid_request` — never a 500. With a valid pending request but no admin session yet,
    307-redirects to `/api/v1/auth/login` (`app.routes.auth_routes.auth_login`) — the SAME cookie
    survives that detour (`Path=/api/v1`, and `/auth/callback`'s own success redirect lands back
    here, per that route's own amendment) so a second visit to this route, post-login, resumes
    exactly where it left off. Once an admin session resolves, re-checks the allowlist (`resolve_
    admin` itself does not — only `/auth/callback` and this route's own check do) before issuing
    the code, since a session minted while still allowlisted can outlive a later allowlist edit.

    mcp-oauth task 06 (docs/plans/mcp-oauth/task-06-consent-screen.md): if an ACTIVE consent
    already exists for this `(user, client)` pair (`find_active_consent`), issues the code
    immediately, exactly as before this task. Otherwise renders the server-rendered Approve/Deny
    consent page (`app.routes.oauth_consent_html.render_consent_page`) instead — task-06 controller
    carry-over (t05 review I-1): a code is NEVER issued from this GET for a client lacking an
    active consent; only `POST /authorize/decision`'s approve branch can do that.

    Raises:
        OAuthError: no valid pending-authorization cookie (`"invalid_request"`, 400), or the
            pending request's own `client_id` no longer names a registered client (`"invalid_
            client"`, 400 — the client was deleted mid-flow, between `/authorize` and this call).
        OAuthRedirectError: the resolved admin's email is not in `settings.admin_email_set`
            (`"access_denied"`) — redirects to the pending request's own `redirect_uri`.
    """
    client_ip = request.client.host if request.client is not None else "unknown"
    limiter.check_oauth_request(client_ip)

    pending = read_pending_authorization(request.cookies.get(AUTHORIZE_COOKIE_NAME), settings)
    if pending is None:
        raise OAuthError("invalid_request", "No pending authorization request.")

    principal = resolve_admin(request)
    if principal is None:
        return RedirectResponse("/api/v1/auth/login", status_code=307)

    if principal.email.lower() not in settings.admin_email_set:
        raise OAuthRedirectError(
            "access_denied",
            "This account is not permitted to authorize MCP access.",
            pending.redirect_uri,
            pending.state,
        )

    active_consent = find_active_consent(
        session, user_id=principal.user_id, client_id=pending.client_id
    )
    if active_consent is not None:
        return _issue_code_and_redirect(session, pending, principal, settings)

    client = get_client(session, pending.client_id)
    if client is None:
        raise OAuthError("invalid_client", "Unknown client.")

    consent_page = render_consent_page(
        client_name=client.client_name,
        user_email=principal.email,
        action_path="/api/v1/oauth/authorize/decision",
        nonce=pending.nonce,
    )
    return HTMLResponse(
        consent_page,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Content-Security-Policy": consent_csp(pending.redirect_uri),
        },
    )


@router.post(
    "/authorize/decision",
    operation_id="oauth_authorize_decision",
    responses={
        302: {
            "description": (
                "Approve: a single-use authorization code was issued (redirects to the client's "
                "own redirect_uri with code/state). Deny: redirects with "
                "error=access_denied/error_description/state, and no code is issued."
            ),
        },
        400: {
            "description": (
                "OAuth error — no pending-authorization cookie, a missing/mismatched consent "
                "form nonce, a decision value other than approve/deny, or (approve only) the "
                "pending authorization's client was deleted before the decision was submitted."
            ),
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_request",
                        "error_description": "…",
                    }
                }
            },
        },
        422: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
    },
)
def oauth_authorize_decision(
    request: Request,
    decision: Annotated[str | None, Form()] = None,
    nonce: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> Response:
    """Handle the consent page's Approve/Deny submission (mcp-oauth plan, task 06).

    docs/plans/mcp-oauth/task-06-consent-screen.md: guarded by `require_admin` (raise-on-failure),
    NOT `resolve_admin` (which `oauth_authorize_continue` uses to bridge to a 307 login redirect) —
    a session that vanished between rendering the consent page and submitting the form must answer
    401, never loop back through Google login (task-06 controller carry-over, t05 review context).
    The submitted `nonce` is compared against the pending request's own `PendingAuthorization.
    nonce` with `hmac.compare_digest` — an absent `nonce` is rejected up front (never passed to
    `compare_digest` as `None`), and a non-ASCII `nonce` is rejected the same way before reaching
    `compare_digest` (fix round 1, review finding I-1: `hmac.compare_digest` raises `TypeError` on
    a non-ASCII `str` operand, which would otherwise escape as an unhandled 500 instead of this
    route's documented 400) — binding this POST to the exact pending request the consent page was
    rendered for, the CSRF-style guard `nonce` exists for (`app.auth.oauth_request`'s own module
    docstring).

    Approve records an `OAuthConsent` row (`app.services.oauth_consents.record_consent`) and then
    issues the code via `_issue_code_and_redirect`, identically to `oauth_authorize_continue`'s own
    already-consented path. Deny redirects to the pending request's own `redirect_uri` with
    `error=access_denied` and clears the pending cookie — records no consent, issues no code — so a
    second `GET /authorize/continue` right after is NOT resumable (400 `invalid_request`, since the
    cookie is already gone).

    Raises:
        OAuthError: no valid pending-authorization cookie (`"invalid_request"`, 400); the
            submitted `nonce` is missing or does not match the pending request's own
            (`"invalid_request"`, "Consent form token mismatch.", 400); `decision` is neither
            `"approve"` nor `"deny"` (`"invalid_request"`, 400); on approve, the pending
            authorization's `client_id` no longer names a registered client — deleted between
            rendering the consent page and this POST (`"invalid_client"`, "Unknown client.", 400;
            final fix round 1, finding F-12 — mirrors `oauth_authorize_continue`'s own check).
        OAuthRedirectError: the resolved admin's email is not in `settings.admin_email_set`
            (`"access_denied"`) — redirects to the pending request's own `redirect_uri`.
        AuthRequiredError: no valid admin session (`require_admin`) — 401 §9 `auth_required`
            envelope.
    """
    client_ip = request.client.host if request.client is not None else "unknown"
    limiter.check_oauth_request(client_ip)

    pending = read_pending_authorization(request.cookies.get(AUTHORIZE_COOKIE_NAME), settings)
    if pending is None:
        raise OAuthError("invalid_request", "No pending authorization request.")

    principal = require_admin(request)

    if principal.email.lower() not in settings.admin_email_set:
        raise OAuthRedirectError(
            "access_denied",
            "This account is not permitted to authorize MCP access.",
            pending.redirect_uri,
            pending.state,
        )

    if nonce is None or not nonce.isascii() or not hmac.compare_digest(nonce, pending.nonce):
        raise OAuthError("invalid_request", "Consent form token mismatch.")

    if decision == "deny":
        params: dict[str, str] = {
            "error": "access_denied",
            "error_description": "The user denied the request.",
        }
        if pending.state is not None:
            params["state"] = pending.state
        response = RedirectResponse(
            _redirect_with_params(pending.redirect_uri, params),
            status_code=302,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
        clear_pending_cookie(response)
        return response

    if decision == "approve":
        # Final fix round 1, F-12: mirrors the sibling check at `oauth_authorize_continue` above
        # (`client = get_client(...); if client is None: raise OAuthError(...)`) — the client can
        # be deleted between rendering this consent page and the browser POSTing the decision
        # back; without this re-check, `record_consent`'s `oauth_consents.client_id` FK insert
        # would raise an uncaught `IntegrityError` (a 500), not this route's documented 400.
        if get_client(session, pending.client_id) is None:
            raise OAuthError("invalid_client", "Unknown client.")
        record_consent(
            session,
            user_id=principal.user_id,
            client_id=pending.client_id,
            scope=pending.scope,
            now=datetime.now(UTC),
        )
        return _issue_code_and_redirect(session, pending, principal, settings)

    raise OAuthError("invalid_request", "decision must be approve or deny.")


@router.post(
    "/token",
    operation_id="oauth_token",
    response_model=TokenResponse,
    responses={
        400: {
            "description": "OAuth error — invalid_request/invalid_grant/invalid_target/"
            "invalid_scope/unsupported_grant_type.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_grant",
                        "error_description": "…",
                    }
                }
            },
        },
        401: {
            "description": "Unknown client_id.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_client",
                        "error_description": "Unknown client.",
                    }
                }
            },
        },
        422: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
    },
)
def oauth_token(
    request: Request,
    grant_type: Annotated[str | None, Form()] = None,
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    resource: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    scope: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_oauth_token_session),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> Response:
    """Exchange an authorization code, or an existing refresh token, for a fresh token pair
    (RFC 6749 §4.1.3/§4.1.4 code grant, §6 refresh grant).

    Validation order (task-07 brief's own pinned route pseudocode): rate limit -> `grant_type`
    presence -> `client_id` presence AND that it names a REGISTERED client (401 `invalid_client`,
    the one 401 this endpoint ever returns — every other rejection is 400) -> grant-type-specific
    required-field checks -> the grant's own service function, which does the rest (PKCE/
    redirect/expiry/replay for a code; expiry/reuse/client/resource/scope for a refresh).

    Always returns `Cache-Control: no-store`/`Pragma: no-cache` on a 200 (RFC 6749 §5.1) — a
    plain `JSONResponse` is used (rather than relying on FastAPI's own response serialization) so
    those headers can be set directly, while `response_model=TokenResponse` still documents and
    validates the shape for OpenAPI/codegen.

    Raises:
        OAuthError: as described above; never a bare framework exception (CONVENTIONS.md §4 — no
            `try/except` in routes, mapping happens in the registered `OAuthError` handler).
    """
    client_ip = request.client.host if request.client is not None else "unknown"
    limiter.check_oauth_request(client_ip)

    if grant_type is None:
        raise OAuthError("invalid_request", "grant_type is required.")

    if client_id is None or get_client(session, client_id) is None:
        raise OAuthError("invalid_client", "Unknown client.", status_code=401)

    now = datetime.now(UTC)

    if grant_type == "authorization_code":
        if code is None:
            raise OAuthError("invalid_request", "code is required.")
        if redirect_uri is None:
            raise OAuthError("invalid_request", "redirect_uri is required.")
        if code_verifier is None:
            raise OAuthError("invalid_request", "code_verifier is required.")

        tokens = redeem_authorization_code(
            session,
            raw_code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            resource=resource or settings.mcp_resource_url,
            now=now,
            settings=settings,
        )
    elif grant_type == "refresh_token":
        if refresh_token is None:
            raise OAuthError("invalid_request", "refresh_token is required.")

        tokens = rotate_refresh_token(
            session,
            raw_refresh_token=refresh_token,
            client_id=client_id,
            resource=resource,
            scope=scope,
            now=now,
            settings=settings,
        )
    else:
        raise OAuthError(
            "unsupported_grant_type",
            "Only authorization_code and refresh_token are supported.",
        )

    body = TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
        scope=tokens.scope,
    )
    return JSONResponse(
        body.model_dump(),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.post(
    "/revoke",
    operation_id="oauth_revoke",
    status_code=200,
    response_class=Response,
    responses={
        400: {
            "description": "OAuth error — token is required.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_request",
                        "error_description": "token is required.",
                    }
                }
            },
        },
        401: {
            "description": "Unknown client_id.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_client",
                        "error_description": "Unknown client.",
                    }
                }
            },
        },
        422: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
    },
)
def oauth_revoke(
    request: Request,
    token: Annotated[str | None, Form()] = None,
    token_type_hint: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> Response:
    """Revoke one refresh or access token (RFC 7009 §2.1 token revocation request).

    docs/plans/mcp-oauth/task-08-revoke-admin-api.md: validation order mirrors `/token`'s own
    pinned pattern — rate limit -> `token` presence -> `client_id` presence AND that it names a
    REGISTERED client (the one 401 this endpoint ever returns; every other rejection is 400).
    Past that point `revoke_token` (`app.services.oauth_tokens`) does the actual work and can
    never fail: RFC 7009 §2.2 requires this endpoint to answer 200 whether or not `token` ever
    existed, belonged to this client, or was already revoked — the response carries no signal
    either way. `token_type_hint` is accepted (so a spec-compliant client's request never 422s
    for including it) but never read — `revoke_token` tries both a refresh-token and an
    access-token lookup unconditionally, which is cheap enough that the hint buys nothing.

    Always answers 200 with an empty body and `Cache-Control: no-store`/`Pragma: no-cache` (RFC
    7009 §2.2) — a plain `Response` (mirrors `oauth_token`'s own `JSONResponse` reasoning) so
    those headers are set directly on every reachable return path, success included.
    `response_class=Response` (fix round 1, review M-5) documents the 200 in `openapi.json` with
    no content, matching what the route actually returns — the same shape the admin DELETE's 204
    already gets; without it FastAPI's default declared 200 as an untyped
    `"application/json"` body, which a generated client calling `.json()` on would choke on.

    Raises:
        OAuthError: `"invalid_request"`, "token is required." (400) if `token` is absent;
            `"invalid_client"`, "Unknown client." (401) if `client_id` is absent or unregistered.
            Never raised for an unknown/foreign/already-revoked `token` — see above.
    """
    client_ip = request.client.host if request.client is not None else "unknown"
    limiter.check_oauth_request(client_ip)

    if token is None:
        raise OAuthError("invalid_request", "token is required.")

    if client_id is None or get_client(session, client_id) is None:
        raise OAuthError("invalid_client", "Unknown client.", status_code=401)

    revoke_token(session, raw_token=token, client_id=client_id, now=datetime.now(UTC))
    logger.info("oauth token revoked: client_id=%s", client_id)

    return Response(
        status_code=200,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
