"""Signed, HttpOnly admin session cookie (PRD §9): issue on login, verify on every request.

Uses `itsdangerous` (timed, signed tokens) rather than a server-side session
store — PRD §9 names no session-storage table, and a signed cookie is
enough to carry a `User.id` safely: tampering invalidates the signature,
and `require_admin` (`app.auth.deps`) re-checks the referenced row on every
request, so a soft-deleted user's cookie stops working immediately (§9)
even though the signature itself stays valid until it expires.
"""

from __future__ import annotations

import uuid

from fastapi import Request, Response
from itsdangerous import BadData, URLSafeTimedSerializer

from app.config import Settings

COOKIE_NAME = "advisordesk_session"
_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days — PRD §9 names no TTL; a reasonable default.
_SALT = "advisordesk.auth.session"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Build the itsdangerous serializer from `Settings.session_secret` (PRD §9)."""
    return URLSafeTimedSerializer(settings.session_secret.get_secret_value(), salt=_SALT)


def issue_cookie(response: Response, user_id: uuid.UUID, settings: Settings) -> None:
    """Sign `user_id` and set it as the HttpOnly session cookie on `response`.

    PRD §9: HttpOnly and `SameSite=Lax` always; `Secure` whenever `settings`
    is not configured for local development (`Settings.is_dev`) — so a
    plain-HTTP local dev server (or the test suite's `TestClient`) still
    gets the cookie sent back on the next request.

    Args:
        response: the response to attach the cookie to (the `/auth/callback` response).
        user_id: the freshly authenticated/reactivated `User.id`.
        settings: the app's `Settings`, for the signing secret and dev/prod mode.
    """
    token = _serializer(settings).dumps(str(user_id))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=not settings.is_dev,
    )


def read_user_id(request: Request, settings: Settings) -> uuid.UUID | None:
    """Return the session cookie's signed user id, or `None` if absent/invalid/expired.

    Never raises: a missing cookie, a tampered signature, an expired
    token, and a value that fails to parse as a UUID are all treated
    identically — "no session" — so `app.auth.deps.require_admin` can turn
    every one of them into a single 401 (PRD §9).
    """
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        return None

    try:
        raw = _serializer(settings).loads(token, max_age=_MAX_AGE_SECONDS)
    except BadData:
        return None

    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def clear_cookie(response: Response) -> None:
    """Delete the session cookie (PRD §5.1 `/auth/logout`)."""
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
