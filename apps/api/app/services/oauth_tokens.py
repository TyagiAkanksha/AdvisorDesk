"""Token issuance, refresh rotation, and reuse detection (mcp-oauth plan, task 07; RFC 6749
§4.1.4 (code grant token response), §6 (refreshing an access token)).

This module is the ONE place an `ApiToken`/`OAuthRefreshToken` pair is minted for the OAuth
authorization-server flow — `issue_token_pair` is shared by both the initial code-exchange grant
(`redeem_authorization_code`) and every subsequent refresh (`rotate_refresh_token`), so the two
paths can never drift in how they build the access-token row `app.auth.tokens.resolve_bearer_token`
must accept (session_epoch copied from the owner at issue time, resource/client_id stamped for the
audience check).

Rotation-family reuse detection (docs/plans/mcp-oauth/DESIGN.md §"Security / threat model"): every
refresh token minted from one authorization code — directly, or through any chain of rotations —
shares that code's id as `family_id`. Presenting an already-rotated-away (`revoked_at IS NOT
NULL`) refresh token is treated as evidence of theft (RFC 6749 §10.4) and kills every token in the
family via `revoke_family`, not just the one presented. `consume_authorization_code`
(`app.services.oauth_codes`) reuses the same `revoke_family` for a replayed authorization code,
since a replayed code implies the same "something is wrong with every token this grant issued"
conclusion.

CONVENTIONS.md §3: every function here is session-first and only ever `flush()`s — the caller (the
route's `get_session` dependency) owns the transaction boundary and commits.

Import-linter contract ("app.services imports only app.models and app.config"): this module may
import other `app.services` modules (e.g. `app.services.token_hashing`, `app.services.users`) —
only `app.routes`/`app.mcp`/`app.rag`/`app.agent`/`app.auth`/`app.main`/`app.db`/`app.factory` are
forbidden. `consume_authorization_code` (`app.services.oauth_codes`) is imported inside
`redeem_authorization_code`'s function body, not at module scope, specifically to break the
codes<->tokens cycle: this module's own `revoke_family` is imported (also function-body-local) by
`oauth_codes.consume_authorization_code` for the replay case, so a module-level import in either
direction would deadlock Python's import machinery.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.api_tokens import ApiToken
from app.models.oauth import OAuthRefreshToken
from app.services.errors import OAuthError
from app.services.token_hashing import generate_token, hash_token
from app.services.users import get_user_by_id

logger = logging.getLogger(__name__)

_ACCESS_TOKEN_PREFIX = "adk_"
_REFRESH_TOKEN_PREFIX = "adkr_"


@dataclass(frozen=True)
class IssuedTokens:
    """One freshly-minted access+refresh token pair, ready to render as `TokenResponse`.

    Attributes:
        access_token: the raw `"adk_..."` bearer token — hand it back exactly once.
        refresh_token: the raw `"adkr_..."` refresh token — hand it back exactly once.
        expires_in: seconds until `access_token` expires (RFC 6749 §4.1.4/§5.1).
        scope: the granted scope, always `"mcp"` today.
    """

    access_token: str
    refresh_token: str
    expires_in: int
    scope: str


def issue_token_pair(
    session: Session,
    *,
    client_id: str,
    user_id: uuid.UUID,
    resource: str,
    scope: str,
    family_id: uuid.UUID,
    refresh_expires_at: datetime,
    now: datetime,
    settings: Settings,
    rotated_from_id: uuid.UUID | None = None,
) -> IssuedTokens:
    """Mint one fresh `ApiToken` (`adk_`) + `OAuthRefreshToken` (`adkr_`) pair.

    The `ApiToken` row is built to satisfy every check `app.auth.tokens.resolve_bearer_token`
    performs: `session_epoch` is copied from the owner's CURRENT `User.session_epoch` at issue
    time (so a later `/auth/logout` epoch bump revokes this token too, exactly like every other
    bearer token), `client_id`/`resource` are stamped so the audience rule applies, and
    `expires_at` is `now + oauth_access_token_ttl_minutes`.

    Args:
        session: the caller's `Session`. Flushed (never committed) — CONVENTIONS.md §3.
        client_id: the registered `OAuthClient.client_id` this pair is minted for.
        user_id: the owning `User.id` — the code's or the old refresh token's `user_id`.
        resource: the RFC 8707 resource indicator both tokens are scoped to.
        scope: the granted scope (always `"mcp"` today), echoed onto the refresh row and the
            eventual `TokenResponse`.
        family_id: the rotation family this refresh token belongs to — the originating
            authorization code's id, unchanged across every rotation in the chain.
        refresh_expires_at: the new refresh token's absolute expiry — a fresh
            `now + oauth_refresh_token_ttl_days` window for the code grant, or the OLD refresh
            token's own (already-computed) `expires_at` when rotating, so rotation inherits the
            remaining window rather than resetting it.
        now: the reference "current time" (CONVENTIONS.md §10's injectable-clock seam).
        settings: supplies `oauth_access_token_ttl_minutes`.
        rotated_from_id: the immediate predecessor `OAuthRefreshToken.id` this row rotates from,
            or `None` for the first token in a family (the code-grant path).

    Returns:
        The raw token pair plus `expires_in`/`scope`, ready for `TokenResponse`.

    Raises:
        OAuthError: `"invalid_grant"` — `user_id` no longer resolves to any `User` row at all
            (soft-deleted or hard-deleted since the code/refresh token was minted).
    """
    user = get_user_by_id(session, user_id)
    if user is None:
        raise OAuthError("invalid_grant", "User no longer exists.")

    access_raw, access_hash = generate_token(_ACCESS_TOKEN_PREFIX)
    access = ApiToken(
        user_id=user_id,
        token_hash=access_hash,
        name=f"oauth:{client_id}",
        session_epoch=user.session_epoch,
        expires_at=now + timedelta(minutes=settings.oauth_access_token_ttl_minutes),
        client_id=client_id,
        resource=resource,
    )
    session.add(access)
    session.flush()

    refresh_raw, refresh_hash = generate_token(_REFRESH_TOKEN_PREFIX)
    refresh = OAuthRefreshToken(
        token_hash=refresh_hash,
        client_id=client_id,
        user_id=user_id,
        access_token_id=access.id,
        family_id=family_id,
        rotated_from_id=rotated_from_id,
        resource=resource,
        scope=scope,
        expires_at=refresh_expires_at,
    )
    session.add(refresh)
    session.flush()

    return IssuedTokens(
        access_token=access_raw,
        refresh_token=refresh_raw,
        expires_in=settings.oauth_access_token_ttl_minutes * 60,
        scope=scope,
    )


def redeem_authorization_code(
    session: Session,
    *,
    raw_code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
    resource: str,
    now: datetime,
    settings: Settings,
) -> IssuedTokens:
    """Exchange a validated authorization code for a fresh token pair (RFC 6749 §4.1.3/§4.1.4).

    The new refresh token starts its own rotation family: `family_id == code.id` (the
    originating code's id), `rotated_from_id is None` (nothing precedes the first token in a
    family), and a fresh `now + oauth_refresh_token_ttl_days` expiry window.

    Args:
        session: the caller's `Session`.
        raw_code, client_id, redirect_uri, code_verifier, resource, now: forwarded verbatim to
            `app.services.oauth_codes.consume_authorization_code` — see that function's docstring
            for the full validation order.
        settings: supplies `oauth_refresh_token_ttl_days` (this function) and
            `oauth_access_token_ttl_minutes` (`issue_token_pair`).

    Returns:
        The freshly-minted `IssuedTokens`.

    Raises:
        OAuthError: whatever `consume_authorization_code` or `issue_token_pair` raises.
    """
    # Local import — see this module's own docstring: breaks the codes<->tokens module cycle
    # (`oauth_codes.consume_authorization_code` itself function-body-imports `revoke_family` from
    # here for the replay case).
    from app.services.oauth_codes import consume_authorization_code

    code = consume_authorization_code(
        session,
        raw_code=raw_code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        resource=resource,
        now=now,
    )
    return issue_token_pair(
        session,
        client_id=client_id,
        user_id=code.user_id,
        resource=code.resource,
        scope=code.scope,
        family_id=code.id,
        refresh_expires_at=now + timedelta(days=settings.oauth_refresh_token_ttl_days),
        now=now,
        settings=settings,
    )


def rotate_refresh_token(
    session: Session,
    *,
    raw_refresh_token: str,
    client_id: str,
    resource: str | None,
    scope: str | None,
    now: datetime,
    settings: Settings,
) -> IssuedTokens:
    """Rotate one refresh token: revoke it, mint a fresh pair, detect reuse (RFC 6749 §6/§10.4).

    Locks the refresh-token row (`SELECT ... FOR UPDATE`) before validating, the same
    concurrent-redemption guard `consume_authorization_code` applies to codes. The new refresh
    token INHERITS the old one's absolute `expires_at` (the "remaining window", not a fresh full
    TTL) — a client cannot extend its session indefinitely by refreshing early. The old row's
    `ApiToken` (if any) is hard-deleted, not merely left to expire, so a token compromised alongside
    its refresh token stops working immediately rather than at its own TTL.

    Reuse detection (RFC 6749 §10.4): a refresh token whose `revoked_at` is already set (i.e. it
    was already rotated away by an earlier, legitimate use) being presented AGAIN means either the
    legitimate client replayed a stale value, or an attacker who stole an old token is using it —
    either way, `revoke_family` kills every token descended from the same original grant.

    Args:
        session: the caller's `Session`.
        raw_refresh_token: the refresh token as presented at `/token`.
        client_id: the `client_id` presented at `/token` — must match the token's own.
        resource: the `resource` presented at `/token`, or `None`/empty to keep the original
            grant's resource unchanged.
        scope: the `scope` presented at `/token`, or `None`/empty to keep the original grant's
            scope unchanged — a non-empty value that differs from the original is scope
            escalation and is rejected (RFC 6749 §6: "shall NOT include ... broader scope").
        now: the reference "current time".
        settings: supplies `oauth_refresh_token_ttl_days` indirectly (inherited, not recomputed —
            see above) and `oauth_access_token_ttl_minutes` (`issue_token_pair`).

    Returns:
        The freshly-minted `IssuedTokens`.

    Raises:
        OAuthError: `"invalid_grant"` (unknown/expired/revoked/wrong-client token) or
            `"invalid_target"`/`"invalid_scope"` (resource/scope mismatch).
    """
    old = session.execute(
        select(OAuthRefreshToken)
        .where(OAuthRefreshToken.token_hash == hash_token(raw_refresh_token))
        .with_for_update()
    ).scalar_one_or_none()
    if old is None:
        raise OAuthError("invalid_grant", "Unknown or expired refresh token.")

    if old.revoked_at is not None:
        revoke_family(session, old.family_id, now)
        logger.warning("refresh token reuse detected client_id=%s reason=refresh-reuse", client_id)
        raise OAuthError("invalid_grant", "Refresh token has been revoked.")

    if old.expires_at <= now:
        raise OAuthError("invalid_grant", "Unknown or expired refresh token.")

    if old.client_id != client_id:
        raise OAuthError("invalid_grant", "Unknown or expired refresh token.")

    if resource not in (None, "", old.resource):
        raise OAuthError("invalid_target", "resource does not match the original grant.")

    if scope not in (None, "", old.scope):
        raise OAuthError("invalid_scope", "Requested scope exceeds the original grant.")

    old.revoked_at = now
    if old.access_token_id is not None:
        session.execute(delete(ApiToken).where(ApiToken.id == old.access_token_id))
    session.flush()

    return issue_token_pair(
        session,
        client_id=client_id,
        user_id=old.user_id,
        resource=old.resource,
        scope=old.scope,
        family_id=old.family_id,
        refresh_expires_at=old.expires_at,
        now=now,
        settings=settings,
        rotated_from_id=old.id,
    )


def revoke_family(session: Session, family_id: uuid.UUID, now: datetime) -> int:
    """Revoke every still-live `OAuthRefreshToken` in `family_id`, deleting each one's access
    token row too.

    Shared by `oauth_codes.consume_authorization_code` (a replayed authorization code kills every
    token it ever minted) and `rotate_refresh_token` (a reused, already-rotated refresh token kills
    the whole rotation chain) — the single place "kill this entire family" is implemented, so a
    later task's `/revoke` endpoint can reuse it too.

    Args:
        session: the caller's `Session`. Flushed (never committed) — CONVENTIONS.md §3.
        family_id: the rotation family to kill — every `OAuthRefreshToken.family_id == family_id`
            row still `revoked_at IS NULL`.
        now: the timestamp stamped onto every row's `revoked_at`.

    Returns:
        The number of `OAuthRefreshToken` rows revoked by this call (0 if the family was already
        fully revoked, or never existed).
    """
    rows = (
        session.execute(
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.family_id == family_id,
                OAuthRefreshToken.revoked_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.revoked_at = now
        if row.access_token_id is not None:
            session.execute(delete(ApiToken).where(ApiToken.id == row.access_token_id))
    session.flush()
    return len(rows)
