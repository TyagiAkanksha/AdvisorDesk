"""Authorization-code issuance (mcp-oauth plan, task 05; RFC 6749 §4.1.2 + RFC 7636).

Task 07 adds consumption (the `/token` code-exchange grant); this module only mints. CONVENTIONS.md
§3: session-first, `flush()` — never `commit()` — the caller (the route's `get_session` dependency)
owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.oauth import OAuthAuthorizationCode
from app.services.token_hashing import generate_token

_CODE_PREFIX = "adkac_"


def issue_authorization_code(
    session: Session,
    *,
    client_id: str,
    user_id: uuid.UUID,
    redirect_uri: str,
    code_challenge: str,
    resource: str,
    scope: str,
    now: datetime,
    ttl_seconds: int,
) -> str:
    """Mint and persist one single-use authorization code (RFC 6749 §4.1.2, RFC 7636).

    Only the sha256 hash of the code is ever persisted (`app.services.token_hashing.hash_token`,
    via `generate_token`) — the raw value exists only transiently, in this function's return value
    and the redirect URL it's placed on.

    Args:
        session: the caller's `Session`. Flushed (never committed) so `created_at` (a server-side
            default) is populated before `expires_at` is computed relative to it — mirrors
            `app.services.oauth_clients.register_client`'s identical flush-before-read pattern.
        client_id: the registered `OAuthClient.client_id` this code is bound to.
        user_id: the authenticated admin `User.id` this code is bound to.
        redirect_uri: the exact redirect URI this code is bound to (RFC 6749 §4.1.3's exact-match
            requirement is enforced at `/token` exchange time, task 07 — this only records it).
        code_challenge: the RFC 7636 PKCE challenge this code is bound to.
        resource: the RFC 8707 resource indicator this code is bound to.
        scope: always `"mcp"`.
        now: the reference "current time" — explicit, not `datetime.now(UTC)` read internally
            (CONVENTIONS.md §10's injectable-clock seam), so a caller controls `expires_at`
            precisely.
        ttl_seconds: how many seconds after `now` the code expires (`Settings.
            oauth_auth_code_ttl_seconds`, default 60 — mcp-oauth Global Constraints).

    Returns:
        The raw code (`"adkac_" + token_urlsafe(32)`) — hand this back to the caller exactly once,
        on the `/authorize/continue` redirect; never persisted or logged in this form.
    """
    raw, hashed = generate_token(_CODE_PREFIX)
    code = OAuthAuthorizationCode(
        code_hash=hashed,
        client_id=client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        resource=resource,
        scope=scope,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    session.add(code)
    session.flush()
    return raw
