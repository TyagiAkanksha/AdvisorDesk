"""RFC 9728 protected-resource + RFC 8414 authorization-server metadata builders.

docs/plans/mcp-oauth/task-02-discovery-docs.md; docs/plans/mcp-oauth/DESIGN.md
§"Conformance target" / §"End-to-end flow" steps 1-3 / §"Endpoints". This module is pure
functions of `Settings` — no I/O, no FastAPI — so `app.routes.discovery_routes` (the HTTP
surface) and `app.mcp` (task 03's 401 `WWW-Authenticate` challenge) can both depend on it
without either pulling in the other (CONVENTIONS.md §2: `app.auth` may import
`app.services`/`app.models`/`app.config` only, never `app.routes`).
"""

from __future__ import annotations

from app.config import Settings

#: RFC 9728 §3: the well-known path for OAuth 2.0 Protected Resource Metadata.
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
#: RFC 8414 §3: the well-known path for OAuth 2.0 Authorization Server Metadata.
AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server"


def protected_resource_metadata(settings: Settings) -> dict[str, object]:
    """Build the RFC 9728 protected-resource metadata document for the MCP endpoint.

    `resource` and `authorization_servers` are the two RFC-required fields (DESIGN.md
    §"Conformance target": "including an `authorization_servers` array (>=1) and the
    `resource` identifier") — `resource` is the canonical MCP resource URI
    (`Settings.mcp_resource_url`, task 01), and this server plays both OAuth roles
    co-hosted, so `authorization_servers` names its own issuer.
    """
    return {
        "resource": settings.mcp_resource_url,
        "authorization_servers": [settings.oauth_issuer_url],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
        "resource_name": "AdvisorDesk MCP",
    }


def authorization_server_metadata(settings: Settings) -> dict[str, object]:
    """Build the RFC 8414 authorization-server metadata document.

    Endpoint paths mirror DESIGN.md §"Endpoints" exactly (`/api/v1/oauth/{register,authorize,
    token,revoke}`, task 04+); `code_challenge_methods_supported == ["S256"]` and
    `token_endpoint_auth_methods_supported == ["none"]` reflect the OAuth 2.1 public-client,
    PKCE-mandatory flow DESIGN.md §"Conformance target" pins for this authorization server.
    """
    issuer = settings.oauth_issuer_url
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/api/v1/oauth/authorize",
        "token_endpoint": f"{issuer}/api/v1/oauth/token",
        "registration_endpoint": f"{issuer}/api/v1/oauth/register",
        "revocation_endpoint": f"{issuer}/api/v1/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }


def www_authenticate_challenge(settings: Settings) -> str:
    """Build the RFC 9728 §5.1 `WWW-Authenticate` challenge for an unauthenticated MCP request.

    Task 03 embeds this in every `/api/v1/mcp` 401 (DESIGN.md §"End-to-end flow" step 1) so a
    calling client discovers the protected-resource metadata document without prior knowledge
    of this server's OAuth wiring.
    """
    return f'Bearer resource_metadata="{settings.oauth_issuer_url}{PROTECTED_RESOURCE_PATH}"'
