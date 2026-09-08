"""RFC 7591 dynamic client registration service (mcp-oauth plan, task 04;
docs/plans/mcp-oauth/DESIGN.md §"End-to-end flow" step 4, §"Security / threat model").

DCR (`POST /api/v1/oauth/register`) is open per the Model Context Protocol — any client can
self-register with no operator approval — so this module also carries the server-side guards
DESIGN.md's threat model requires for an open registration endpoint: a hard cap on the total
number of registered clients (`prune_stale_clients`, `count_clients` — enforced by the ROUTE, not
here), pruning of stale, never-used registrations so an unbounded flood of throwaway
registrations doesn't grow `oauth_clients` forever, and (fix round 1, review finding M-2) a hard
cap on both the number and length of `redirect_uris` entries a single registration may persist
(`MAX_REDIRECT_URIS`, `MAX_REDIRECT_URI_LENGTH` below) — the same "an open, unauthenticated
endpoint's every unbounded input is a DoS vector" rationale, applied to persisted row *size*
rather than row *count*.

Fix round 1 (review findings I-1, I-2, I-3, M-1): `validate_redirect_uri` also closes three gaps
a redirect-URI-bypass probe found in the original implementation — an uncaught `ValueError` from
`urlsplit` on malformed input (I-1, -> unauthenticated 500 instead of 400), a Python/WHATWG
parser differential reachable via a backslash or userinfo component in the authority (I-2/M-1),
and an empty fragment (`"...#"`) evading the original truthiness-based fragment check (I-3). See
`validate_redirect_uri`'s own docstring for the mechanism of each.

CONVENTIONS.md §3: every function here is session-first and only ever `flush()`es — the caller
(the route's `get_session` dependency) owns the transaction boundary and commits.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import urlsplit

from sqlalchemy import case, delete, exists, func, or_, select
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

MAX_REDIRECT_URIS = 10
"""Fix round 1 (review finding M-2): a hard cap on `len(redirect_uris)` per registration.
DESIGN.md §"Security / threat model": DCR is an OPEN, unauthenticated endpoint, so every
unbounded input it accepts is a persisted-size DoS vector — `oauth_max_clients` already bounds
row *count*; this bounds row *size* the same way. Enforced by `register_client`, not here.
"""

MAX_REDIRECT_URI_LENGTH = 2000
"""Fix round 1 (review finding M-2): a hard cap on one `redirect_uris` entry's length — same
DESIGN.md §"Security / threat model" rationale as `MAX_REDIRECT_URIS` above, applied per-URI
instead of to the list as a whole. Enforced by `validate_redirect_uri` below.
"""


def validate_redirect_uri(uri: str) -> None:
    """Validate one `redirect_uris` entry (RFC 7591 §3, mcp-oauth Global Constraints "Redirect
    Uris").

    Accepts `https://` at any host, or `http://` ONLY when the host is `localhost`, `127.0.0.1`,
    or `[::1]` (any port, any path) — the standard loopback carve-out (RFC 8252 §7.3) for a local
    development client. Rejects a fragment component unconditionally (RFC 6749 §3.1.2: a
    redirection URI "MUST NOT include a fragment component"), a backslash or userinfo component
    (fix round 1, findings I-2/M-1 — see below), an empty/missing scheme or host, and anything
    over `MAX_REDIRECT_URI_LENGTH` characters (fix round 1, finding M-2).

    Fix round 1 (review findings I-1/I-2/I-3, an open unauthenticated endpoint's input validator):

    - **I-1**: `urlsplit` can raise `ValueError` on a bracket-mismatched authority (e.g.
      `"http://[::1"`) — previously uncaught, so it fell through the route's no-`try/except` rule
      straight into the generic 500 handler instead of a 400. Caught here and re-raised as the
      same `OAuthError` every other rejection in this function raises.
    - **I-2/M-1**: `parts.hostname` is resolved *after* userinfo — Python's `urlsplit` does not
      treat a literal backslash as an authority terminator, but WHATWG (every browser) does for
      special schemes, so `"http://evil.example\\@localhost/cb"` parses as host `localhost` in
      Python while a browser resolves it to `evil.example`. Rejecting any backslash, or any `@` in
      the netloc (which also closes the plain-userinfo case, M-1, e.g.
      `"http://user:pass@localhost/cb"`), closes that parser differential before the host check
      ever runs.
    - **I-3**: `if parts.fragment:` is a truthiness test, and `urlsplit("https://a.example/cb#")
      .fragment == ""` — a bare trailing `#` is indistinguishable from "no fragment" to that check,
      so RFC 6749 §3.1.2's "MUST NOT include a fragment component" was silently violated for any
      URI ending in a lone `#`. Testing the raw string for `"#"` (rather than the parsed
      `.fragment`) catches an empty fragment too.

    Args:
        uri: one candidate redirect URI from the registration request.

    Raises:
        OAuthError: `"invalid_redirect_uri"`, with a field-specific description, if `uri` fails
            any rule above.
    """
    if len(uri) > MAX_REDIRECT_URI_LENGTH:
        raise OAuthError(
            "invalid_redirect_uri",
            f"redirect_uris: {uri!r} is longer than {MAX_REDIRECT_URI_LENGTH} characters.",
        )

    try:
        parts = urlsplit(uri)
    except ValueError as exc:
        raise OAuthError(
            "invalid_redirect_uri", f"redirect_uris: {uri!r} is not a valid absolute URI."
        ) from exc

    if "#" in uri:
        raise OAuthError(
            "invalid_redirect_uri", f"redirect_uris: {uri!r} must not include a fragment."
        )
    if "\\" in uri or "@" in parts.netloc:
        raise OAuthError(
            "invalid_redirect_uri",
            f"redirect_uris: {uri!r} must not contain a backslash or userinfo component.",
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

    Fix round 1 (review finding M-2): rejects `len(redirect_uris) > MAX_REDIRECT_URIS` up front,
    before validating any individual URI — DESIGN.md §"Security / threat model": DCR is an open,
    unauthenticated endpoint, so an unbounded `redirect_uris` list is a persisted-size DoS vector
    (`oauth_clients.redirect_uris` is an unbounded `ARRAY(Text)`) just like an unbounded per-URI
    length is (`validate_redirect_uri`'s own `MAX_REDIRECT_URI_LENGTH` check).

    Args:
        session: the caller's `Session`. Flushed (never committed) so `client.created_at` (a
            server-side default) is populated before the caller reads it.
        redirect_uris: one or more candidate redirect URIs, at most `MAX_REDIRECT_URIS` of them —
            every entry must also pass `validate_redirect_uri`.
        client_name: the client's human-readable display name (the route defaults this to
            `"Unnamed client"` when absent/blank before calling here).

    Returns:
        The newly persisted `OAuthClient`, with `created_at` populated.

    Raises:
        OAuthError: `len(redirect_uris) > MAX_REDIRECT_URIS`, or any entry fails
            `validate_redirect_uri`.
    """
    if len(redirect_uris) > MAX_REDIRECT_URIS:
        raise OAuthError(
            "invalid_redirect_uri",
            f"redirect_uris: at most {MAX_REDIRECT_URIS} entries are allowed.",
        )
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


@dataclass(frozen=True)
class ConnectedAppRow:
    """One `OAuthClient`'s row on the admin "Connected apps" page (mcp-oauth plan, task 08;
    docs/plans/mcp-oauth/task-08-revoke-admin-api.md; the frozen counterpart of
    `app.models.schemas.oauth.ConnectedApp`, which maps directly from this via
    `ConfigDict(from_attributes=True)`).

    Every field here is computed by `list_connected_apps` below, never queried piecemeal per
    client — see that function's own docstring for the exact query shape.

    Attributes:
        client_id: the `OAuthClient.client_id` this row summarizes.
        client_name: the client's registered display name.
        redirect_uris: the client's registered redirect URIs.
        created_at: when the client was registered.
        consent_granted_at: `OAuthConsent.created_at` of the client's currently-active
            (`revoked_at IS NULL`) consent row, or `None` if no user has ever granted it consent.
            Controller ruling (task-08 dispatch; the brief's own comment here cites a nonexistent
            `OAuthConsent.updated_at` column — that column does not exist): this is the FIRST
            grant's timestamp — a later re-grant after a revoke does not move it, since
            `record_consent` revives the same row rather than inserting a new one
            (`app.services.oauth_consents.record_consent`), and that row's `created_at` is never
            updated.
        active_access_tokens: live `ApiToken` rows for this client — `expires_at IS NULL OR
            expires_at > now` (task-07 review M-6 carry-over: refresh rotation hard-deletes the
            old `ApiToken` row, so this is a true LIVE count, never a historical one).
        active_refresh_tokens: live `OAuthRefreshToken` rows for this client — `revoked_at IS NULL
            AND expires_at > now`.
        last_used_at: `max(ApiToken.last_used_at)` over every `ApiToken` row this client has ever
            owned (not filtered to only-active rows) — `None` if the client owns no `ApiToken` row,
            or none of them has ever been used.
        latest_expires_at: `max(OAuthRefreshToken.expires_at)` over this client's ACTIVE refresh
            rows only (the same `revoked_at IS NULL AND expires_at > now` predicate as
            `active_refresh_tokens`) — `None` once no refresh row is active, even if a revoked or
            expired one still exists.
    """

    client_id: str
    client_name: str
    redirect_uris: list[str]
    created_at: datetime
    consent_granted_at: datetime | None
    active_access_tokens: int
    active_refresh_tokens: int
    last_used_at: datetime | None
    latest_expires_at: datetime | None


def list_connected_apps(session: Session, *, now: datetime) -> list[ConnectedAppRow]:
    """Return every registered `OAuthClient`, newest-first, with its live-token summary.

    docs/plans/mcp-oauth/task-08-revoke-admin-api.md; task brief acceptance criterion ("the list
    query is not N+1"): this is exactly ONE SQL statement — three grouped aggregate subqueries
    (one over `api_tokens`, one over `oauth_refresh_tokens`, one over `oauth_consents`, each
    `GROUP BY client_id`), LEFT OUTER JOINed onto `oauth_clients` and ordered once. There is no
    per-client query in a loop, so this function's cost is O(1) round trips regardless of how many
    clients or tokens exist.

    - The `api_tokens` aggregate computes `active_access_tokens` (a conditional `COUNT`: only rows
      with `expires_at IS NULL OR expires_at > now` count) and `last_used_at` (an unconditional
      `MAX` over every row for that client) in the SAME grouped subquery — one pass over the
      table, two aggregates.
    - The `oauth_refresh_tokens` aggregate computes `active_refresh_tokens` and
      `latest_expires_at` the same way: both conditioned on `revoked_at IS NULL AND expires_at >
      now`, `latest_expires_at`'s `MAX` returning NULL for a client with no currently-active row
      (a `CASE` inside `MAX`, not a `WHERE`, since a client with zero active rows must still
      appear via the outer join — a `WHERE` would filter the whole group out of this subquery
      instead of just zeroing its aggregates).
    - The `oauth_consents` aggregate is `MAX(created_at)` filtered to `revoked_at IS NULL` (there
      is at most one active row per `(user, client)` — the table's own unique constraint — but
      several distinct users may each hold an active consent for the same client, so this is the
      most recent still-active grant across all users).

    A client with zero tokens/consents ever (a fresh `/register` with no authorization) still
    appears, via the LEFT OUTER JOIN: every aggregate subquery's columns come back NULL for it,
    turned into `0` for the two counts (`coalesce`) and left `None` for the two timestamps (no
    coalesce needed — `None` already IS this field's "never happened" value).

    Args:
        session: the caller's `Session`. Read-only — never flushes or commits.
        now: the reference "current time" for both "active" predicates (CONVENTIONS.md §10's
            injectable-clock seam).

    Returns:
        One `ConnectedAppRow` per `oauth_clients` row, ordered by `created_at` DESC (newest
        registration first).
    """
    access_active = or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now)
    access_stats = (
        select(
            ApiToken.client_id.label("client_id"),
            func.count(case((access_active, 1))).label("active_access_tokens"),
            func.max(ApiToken.last_used_at).label("last_used_at"),
        )
        .group_by(ApiToken.client_id)
        .subquery()
    )

    refresh_active = (OAuthRefreshToken.revoked_at.is_(None)) & (OAuthRefreshToken.expires_at > now)
    refresh_stats = (
        select(
            OAuthRefreshToken.client_id.label("client_id"),
            func.count(case((refresh_active, 1))).label("active_refresh_tokens"),
            func.max(case((refresh_active, OAuthRefreshToken.expires_at))).label(
                "latest_expires_at"
            ),
        )
        .group_by(OAuthRefreshToken.client_id)
        .subquery()
    )

    consent_stats = (
        select(
            OAuthConsent.client_id.label("client_id"),
            func.max(OAuthConsent.created_at).label("consent_granted_at"),
        )
        .where(OAuthConsent.revoked_at.is_(None))
        .group_by(OAuthConsent.client_id)
        .subquery()
    )

    stmt = (
        select(
            OAuthClient.client_id,
            OAuthClient.client_name,
            OAuthClient.redirect_uris,
            OAuthClient.created_at,
            consent_stats.c.consent_granted_at,
            func.coalesce(access_stats.c.active_access_tokens, 0).label("active_access_tokens"),
            func.coalesce(refresh_stats.c.active_refresh_tokens, 0).label("active_refresh_tokens"),
            access_stats.c.last_used_at,
            refresh_stats.c.latest_expires_at,
        )
        .select_from(OAuthClient)
        .outerjoin(access_stats, access_stats.c.client_id == OAuthClient.client_id)
        .outerjoin(refresh_stats, refresh_stats.c.client_id == OAuthClient.client_id)
        .outerjoin(consent_stats, consent_stats.c.client_id == OAuthClient.client_id)
        .order_by(OAuthClient.created_at.desc())
    )

    rows = session.execute(stmt).all()
    return [
        ConnectedAppRow(
            client_id=row.client_id,
            client_name=row.client_name,
            redirect_uris=list(row.redirect_uris),
            created_at=row.created_at,
            consent_granted_at=row.consent_granted_at,
            active_access_tokens=row.active_access_tokens,
            active_refresh_tokens=row.active_refresh_tokens,
            last_used_at=row.last_used_at,
            latest_expires_at=row.latest_expires_at,
        )
        for row in rows
    ]


def delete_client(session: Session, client_id: str) -> bool:
    """Delete one `OAuthClient` outright — the admin "Disconnect" action (mcp-oauth plan, task 08).

    `session.delete(client)` on a LOADED row (from `get_client`, never `session.expunge`d) issues
    a real DB-level `DELETE`, which every dependent table's `ondelete="CASCADE"` FK
    (`oauth_authorization_codes.client_id`, `oauth_refresh_tokens.client_id`,
    `oauth_consents.client_id`, `api_tokens.client_id` — `app.models.oauth`'s own module
    docstring) removes along with it in the same statement, at the database level — not an ORM
    relationship cascade (none is configured on `OAuthClient`), so this works regardless of
    whether any dependent row happens to be loaded into this `session`.

    Args:
        session: the caller's `Session`. Flushed (never committed) — CONVENTIONS.md §3.
        client_id: the `OAuthClient.client_id` to delete.

    Returns:
        `True` if a client was found and deleted; `False` if `client_id` names no registered
        client (the caller — the admin route — raises `NotFoundError` in that case).
    """
    client = get_client(session, client_id)
    if client is None:
        return False
    session.delete(client)
    session.flush()
    return True
