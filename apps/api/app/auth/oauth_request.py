"""Signed, timestamped pending-authorization cookie (mcp-oauth plan, task 05).

Parks a validated `/oauth/authorize` request across the Google-login bridge round trip:
`/authorize` mints this cookie and 303s to `/authorize/continue`; `/authorize/continue` reads it
back (after the admin session exists, possibly after a `/auth/login` -> `/auth/callback` detour)
to know which client/redirect/PKCE-challenge/resource/scope/state the caller originally asked for.

Mirrors `app.auth.state`'s own signed-cookie pattern (`itsdangerous.URLSafeTimedSerializer`,
`Settings.session_secret`, a distinct `_SALT` so this cookie can never be replayed as a session
cookie, a state token, or vice versa) rather than inventing a new signing scheme. Unlike
`app.auth.state`'s opaque random payload, this cookie's payload IS the pending request itself
(`PendingAuthorization`, a `dataclasses.asdict`-serializable frozen dataclass) — `itsdangerous`
already handles nested dict/str/None JSON-shaped payloads, and every field here is a plain string
or `None`, so no custom (de)serialization is needed beyond `dataclasses.asdict`/the dataclass
constructor.

`nonce` (`secrets.token_urlsafe(16)`) carries no meaning to THIS task — no consent screen exists
yet (task 05's own brief: "No consent screen yet ... this task's `continue` goes straight to the
code") — but is minted and round-tripped now so task 06's consent form has something unpredictable
to bind its own CSRF-style form-to-pending-request check to, without this task needing to touch
`PendingAuthorization`'s shape again.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from fastapi import Response
from itsdangerous import BadData, URLSafeTimedSerializer

from app.config import Settings

AUTHORIZE_COOKIE_NAME = "advisordesk_oauth_authz"
AUTHORIZE_MAX_AGE_SECONDS = 600  # 10 minutes — generous for the Google-login detour.
_SALT = "advisordesk.auth.oauth-authorize"


@dataclass(frozen=True)
class PendingAuthorization:
    """A validated `/oauth/authorize` request, parked pending the Google-login bridge.

    Attributes:
        client_id: the registered `OAuthClient.client_id` the request validated against.
        redirect_uri: the exact, registered redirect URI the eventual code/error redirects to.
        code_challenge: the RFC 7636 PKCE challenge the eventual `/token` exchange must satisfy.
        resource: the RFC 8707 resource indicator (defaults to `Settings.mcp_resource_url`).
        scope: always `"mcp"` (the only supported scope).
        state: the caller's opaque `state`, echoed back verbatim on both success and error
            redirects (RFC 6749 §4.1.2/§4.1.2.1); `None` if the caller didn't send one.
        nonce: `secrets.token_urlsafe(16)` — unused by this task; task 06 binds the consent form
            to it.
    """

    client_id: str
    redirect_uri: str
    code_challenge: str
    resource: str
    scope: str
    state: str | None
    nonce: str


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Build the itsdangerous serializer from `Settings.session_secret`, this module's own salt."""
    return URLSafeTimedSerializer(settings.session_secret.get_secret_value(), salt=_SALT)


def mint_pending_authorization(pending: PendingAuthorization, settings: Settings) -> str:
    """Sign `pending` into an opaque token suitable for `set_pending_cookie`."""
    return _serializer(settings).dumps(dataclasses.asdict(pending))


def read_pending_authorization(
    value: str | None, settings: Settings
) -> PendingAuthorization | None:
    """Recover a `PendingAuthorization` from a cookie value, or `None` if it can't be trusted.

    Never raises: a missing cookie (`value is None`), a tampered/garbage signature, an expired
    token (older than `AUTHORIZE_MAX_AGE_SECONDS`), and a validly-signed payload that doesn't
    match `PendingAuthorization`'s shape are all treated identically — "no pending authorization"
    — so the `/authorize/continue` route can turn every one of them into a single 400
    `invalid_request`, never a 500 from a signature-verification or shape-mismatch crash.

    Args:
        value: the raw `AUTHORIZE_COOKIE_NAME` cookie value, or `None` if absent.
        settings: the app's `Settings`, for the signing secret.
    """
    if value is None:
        return None

    try:
        raw: Any = _serializer(settings).loads(value, max_age=AUTHORIZE_MAX_AGE_SECONDS)
    except BadData:
        return None

    if not isinstance(raw, dict):
        return None

    expected_fields = {field.name for field in dataclasses.fields(PendingAuthorization)}
    if set(raw) != expected_fields:
        return None
    if not all(isinstance(raw[key], str) for key in expected_fields - {"state"}):
        return None
    if raw["state"] is not None and not isinstance(raw["state"], str):
        return None

    return PendingAuthorization(**raw)


def set_pending_cookie(response: Response, value: str, settings: Settings) -> None:
    """Set the signed pending-authorization cookie on `response`.

    `HttpOnly` and `SameSite=Lax` always; `Secure` whenever `settings` is not configured for
    local development (mirrors `app.auth.sessions.issue_cookie`'s identical flags). `Path=/api/v1`
    scopes it to this app's own API prefix — narrower than the session cookie's default (root)
    path, since this cookie only ever needs to be read back by `/api/v1/oauth/authorize/continue`.
    """
    response.set_cookie(
        AUTHORIZE_COOKIE_NAME,
        value,
        max_age=AUTHORIZE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=not settings.is_dev,
        path="/api/v1",
    )


def clear_pending_cookie(response: Response) -> None:
    """Delete the pending-authorization cookie — single-use, cleared once a code is issued."""
    response.delete_cookie(AUTHORIZE_COOKIE_NAME, path="/api/v1", httponly=True, samesite="lax")
