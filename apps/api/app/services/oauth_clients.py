"""RFC 7591 dynamic client registration service (mcp-oauth plan, task 04;
docs/plans/mcp-oauth/DESIGN.md §"End-to-end flow" step 4, §"Security / threat model").

DCR (`POST /api/v1/oauth/register`) is open per the Model Context Protocol — any client can
self-register with no operator approval — so this module also carries the two server-side guards
DESIGN.md's threat model requires for an open registration endpoint: a hard cap on the total
number of registered clients (`prune_stale_clients`, `count_clients` — enforced by the ROUTE, not
here) and pruning of stale, never-used registrations so an unbounded flood of throwaway
registrations doesn't grow `oauth_clients` forever.

CONVENTIONS.md §3: every function here is session-first and only ever `flush()`es — the caller
(the route's `get_session` dependency) owns the transaction boundary and commits.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import urlsplit

from sqlalchemy import delete, exists, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models.api_tokens import ApiToken
from app.models.oauth import OAuthClient, OAuthConsent, OAuthRefreshToken
from app.services.errors import OAuthError

_ALLOWED_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}
"""RFC 8252 §7.3's loopback-redirect carve-out: the only hosts a plain (non-TLS) `http://`
redirect URI may target — a local development client cannot obtain a TLS certificate for these.
`urlsplit(...).hostname` lower-cases and strips the brackets off an IPv6 literal (e.g.
`urlsplit("http://[::1]:8/cb").hostname == "::1"`), so `"::1"`, not `"[::1]"`, is the entry here.
"""

_CLIENT_ID_PREFIX = "adkc_"
_STALE_CLIENT_AGE = timedelta(hours=24)


def validate_redirect_uri(uri: str) -> None:
    """Validate one `redirect_uris` entry (RFC 7591 §3, mcp-oauth Global Constraints "Redirect
    Uris").

    Accepts `https://` at any host, or `http://` ONLY when the host is `localhost`, `127.0.0.1`,
    or `[::1]` (any port, any path) — the standard loopback carve-out (RFC 8252 §7.3) for a local
    development client. Rejects a fragment component unconditionally (RFC 6749 §3.1.2: a
    redirection URI "MUST NOT include a fragment component") and an empty/missing scheme or host.

    Args:
        uri: one candidate redirect URI from the registration request.

    Raises:
        OAuthError: `"invalid_redirect_uri"`, with a field-specific description, if `uri` fails
            any rule above.
    """
    parts = urlsplit(uri)

    if parts.fragment:
        raise OAuthError(
            "invalid_redirect_uri", f"redirect_uris: {uri!r} must not include a fragment."
        )
    if not parts.scheme or not parts.hostname:
        raise OAuthError(
            "invalid_redirect_uri", f"redirect_uris: {uri!r} is not a valid absolute URI."
        )
    if parts.scheme == "https":
        return
    if parts.scheme == "http" and parts.hostname in _ALLOWED_HTTP_HOSTS:
        return
    raise OAuthError(
        "invalid_redirect_uri",
        f"redirect_uris: {uri!r} must be https://, or http:// with host "
        "localhost, 127.0.0.1, or [::1].",
    )


def register_client(session: Session, *, redirect_uris: list[str], client_name: str) -> OAuthClient:
    """Validate and persist one new `OAuthClient` (RFC 7591 §3 dynamic client registration).

    Every `redirect_uris` entry is validated (`validate_redirect_uri`) before any row is
    inserted, so a single bad URI in a multi-URI list fails the whole registration rather than
    partially persisting one. `client_id` is minted directly via `secrets.token_urlsafe` — NOT
    `app.services.token_hashing.generate_token`, which appends `token_urlsafe(32)` and returns a
    hash: RFC 7591's `client_id` is a public identifier, not a secret, so it has no use for a
    hashed/unhashed pair.

    The `oauth_max_clients` cap (mcp-oauth Global Constraints "Rate limiting") is enforced by the
    CALLER (the route, via `count_clients`) before this function is ever invoked — this function
    performs no cap check of its own.

    Args:
        session: the caller's `Session`. Flushed (never committed) so `client.created_at` (a
            server-side default) is populated before the caller reads it.
        redirect_uris: one or more candidate redirect URIs — every entry must pass
            `validate_redirect_uri`.
        client_name: the client's human-readable display name (the route defaults this to
            `"Unnamed client"` when absent/blank before calling here).

    Returns:
        The newly persisted `OAuthClient`, with `created_at` populated.

    Raises:
        OAuthError: any `redirect_uris` entry fails `validate_redirect_uri`.
    """
    for uri in redirect_uris:
        validate_redirect_uri(uri)

    client = OAuthClient(
        client_id=_CLIENT_ID_PREFIX + secrets.token_urlsafe(24),
        client_name=client_name,
        redirect_uris=redirect_uris,
    )
    session.add(client)
    session.flush()
    return client


def count_clients(session: Session) -> int:
    """Return the total number of registered `OAuthClient` rows.

    Used by the route to enforce `Settings.oauth_max_clients` (mcp-oauth Global Constraints
    "Rate limiting": "DCR is open per MCP, so cap client creation") before calling
    `register_client`.
    """
    return session.execute(select(func.count(OAuthClient.client_id))).scalar_one()


def get_client(session: Session, client_id: str) -> OAuthClient | None:
    """Return the `OAuthClient` row for `client_id`, or `None` if it doesn't exist.

    A plain primary-key lookup — `client_id` IS `OAuthClient`'s primary key
    (`app.models.oauth.OAuthClient`'s own docstring), so no separate active/soft-delete filter
    applies here (this table has no `SoftDeleteMixin`).
    """
    return session.get(OAuthClient, client_id)


def prune_stale_clients(session: Session, *, now: datetime) -> int:
    """Delete every `OAuthClient` older than 24h that owns no consent/token/refresh-token row.

    mcp-oauth Global Constraints "Rate limiting": "clients older than 24h with no consent/tokens
    are pruned" — DCR is open per MCP, so this bounds an unbounded flood of throwaway
    registrations that never went on to complete an authorization. A client is "in use" if it
    owns any `oauth_consents`, `api_tokens` (`client_id`), or `oauth_refresh_tokens` row — any one
    of those means a real user actually authorized it at some point, so it must never be pruned
    regardless of age.

    One `DELETE ... WHERE ... NOT EXISTS (...) AND NOT EXISTS (...) AND NOT EXISTS (...)`
    statement (three correlated `NOT EXISTS` subqueries, one per dependent table) rather than a
    SELECT-then-delete-in-Python loop — this stays a single round trip and can never race a
    concurrent request that inserts a dependent row between the check and the delete.
    `synchronize_session=False`: this route never holds a loaded `OAuthClient` instance for a
    stale row in the session's identity map (the stale rows this deletes were never queried into
    this session), so there is nothing to synchronize.

    Called unconditionally by the ROUTE on every `/register` call, before any metadata validation
    (task brief's own route-ordering pin) — services `flush()` but never `commit()`
    (CONVENTIONS.md §3); the caller's session dependency commits.

    Args:
        session: the caller's `Session`.
        now: the reference "current time" — a client is stale when `created_at < now - 24h`.
            Explicit (not `datetime.now(UTC)` read internally) so a caller controls the reference
            point precisely, mirroring every other injectable-clock seam in this codebase
            (CONVENTIONS.md §10).

    Returns:
        The number of `OAuthClient` rows deleted.
    """
    cutoff = now - _STALE_CLIENT_AGE
    stmt = (
        delete(OAuthClient)
        .where(
            OAuthClient.created_at < cutoff,
            ~exists().where(OAuthConsent.client_id == OAuthClient.client_id),
            ~exists().where(ApiToken.client_id == OAuthClient.client_id),
            ~exists().where(OAuthRefreshToken.client_id == OAuthClient.client_id),
        )
        .execution_options(synchronize_session=False)
    )
    # `Session.execute` is statically typed to return the generic `Result[Any]` regardless of
    # statement kind — `cast` to `CursorResult[Any]` (what a `delete()` Core statement actually
    # returns at runtime) so mypy strict sees `.rowcount` as the `int` it really is.
    result = cast("CursorResult[Any]", session.execute(stmt))
    return result.rowcount
