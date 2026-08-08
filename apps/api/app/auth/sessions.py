"""Signed, HttpOnly admin session cookie (PRD §9): issue on login, verify on every request.

Uses `itsdangerous` (timed, signed tokens) rather than a server-side session
store — PRD §9 names no session-storage table, and a signed cookie is
enough to carry a `User.id` safely: tampering invalidates the signature,
and `require_admin` (`app.auth.deps`) re-checks the referenced row on every
request, so a soft-deleted user's cookie stops working immediately (§9)
even though the signature itself stays valid until it expires.

Phase-6 task-05 (PRD §9 logout revocation, phase-2 review finding t01-M6): the payload is now
the signed dict `{"uid": str(user_id), "epoch": int}` rather than a bare `str(user_id)` — `epoch`
mirrors `users.session_epoch` at issuance time, so `require_admin` can compare it against the
row's CURRENT value and reject a cookie the instant `/auth/logout` bumps that counter
(`app.services.users.bump_session_epoch`), not just when the browser that held it clears its own
jar. `read_user_id` is replaced by `read_session`, returning `(user_id, epoch)`. Old, pre-task-05
cookies (a bare signed string, not this dict shape) simply fail to match and read as `None` — the
same "no session" outcome as a missing/tampered cookie — so the one admin account this app
supports at deploy time just re-logs in once; no migration/compat shim for the payload shape
itself is warranted at this scale.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request, Response
from itsdangerous import BadData, URLSafeTimedSerializer

from app.config import Settings

COOKIE_NAME = "advisordesk_session"
_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days — PRD §9 names no TTL; a reasonable default.
_SALT = "advisordesk.auth.session"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Build the itsdangerous serializer from `Settings.session_secret` (PRD §9)."""
    return URLSafeTimedSerializer(settings.session_secret.get_secret_value(), salt=_SALT)


def issue_cookie(
    response: Response, user_id: uuid.UUID, session_epoch: int, settings: Settings
) -> None:
    """Sign `{user_id, session_epoch}` and set it as the HttpOnly session cookie on `response`.

    PRD §9: HttpOnly and `SameSite=Lax` always; `Secure` whenever `settings`
    is not configured for local development (`Settings.is_dev`) — so a
    plain-HTTP local dev server (or the test suite's `TestClient`) still
    gets the cookie sent back on the next request.

    Args:
        response: the response to attach the cookie to (the `/auth/callback` response).
        user_id: the freshly authenticated/reactivated `User.id`.
        session_epoch: `User.session_epoch` at issuance — a re-login right after `/auth/logout`
            passes the just-bumped value, so the new cookie is immediately valid again.
        settings: the app's `Settings`, for the signing secret and dev/prod mode.
    """
    token = _serializer(settings).dumps({"uid": str(user_id), "epoch": session_epoch})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=not settings.is_dev,
    )


def read_session(request: Request, settings: Settings) -> tuple[uuid.UUID, int] | None:
    """Return `(user_id, session_epoch)` from the session cookie, or `None` if absent/invalid.

    Never raises: a missing cookie, a tampered signature, an expired token, a legacy
    pre-task-05 payload (a bare signed string rather than this `{"uid", "epoch"}` dict), a dict
    missing the `"epoch"` key, and a non-int `"epoch"` value are all treated identically — "no
    session" — so `app.auth.deps.require_admin` can turn every one of them into a single 401
    (PRD §9).
    """
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        return None

    try:
        raw: Any = _serializer(settings).loads(token, max_age=_MAX_AGE_SECONDS)
    except BadData:
        return None

    if not isinstance(raw, dict):
        return None  # legacy pre-task-05 payload (a bare string) or some other shape

    uid = raw.get("uid")
    epoch = raw.get("epoch")
    if not isinstance(uid, str) or not isinstance(epoch, int):
        return None

    try:
        return uuid.UUID(uid), epoch
    except ValueError:
        return None


def clear_cookie(response: Response) -> None:
    """Delete the session cookie (PRD §5.1 `/auth/logout`)."""
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
