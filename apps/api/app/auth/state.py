"""Signed, timestamped OAuth `state` token — login-CSRF defense (PRD §9; phase-6 task-05).

Phase-2 review finding t01-M7: `/auth/callback` previously accepted ANY `state` value at all
(Google echoes back whatever `/auth/login` sent, but nothing verified it came from THIS
browser's own login attempt) — an attacker could start their own `/auth/login`, capture Google's
redirect, and trick a victim into visiting `/auth/callback` with the attacker's `code`, binding
the victim's session to an account the attacker controls (login-CSRF).

The fix is two checks, both required (`app.routes.auth_routes.auth_callback`):

1. **Signature + age** (this module): `mint_state` signs an opaque random token with
   `itsdangerous.URLSafeTimedSerializer`, same pattern as `app.auth.sessions`, but its own salt
   so a state token can never be replayed as a session cookie or vice versa. `verify_state`
   checks the signature and that the token is no older than `STATE_MAX_AGE_SECONDS`.
2. **Double-submit cookie** (`app.routes.auth_routes`): the signature alone does not stop
   login-CSRF — an attacker can mint their OWN validly-signed state from their own
   `/auth/login` call. `/auth/login` also sets the SAME state as an HttpOnly cookie
   (`advisordesk_oauth_state`) on the victim's browser; `/auth/callback` requires the query
   `state` to match that cookie too, which an attacker cannot forge cross-origin.

`STATE_MAX_AGE_SECONDS` is read as a live module global inside `verify_state` (not captured as a
function-default value, which binds once at def-time) so tests can `monkeypatch.setattr(
"app.auth.state.STATE_MAX_AGE_SECONDS", 0)` to exercise expiry deterministically.
"""

from __future__ import annotations

import secrets

from itsdangerous import BadData, URLSafeTimedSerializer

from app.config import Settings

STATE_COOKIE_NAME = "advisordesk_oauth_state"
STATE_MAX_AGE_SECONDS = 600  # 10 minutes — generous for a user to complete Google's consent UI.
_SALT = "advisordesk.auth.oauth-state"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Build the itsdangerous serializer from `Settings.session_secret` (PRD §9).

    Reuses `session_secret` (same secret `app.auth.sessions` signs cookies with) but a distinct
    `_SALT`, so a state token and a session cookie are never interchangeable even though both
    are ultimately signed with the same underlying key.
    """
    return URLSafeTimedSerializer(settings.session_secret.get_secret_value(), salt=_SALT)


def mint_state(settings: Settings) -> str:
    """Mint a fresh, signed, timestamped OAuth `state` token.

    The payload itself (`secrets.token_urlsafe(16)`) carries no meaning — it exists only so the
    signature has something unpredictable to sign; the signature plus the automatic
    `itsdangerous` timestamp are what `verify_state` checks.
    """
    return _serializer(settings).dumps(secrets.token_urlsafe(16))


def verify_state(value: str, settings: Settings) -> bool:
    """Return whether `value` is a validly signed, not-yet-expired state token.

    Never raises: a garbage string, a tampered signature, and an expired token all fail the same
    way, since `/auth/callback` treats any failure identically (403, `ForbiddenError`) regardless
    of which specific `itsdangerous` exception fired.

    Args:
        value: the `state` query parameter `/auth/callback` received.
        settings: the app's `Settings`, for the signing secret.
    """
    try:
        _serializer(settings).loads(value, max_age=STATE_MAX_AGE_SECONDS)
    except BadData:
        return False
    return True
