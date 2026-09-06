"""Shared Google-OAuth test seam: a fake client + login helpers.

CONVENTIONS.md §10: mock ONLY the true external seam (Google OAuth) — this
task's tests, and every later admin-route test that needs an authenticated
session, drive the real HTTP surface via `login_as` rather than reaching
into cookies or sessions by hand. Kept deliberately small (task-01 brief):
one fake client, one login helper — `begin_login` was added by phase-6
task-05 (OAuth state CSRF) as the one extra seam `login_as` itself needed
to keep working once `/auth/callback` verifies `state` against a signed,
double-submit cookie minted by `/auth/login` (see `begin_login`'s
docstring); every existing caller of `login_as` is unaffected, since its
signature and observable contract (a live session lands in `client`'s
cookie jar) are unchanged.
"""

from __future__ import annotations

import secrets
import urllib.parse
from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from app.auth.oauth import GoogleIdentity

_LOGIN_PATH = "/api/v1/auth/login"
_CALLBACK_PATH = "/api/v1/auth/callback"


@dataclass
class FakeGoogleOAuthClient:
    """Fake `app.auth.oauth.GoogleOAuthClient` — the injected `oauth_client` test seam.

    Structurally matches the `GoogleOAuthClient` protocol
    (`authorization_url(state) -> str`, `exchange_code(code) -> GoogleIdentity`)
    without making any real HTTP call to Google. `identities` is the
    per-test configuration point: register whatever `GoogleIdentity` a given
    opaque `code` should exchange to (see `login_as`, which drives this for
    the common case).
    """

    consent_url: str = "https://accounts.google.com/o/oauth2/fake-consent"
    identities: dict[str, GoogleIdentity] = field(default_factory=dict)

    def authorization_url(self, state: str) -> str:
        """Return a deterministic fake consent URL carrying `state` as a query param."""
        return f"{self.consent_url}?state={state}"

    def exchange_code(self, code: str) -> GoogleIdentity:
        """Return the `GoogleIdentity` a test registered for `code` (see `identities`)."""
        return self.identities[code]


def begin_login(client: TestClient) -> str:
    """Hit `GET /auth/login` and return the real, signed `state` it minted.

    Phase-6 task-05 (PRD §9 OAuth state CSRF): `/auth/login` mints a signed
    `state` via `app.auth.state.mint_state` and sets it as a double-submit
    cookie (`advisordesk_oauth_state`) on its own redirect response — this
    helper drives that request and returns the `state` value carried on
    the redirect `Location`. The matching cookie lands in `client`'s
    cookie jar as a side effect of this call (`TestClient` persists
    `Set-Cookie` headers across requests made on the same client), so a
    SUBSEQUENT `/auth/callback` request on the SAME `client` automatically
    carries a matching cookie, exactly like a real browser's double-submit
    round trip. `follow_redirects=False` is required here: the redirect
    target is the fake OAuth client's consent URL
    (`FakeGoogleOAuthClient.consent_url`), an unreachable off-app address.

    Used by `login_as` below, and directly by tests that want a
    callback-only round trip driven by a real login-minted `state` rather
    than `login_as`'s own bundled fake identity.

    Args:
        client: a `TestClient` over an app built with a `FakeGoogleOAuthClient`
            injected as `oauth_client`.

    Returns:
        The `state` query parameter from `/auth/login`'s redirect `Location`.
    """
    response = client.get(_LOGIN_PATH, follow_redirects=False)
    location = response.headers["location"]
    query = urllib.parse.urlparse(location).query
    return urllib.parse.parse_qs(query)["state"][0]


def login_as(
    client: TestClient,
    email: str,
    *,
    name: str = "Test Admin",
    avatar_url: str = "https://example.com/avatar.png",
) -> GoogleIdentity:
    """Drive the fake OAuth flow end to end so `client`'s cookie jar holds a live admin session.

    Registers a fresh opaque code for `email` against the `FakeGoogleOAuthClient`
    the app under test was built with (`create_app(oauth_client=...)`, read
    back from `client.app.state.oauth_client`), then drives `/api/v1/auth/login`
    followed by `/api/v1/auth/callback` with that code — exactly as a real
    browser's OAuth round trip would, and (phase-6 task-05) required for
    `/auth/callback`'s own signed-state + double-submit-cookie verification
    to succeed at all. `begin_login` (above) does the login leg and hands
    back the state that landed in `client`'s cookie jar; the callback call
    below reuses it, landing the signed session cookie `issue_cookie` sets
    onto `client`. Reused by every later admin-route test (task-01 brief,
    Interfaces block) so callers never need to know the cookie's name,
    format, or (since task-05) the state CSRF mechanics either.

    Args:
        client: a `TestClient` over an app built with a `FakeGoogleOAuthClient`
            injected as `oauth_client`.
        email: the identity's email. Must be present in the app's
            `ADMIN_EMAILS` allowlist for the login to succeed.
        name: the identity's display name.
        avatar_url: the identity's avatar URL.

    Returns:
        The `GoogleIdentity` registered for this login.

    Raises:
        AssertionError: if the callback did not return a success/redirect
            status (i.e. the login did not go through).
    """
    oauth_client: FakeGoogleOAuthClient = client.app.state.oauth_client  # type: ignore[attr-defined]
    code = secrets.token_urlsafe(16)
    identity: GoogleIdentity = {"email": email, "name": name, "avatar_url": avatar_url}
    oauth_client.identities[code] = identity

    state = begin_login(client)
    response = client.get(
        _CALLBACK_PATH,
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    assert response.status_code < 400, (
        f"login_as callback failed: {response.status_code} {response.text}"
    )

    return identity
