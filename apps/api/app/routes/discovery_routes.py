"""RFC 9728 / RFC 8414 OAuth discovery documents — the domain-root exception.

docs/plans/mcp-oauth/task-02-discovery-docs.md; docs/plans/mcp-oauth/DESIGN.md §"Endpoints".

RFC 9728 §3 and RFC 8414 §3 both mandate that a resource/authorization server's metadata
document be served at a fixed `/.well-known/...` path relative to the **origin root** — a
client discovering these documents has no other way to locate them. This is the one
sanctioned exception to CONVENTIONS.md §5's "all routes live under `/api/v1`" rule: this
router is included in `app/factory.py` with **no** `_API_PREFIX`, unlike every other router.
The endpoints these documents advertise (`authorization_endpoint`, `token_endpoint`, ...)
still live under `/api/v1/oauth/*` (task 04+) — only the discovery documents themselves sit
at the root.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.oauth_discovery import (
    authorization_server_metadata,
    protected_resource_metadata,
)
from app.config import Settings
from app.routes.deps import get_settings

router = APIRouter()

_CACHE_CONTROL = "public, max-age=3600"


@router.get(
    "/.well-known/oauth-protected-resource",
    operation_id="oauth_protected_resource_metadata",
)
def get_protected_resource_metadata(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """RFC 9728 protected-resource metadata for the `/api/v1/mcp` resource."""
    body = protected_resource_metadata(settings)
    return JSONResponse(content=body, headers={"Cache-Control": _CACHE_CONTROL})


@router.get(
    "/.well-known/oauth-protected-resource/api/v1/mcp",
    operation_id="oauth_protected_resource_metadata_mcp_path",
)
def get_protected_resource_metadata_mcp_path(
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """RFC 9728 §3.1 path-suffixed form: identical document, for clients that probe it first."""
    body = protected_resource_metadata(settings)
    return JSONResponse(content=body, headers={"Cache-Control": _CACHE_CONTROL})


@router.get(
    "/.well-known/oauth-authorization-server",
    operation_id="oauth_authorization_server_metadata",
)
def get_authorization_server_metadata(
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """RFC 8414 authorization-server metadata for this co-hosted OAuth 2.1 server."""
    body = authorization_server_metadata(settings)
    return JSONResponse(content=body, headers={"Cache-Control": _CACHE_CONTROL})
