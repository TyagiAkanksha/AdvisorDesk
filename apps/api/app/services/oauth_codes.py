"""Authorization-code issuance and consumption (mcp-oauth plan, task 05 + task 07; RFC 6749
§4.1.2/§4.1.3 + RFC 7636).

Task 05 minted codes; task 07 (`consume_authorization_code`) adds the `/token` code-exchange
grant's redemption side, including replay detection (RFC 6749 §4.1.2: a code MUST be used only
once). CONVENTIONS.md §3: session-first, `flush()` — never `commit()` — the caller (the route's
`get_session` dependency) owns the transaction boundary.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oauth import OAuthAuthorizationCode
from app.services.errors import OAuthError
from app.services.token_hashing import generate_token, hash_token

logger = logging.getLogger(__name__)

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
        session: the caller's `Session`. Flushed (never committed) so the INSERT lands inside the
            caller's transaction before the route returns — the caller's `get_session` dependency
            owns the commit (CONVENTIONS.md §3); mirrors `app.services.oauth_clients.
            register_client`'s identical flush-then-return pattern.
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


def consume_authorization_code(
    session: Session,
    *,
    raw_code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
    resource: str,
    now: datetime,
) -> OAuthAuthorizationCode:
    """Redeem one single-use authorization code (RFC 6749 §4.1.3 token request validation).

    Locks the code row (`SELECT ... FOR UPDATE`) before validating so two concurrent redemption
    attempts for the same code can never both observe `consumed_at IS NULL` and both proceed — the
    second waits for the first's transaction to commit (or roll back) before it can even read the
    row, closing the TOCTOU window a plain `SELECT` would leave open on a code with real financial
    value (it mints an access + refresh token pair). RFC 6749 §4.1.2: "The authorization code MUST
    expire shortly after it is issued ... MUST NOT be used more than once. If [it] is used more
    than once, the authorization server ... SHOULD revoke ... all tokens previously issued based on
    that authorization code" — a replay revokes the whole token family this code minted
    (`app.services.oauth_tokens.revoke_family`), not just the code itself.

    Validation order (task-07 brief's own pinned pseudocode): unknown/never-existed code, then
    replay (already consumed), then expiry, then client match, then redirect_uri exact match
    (RFC 6749 §4.1.3), then PKCE (RFC 7636 §4.6), then resource/audience (RFC 8707). PKCE is gated
    by `is_valid_code_verifier` BEFORE `verify_s256` is ever called — `verify_s256` calls
    `.encode("ascii")` internally and raises `UnicodeEncodeError` on a non-ASCII verifier; a
    malformed verifier fails the regex first, so `verify_s256` is never reached with input it can't
    handle.

    Only a SUCCESSFUL exchange consumes the code (`consumed_at` is set only on the final line,
    after every check above has passed) — a failed PKCE check, wrong redirect_uri, etc. leaves the
    code intact so the legitimate client can retry within its 60s TTL (task-07 brief's own pinned
    decision: the short TTL plus the token endpoint's rate limit bound retries, and the PKCE
    verifier space is not brute-forceable in that window).

    Args:
        session: the caller's `Session`. Flushed (never committed) — the caller's `get_session`
            dependency owns the commit (CONVENTIONS.md §3).
        raw_code: the code as presented at `/token` (`"adkac_..."`).
        client_id: the `client_id` presented at `/token` — must match the code's own.
        redirect_uri: the `redirect_uri` presented at `/token` — must exactly match the one the
            code was issued for (RFC 6749 §4.1.3).
        code_verifier: the RFC 7636 PKCE verifier presented at `/token`.
        resource: the RFC 8707 resource indicator presented at `/token`.
        now: the reference "current time" (CONVENTIONS.md §10's injectable-clock seam).

    Returns:
        The now-consumed `OAuthAuthorizationCode` row (`consumed_at` freshly set to `now`).

    Raises:
        OAuthError: `"invalid_grant"` for an unknown/expired/already-used/wrong-client/
            wrong-redirect/failed-PKCE code, or `"invalid_target"` for a resource mismatch.
    """
    # Local import: `app.services.oauth_tokens.revoke_family` depends on this module's
    # `OAuthAuthorizationCode` row shape only indirectly (via `family_id`) — the real reason this
    # is a function-body import is to break the codes<->tokens module cycle (task-07 brief:
    # "codes -> tokens is a one-way import; tokens must NOT import codes at module level").
    from app.services.oauth_tokens import revoke_family
    from app.services.pkce import is_valid_code_verifier, verify_s256

    row = session.execute(
        select(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.code_hash == hash_token(raw_code))
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise OAuthError("invalid_grant", "Unknown or expired authorization code.")

    if row.consumed_at is not None:
        revoke_family(session, row.id, now)
        logger.warning("oauth code replay detected client_id=%s reason=code-replay", client_id)
        raise OAuthError("invalid_grant", "Authorization code already used.")

    if row.expires_at <= now:
        raise OAuthError("invalid_grant", "Unknown or expired authorization code.")

    if row.client_id != client_id:
        raise OAuthError("invalid_grant", "Unknown or expired authorization code.")

    if row.redirect_uri != redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri does not match the authorization request.")

    if not is_valid_code_verifier(code_verifier) or not verify_s256(
        code_verifier, row.code_challenge
    ):
        raise OAuthError("invalid_grant", "PKCE verification failed.")

    if row.resource != resource:
        raise OAuthError("invalid_target", "resource does not match the authorization request.")

    row.consumed_at = now
    session.flush()
    return row
