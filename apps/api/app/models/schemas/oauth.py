"""RFC 7591 dynamic client registration DTOs — `POST /api/v1/oauth/register`'s wire shape
(mcp-oauth plan, task 04; docs/plans/mcp-oauth/DESIGN.md §"End-to-end flow" step 4: "Claude ->
POST /register (DCR) with its redirect_uris + name -> { client_id, ... } (public client, no
secret)"). `TokenResponse` (mcp-oauth plan, task 07) is `POST /api/v1/oauth/token`'s wire shape
(RFC 6749 §4.1.4/§5.1 access token response). `ConnectedApp`/`ConnectedAppsResponse` (mcp-oauth
plan, task 08; docs/plans/mcp-oauth/task-08-revoke-admin-api.md) are `GET /api/v1/oauth/clients`'s
wire shape — the admin "Connected apps" page's list of registered clients.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClientRegistrationRequest(BaseModel):
    """RFC 7591 §3.1 client registration request — only the fields this server understands.

    `extra="ignore"`: a real DCR client (e.g. claude.ai) sends additional RFC 7591 §2 metadata
    fields this server has no use for (`client_uri`, `contacts`, `logo_uri`, ...). Ignoring them
    — rather than 422ing on an unrecognized field — is this task's own acceptance criterion:
    "claude.ai's extra DCR fields ... never 422".

    `redirect_uris` is `list[str] | None` rather than a required, non-empty field: "required" is
    enforced at the ROUTE level as an RFC-shaped `invalid_client_metadata` `OAuthError`, not a
    generic Pydantic 422 — the two failure shapes render differently
    (`app.routes.errors._oauth_error_handler` vs. `_validation_error_handler`), and RFC 7591 §3.2.2
    reserves `invalid_client_metadata` for exactly this "a required field is missing" case.
    """

    model_config = ConfigDict(extra="ignore")

    redirect_uris: list[str] | None = None
    client_name: str | None = Field(default=None, max_length=200)
    token_endpoint_auth_method: str | None = None
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    scope: str | None = None


class ClientRegistrationResponse(BaseModel):
    """RFC 7591 §3.2.1 client information response — `POST /register`'s 201 wire shape.

    This server issues only public clients (`token_endpoint_auth_method == "none"`, no client
    secret — DESIGN.md's end-to-end flow), scoped to `mcp` — both fixed by a `Literal` default
    rather than echoed from the request, since this server never issues anything else.
    """

    client_id: str
    client_id_issued_at: int
    client_name: str
    redirect_uris: list[str]
    token_endpoint_auth_method: Literal["none"] = "none"
    grant_types: list[str]
    response_types: list[str]
    scope: Literal["mcp"] = "mcp"


class TokenResponse(BaseModel):
    """RFC 6749 §4.1.4/§5.1 access token response — `POST /api/v1/oauth/token`'s 200 wire shape.

    Returned for BOTH the `authorization_code` and `refresh_token` grants (mcp-oauth plan, task
    07) — a refresh always mints a brand-new pair (rotation), so the response shape never needs to
    distinguish which grant produced it.
    """

    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str


class ConnectedApp(BaseModel):
    """`GET /api/v1/oauth/clients`'s per-client wire shape (mcp-oauth plan, task 08).

    `model_config = ConfigDict(from_attributes=True)`: maps directly from an
    `app.services.oauth_clients.ConnectedAppRow` (a frozen dataclass with the exact same field
    names) — field-for-field, no manual construction call site needed.
    """

    model_config = ConfigDict(from_attributes=True)

    client_id: str
    client_name: str
    redirect_uris: list[str]
    created_at: datetime
    consent_granted_at: datetime | None
    active_access_tokens: int
    active_refresh_tokens: int
    last_used_at: datetime | None
    latest_expires_at: datetime | None


class ConnectedAppsResponse(BaseModel):
    """`GET /api/v1/oauth/clients`'s top-level wire shape — one `items` list, task-08 brief."""

    items: list[ConnectedApp]
