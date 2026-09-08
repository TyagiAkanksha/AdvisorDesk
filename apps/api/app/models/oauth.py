"""OAuth 2.1 authorization-server ORM models (mcp-oauth plan, task-01;
docs/plans/mcp-oauth/DESIGN.md §"Token & data model").

Four new tables, co-hosted alongside the existing `/api/v1/mcp` endpoint (PRD §3): a registered
`OAuthClient` (RFC 7591 dynamic client registration — the `client_id` IS the primary key, there is
no separate surrogate id), a one-time `OAuthAuthorizationCode` (RFC 7636 PKCE authorization-code
flow), a rotatable `OAuthRefreshToken` (RFC 6749 §6 refresh-token grant, with rotation-family
tracking via `family_id`/`rotated_from_id` — docs/plans/mcp-oauth/DESIGN.md §"Security / threat
model"), and a per-user `OAuthConsent` record (one row per `(user, client)` pair, PRD's own
"remember this client's access" consent-screen behavior).

Only the data model lands here — nothing in this module issues, verifies, or rotates a
code/token; every later mcp-oauth task builds its issuance/verification logic on top of these
tables and `app.services.token_hashing`. Every secret column (`code_hash`, `token_hash`) stores
ONLY a `app.services.token_hashing.hash_token` digest — the raw value is never persisted.

FK `ondelete` choices (docs/plans/mcp-oauth/DESIGN.md §"Decisions pinned at plan time"): deleting
an `OAuthClient` cascades to every dependent row minted for it (`oauth_authorization_codes`,
`oauth_refresh_tokens`, `oauth_consents`, and `api_tokens.client_id` — see `app/models/
api_tokens.py`) since none of them mean anything once the client itself is gone. A refresh token's
own optional back-references (`access_token_id` to the `api_tokens` row it minted,
`rotated_from_id` to the refresh token it rotated from) are `SET NULL` instead — the refresh token
row itself stays a historical/audit record even after the thing it points to is gone.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class OAuthClient(Base, TimestampMixin):
    """A registered OAuth client (RFC 7591 dynamic client registration).

    `client_id` is the RFC 7591 identifier itself — no separate surrogate `id` column, since the
    client id IS the natural key every other OAuth table (and `api_tokens.client_id`) references.
    """

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(Text, primary_key=True)
    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False)


class OAuthAuthorizationCode(Base, TimestampMixin):
    """A one-time PKCE authorization code (RFC 6749 §4.1 + RFC 7636), pending exchange.

    `code_hash` is the ONLY thing ever stored — the raw code exists only transiently in the
    redirect URL. `resource` pins the RFC 8707 resource indicator the code was issued for (the
    same value the eventual access token is minted for); `consumed_at` (set once the code is
    exchanged) makes replay of an already-used code detectable rather than merely "not found".
    """

    __tablename__ = "oauth_authorization_codes"

    id: Mapped[uuid.UUID] = uuid_pk()
    code_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    client_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthRefreshToken(Base, TimestampMixin):
    """A rotatable refresh token (RFC 6749 §6), one rotation family per original grant.

    `family_id` is the originating authorization code's `id` — every refresh token minted from
    that code, directly or through a chain of rotations, shares the same `family_id`, so a later
    task can detect refresh-token reuse (a stolen, already-rotated token replayed) by revoking the
    whole family rather than just the one row. `rotated_from_id` is the immediate predecessor in
    that chain (`NULL` for the first token in a family); `access_token_id` optionally points at the
    `api_tokens` row this refresh most recently minted. Both are `SET NULL` on delete of their
    target (docs/plans/mcp-oauth/DESIGN.md §"Decisions pinned at plan time") — this row is a
    historical record, not merely a live pointer.
    """

    __tablename__ = "oauth_refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    client_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    access_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    rotated_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthConsent(Base, TimestampMixin):
    """One row per `(user, client)` pair — records that a user has already granted a client
    access, so the authorize flow can skip re-prompting for consent on a later authorization.

    `revoked_at` lets a later "revoke this app's access" action retract consent without deleting
    the audit row (mirrors `OAuthRefreshToken.revoked_at`'s own soft-revocation shape).
    """

    __tablename__ = "oauth_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_oauth_consents_user_id_client_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(
        Text, ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
