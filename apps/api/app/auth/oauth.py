"""Google OAuth: the `GoogleOAuthClient` seam plus the real httpx-backed implementation.

PRD §5.1 / CONVENTIONS.md §10: `GoogleOAuthClient` is the one true external
seam this app mocks in tests (`FakeGoogleOAuthClient`,
`tests/auth_helpers.py`); `HttpxGoogleOAuthClient` talks to Google's real
OAuth2 + OpenID endpoints over `httpx`. Injected via
`create_app(oauth_client=...)` onto `app.state.oauth_client`
(`app/routes/deps.py::get_oauth_client` reads it back for routes).
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.models.schemas.auth import GoogleIdentity

__all__ = ["GoogleIdentity", "GoogleOAuthClient", "HttpxGoogleOAuthClient"]

_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "openid email profile"
_REQUEST_TIMEOUT_SECONDS = 10.0


class GoogleOAuthClient(Protocol):
    """The OAuth collaborator `app.auth`/`app.routes.auth_routes` depend on.

    Structurally implemented by `HttpxGoogleOAuthClient` (real Google) and
    `tests/auth_helpers.py::FakeGoogleOAuthClient` (the test seam) — a
    `Protocol`, not an ABC, so the fake needs no inheritance relationship
    to satisfy it (CONVENTIONS.md §10 injectable seams).
    """

    def authorization_url(self, state: str) -> str:
        """Return the Google consent URL the browser should be redirected to."""
        ...

    def exchange_code(self, code: str) -> GoogleIdentity:
        """Exchange an authorization `code` for the authenticated Google identity."""
        ...


class HttpxGoogleOAuthClient:
    """The real `GoogleOAuthClient`, built from `Settings` (PRD §5.1)."""

    def __init__(self, *, client_id: str, client_secret: str, redirect_uri: str) -> None:
        """Store the three values a Google OAuth2 authorization-code exchange needs.

        Args:
            client_id: `GOOGLE_CLIENT_ID`.
            client_secret: `GOOGLE_CLIENT_SECRET`'s plaintext value (already
                unwrapped via `.get_secret_value()` — CONVENTIONS.md §7).
            redirect_uri: the fixed, Google-console-registered callback URL
                for this deployment (`Settings.google_redirect_uri`).
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    @classmethod
    def from_settings(cls, settings: Settings) -> HttpxGoogleOAuthClient:
        """Build the real client from `Settings` — the one non-test constructor (PRD §5.1)."""
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret.get_secret_value(),
            redirect_uri=settings.google_redirect_uri,
        )

    def authorization_url(self, state: str) -> str:
        """Build Google's consent-screen URL, carrying `state` for CSRF round-tripping."""
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            "state": state,
            "access_type": "online",
        }
        return f"{_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, code: str) -> GoogleIdentity:
        """Exchange `code` for an access token, then fetch and shape the caller's identity."""
        with httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            token_response = client.post(
                _TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            userinfo_response = client.get(
                _USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_response.raise_for_status()
            payload = userinfo_response.json()

        return GoogleIdentity(
            email=payload["email"],
            name=payload.get("name"),
            avatar_url=payload.get("picture"),
        )
