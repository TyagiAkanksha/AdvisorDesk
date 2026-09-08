"""`/oauth/authorize` request validation against the registered client (mcp-oauth plan, task 05;
RFC 6749 §4.1.1 authorization request / §4.1.2.1 error response; RFC 7636 PKCE).

Import-linter contract ("app.auth imports only app.services, app.models, and app.config"): this
module may import `app.services.oauth_clients` (`get_client`), `app.services.errors`
(`OAuthError`/`OAuthRedirectError`), `app.services.pkce`, and `app.auth.oauth_request`
(`PendingAuthorization`) — no `app.routes`, no `app.mcp`.

Validation order is pinned exactly (task-05 brief Interfaces block, DESIGN.md §"End-to-end flow"
+ RFC 6749 §4.1.2.1): `client_id`/`redirect_uri` are checked FIRST and NEVER redirect on failure —
an unknown client or an unregistered redirect is exactly the situation RFC 6749 §4.1.2.1 forbids
redirecting for, since there is nothing yet established as safe to redirect TO. Every later check
(response_type, PKCE challenge/method, scope, resource) redirects to the now-verified
`redirect_uri`, since by that point RFC 6749 §4.1.2.1's precondition is satisfied.
"""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.auth.oauth_request import PendingAuthorization
from app.config import Settings
from app.services.errors import OAuthError, OAuthRedirectError
from app.services.oauth_clients import get_client
from app.services.pkce import is_valid_code_challenge


def validate_authorize_request(
    session: Session,
    *,
    client_id: str | None,
    redirect_uri: str | None,
    response_type: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    scope: str | None,
    resource: str | None,
    state: str | None,
    settings: Settings,
) -> PendingAuthorization:
    """Validate one `/oauth/authorize` request against the registered client (RFC 6749 §4.1.1).

    Steps 1-2 (client_id/redirect_uri) NEVER redirect on failure (RFC 6749 §4.1.2.1) — every
    later step redirects to the now-verified `redirect_uri`, with `state` preserved when the
    caller sent one.

    Args:
        session: the caller's `Session` — a read-only `get_client` lookup, never written to.
        client_id: the caller's `client_id` query param.
        redirect_uri: the caller's `redirect_uri` query param — must exact-match one of the
            registered client's `redirect_uris`.
        response_type: the caller's `response_type` query param — only `"code"` is supported.
        code_challenge: the caller's RFC 7636 PKCE `code_challenge` query param.
        code_challenge_method: the caller's RFC 7636 PKCE `code_challenge_method` query param —
            only `"S256"` is supported (`"plain"` or absent is rejected).
        scope: the caller's `scope` query param — only `"mcp"`, or absent/empty (defaulting to
            `"mcp"`), is supported.
        resource: the caller's RFC 8707 `resource` query param — only `settings.mcp_resource_url`,
            or absent/empty (defaulting to it), is supported.
        state: the caller's opaque `state` query param, echoed back on every error/success
            redirect when not `None`.
        settings: the app's `Settings`, for `mcp_resource_url`.

    Returns:
        A `PendingAuthorization` ready to be signed into the pending-authorization cookie.

    Raises:
        OAuthError: `client_id` is absent or unregistered (`"invalid_client"`, 400), or
            `redirect_uri` is absent or not on the client's registered allowlist
            (`"invalid_redirect_uri"`, 400) — never a redirect (RFC 6749 §4.1.2.1).
        OAuthRedirectError: any other validation failure — `response_type != "code"`
            (`"unsupported_response_type"`), a missing/malformed `code_challenge`
            (`"invalid_request"`), `code_challenge_method != "S256"` (`"invalid_request"`), an
            unsupported `scope` (`"invalid_scope"`), or an unsupported `resource`
            (`"invalid_target"`) — redirects to the now-verified `redirect_uri`.
    """
    client = get_client(session, client_id) if client_id is not None else None
    if client is None:
        raise OAuthError("invalid_client", "Unknown client.", status_code=400)

    if redirect_uri is None or redirect_uri not in client.redirect_uris:
        raise OAuthError("invalid_redirect_uri", "redirect_uri is not registered for this client.")

    if response_type != "code":
        raise OAuthRedirectError(
            "unsupported_response_type",
            "Only response_type=code is supported.",
            redirect_uri,
            state,
        )

    if code_challenge is None or not is_valid_code_challenge(code_challenge):
        raise OAuthRedirectError(
            "invalid_request",
            "code_challenge is required (PKCE S256).",
            redirect_uri,
            state,
        )

    if code_challenge_method != "S256":
        raise OAuthRedirectError(
            "invalid_request",
            "code_challenge_method must be S256.",
            redirect_uri,
            state,
        )

    if scope not in (None, "", "mcp"):
        raise OAuthRedirectError(
            "invalid_scope",
            "Only scope=mcp is supported.",
            redirect_uri,
            state,
        )

    if resource not in (None, "", settings.mcp_resource_url):
        raise OAuthRedirectError(
            "invalid_target",
            "resource must be the MCP endpoint of this server.",
            redirect_uri,
            state,
        )

    return PendingAuthorization(
        client_id=client.client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        resource=settings.mcp_resource_url,
        scope="mcp",
        state=state,
        nonce=secrets.token_urlsafe(16),
    )
