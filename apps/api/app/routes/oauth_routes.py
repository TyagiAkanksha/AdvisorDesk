"""RFC 7591 dynamic client registration route — `POST /oauth/register` (mcp-oauth plan, task 04);
`GET /oauth/authorize` + `GET /oauth/authorize/continue` (mcp-oauth plan, task 05; RFC 6749 §4.1,
RFC 7636 PKCE); `POST /oauth/token` (mcp-oauth plan, task 07; RFC 6749 §4.1.3/§4.1.4 code grant,
§6 refresh grant).

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

from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import AdminPrincipal, resolve_admin
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
from app.services.oauth_tokens import redeem_authorization_code, rotate_refresh_token

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


def _issue_code_and_redirect(
    session: Session,
    pending: PendingAuthorization,
    principal: AdminPrincipal,
    settings: Settings,
) -> RedirectResponse:
    """Mint a single-use authorization code for `pending`/`principal` and 302-redirect with it.

    Module-level (not a route) so mcp-oauth task 06's consent-approval endpoint can reuse this
    exact issuance-and-redirect step once a consent decision has been recorded, without
    duplicating it.

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
    separator = "&" if "?" in pending.redirect_uri else "?"
    response = RedirectResponse(
        f"{pending.redirect_uri}{separator}{urlencode(params)}",
        status_code=302,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    clear_pending_cookie(response)
    return response


@router.get(
    "/authorize/continue",
    operation_id="oauth_authorize_continue",
    responses={
        307: {
            "description": (
                "No admin session yet — redirects to /api/v1/auth/login (the Google-login "
                "bridge); the pending-authorization cookie is left in place."
            ),
        },
        302: {
            "description": (
                "Either a single-use authorization code was issued (redirects to the client's "
                "own redirect_uri with code/state), or the resolved admin is not allowlisted "
                "(redirects with error=access_denied/state)."
            ),
        },
        400: {
            "description": (
                "OAuth error — no (or an invalid/expired/tampered) pending-authorization cookie."
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
    """Resume a parked `/authorize` request: bridge to Google login if needed, then issue a code.

    DESIGN.md §"End-to-end flow" steps 5-6, §"Google bridge + consent": reads the signed
    pending-authorization cookie `/authorize` set. No cookie (missing, tampered, or expired) is a
    400 `invalid_request` — never a 500. With a valid pending request but no admin session yet,
    307-redirects to `/api/v1/auth/login` (`app.routes.auth_routes.auth_login`) — the SAME cookie
    survives that detour (`Path=/api/v1`, and `/auth/callback`'s own success redirect lands back
    here, per that route's own amendment) so a second visit to this route, post-login, resumes
    exactly where it left off. Once an admin session resolves, re-checks the allowlist (`resolve_
    admin` itself does not — only `/auth/callback` and this route's own check do) before issuing
    the code, since a session minted while still allowlisted can outlive a later allowlist edit.

    No consent screen yet (mcp-oauth task 06 inserts one here); this task's `continue` goes
    straight from a resolved, allowlisted admin to a minted code, so the core flow is provable in
    task 07's `/token` exchange.

    Raises:
        OAuthError: no valid pending-authorization cookie (`"invalid_request"`, 400).
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

    return _issue_code_and_redirect(session, pending, principal, settings)


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
