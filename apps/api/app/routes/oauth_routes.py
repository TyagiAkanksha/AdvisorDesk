"""RFC 7591 dynamic client registration route — `POST /oauth/register` (mcp-oauth plan, task 04).

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

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.oauth import ClientRegistrationRequest, ClientRegistrationResponse
from app.routes.deps import get_rate_limiter, get_session, get_settings
from app.routes.ratelimit import RateLimiter
from app.services.errors import OAuthError
from app.services.oauth_clients import (
    count_clients,
    prune_stale_clients,
    register_client,
    validate_redirect_uri,
)

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
