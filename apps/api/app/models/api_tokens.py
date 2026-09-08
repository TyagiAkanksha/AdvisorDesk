"""`ApiToken` ORM model — bearer tokens for the MCP endpoint (PRD §3, §9; phase-6 task-04).

A deployed Claude connector can send an `Authorization: Bearer <token>` header but never the
admin session cookie — `scripts/mint_mcp_token.py` mints rows here, `app.auth.tokens.
resolve_bearer_token` resolves them back to the same `AdminPrincipal` shape `require_admin`
produces from a cookie (`app.mcp.server._AdminGatedMcpApp.__call__` gates on either).

Task-04 brief, design ruling: composes ONLY `TimestampMixin`, like the append-only tables
(`content_tags`, `chunks`, `chat_sessions`, `chat_messages`) — PRD §4.1 scopes `SoftDeleteMixin`
to `users`/`content`/`tags` specifically, and revocation here is an honest hard `DELETE` via
`scripts/mint_mcp_token.py --revoke`, with no restore path (unlike a soft-deleted `User`/
`Content`/`Tag` row, a revoked token is gone for good).

Phase-6 remediation task-03 (WR-02, migration 0005): `session_epoch` is a SECOND revocation path,
independent of the hard-delete one above — a bulk one, keyed off the owning `User` row rather than
this row's own id.

Phase-6 remediation task-09 (WR-02 residual, migration 0006): `expires_at` is a THIRD, purely
per-row, self-expiring path — `NULL` means "no expiry" (permanent semantics; every row that
predates this column stays `NULL` forever, never force-expired). `scripts/mint_mcp_token.py::mint`
stamps every FRESH token with `now() + Settings.mcp_token_ttl_days`;
`app.auth.tokens.resolve_bearer_token` rejects a token whose `expires_at` is not `NULL` and is in
the past.

mcp-oauth plan, task-01 (migration 0007; docs/plans/mcp-oauth/DESIGN.md §"Token & data model"):
`client_id`, `resource`, `last_used_at` are additive, all NULLABLE so every existing
`ApiToken(...)` call site across the codebase keeps constructing rows exactly as before.
`client_id` links a token minted through the new OAuth authorization-code/refresh-token flow
(`app.models.oauth.OAuthClient`) back to the client that obtained it — `NULL` for every token
minted the old way, by `scripts/mint_mcp_token.py` directly, which has no OAuth client at all.
`resource` records the RFC 8707 resource indicator the token is scoped to (now stamped by
`scripts/mint_mcp_token.py::mint` too, via `Settings.mcp_resource_url`, even for the non-OAuth
mint path). `last_used_at` is a last-seen stamp nothing in this task writes yet — a later
mcp-oauth task updates it on successful resolution.

`resource`'s `NULL` meaning, pinned here (mirrors migration 0006's `expires_at` NULL note, PRD
§9): every `api_tokens` row minted before migration 0007 ever ran has `resource IS NULL` —
PERMANENTLY, like `expires_at`'s pre-0006 NULL rows, never backfilled by this migration. A future
task's audience check (task 03) treats a `client_id IS NULL` row (every token minted by
`scripts/mint_mcp_token.py`, OAuth or not) as legacy-compatible when `resource IS NULL OR resource
== settings.mcp_resource_url`; a `client_id IS NOT NULL` row (minted through the OAuth
authorization-code/refresh-token flow) must always have `resource == settings.mcp_resource_url`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class ApiToken(Base, TimestampMixin):
    """A bearer token minted for one `User` (the token's owner/actor for every MCP call it makes).

    `token_hash` is the ONLY thing ever stored — `hashlib.sha256(raw.encode()).hexdigest()` of
    the full `"adk_" + secrets.token_urlsafe(32)` raw token (`app.auth.tokens.mint_token`). The
    raw token itself exists only transiently, in the mint script's one-time stdout output — never
    written to any row, log, or column here.
    """

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Per-token revocation stamp (PRD §9; phase-6 remediation task-03, WR-02, migration 0005):
    # stamped with the owner's CURRENT `users.session_epoch` at mint time
    # (`scripts/mint_mcp_token.py::mint`). `app.auth.tokens.resolve_bearer_token` rejects a token
    # whose `session_epoch` no longer matches the owner's LIVE `session_epoch` — so
    # `/auth/logout`'s epoch bump (`app.services.users.bump_session_epoch`) revokes every
    # outstanding bearer token for that user in the same stroke it already revokes every
    # outstanding session cookie. `default=0` (client-side) exists ONLY for backward compatibility
    # with pre-task-03 call sites that construct `ApiToken(...)` without a `session_epoch` kwarg
    # (several sha256-pinned tests in `tests/test_mcp_bearer_auth.py`/`tests/test_mcp_gate_fixes
    # .py` predate this column and cannot be edited) — it mirrors `User.session_epoch`'s own
    # `default=0` for a freshly-created owner, so those unmodified call sites keep resolving
    # (epoch 0 == a fresh owner's epoch 0), exactly as they did before this task. The real mint
    # path (`scripts/mint_mcp_token.py::mint`) always stamps the value explicitly and never relies
    # on this default.
    session_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Per-token self-expiry (PRD §9; phase-6 remediation task-09, WR-02 residual, migration 0006):
    # `NULL` = "no expiry", permanently — every row that predates this column, and any future row
    # a caller deliberately constructs without this kwarg, keeps working forever, exactly as
    # before. `scripts/mint_mcp_token.py::mint` always stamps a real future value on a fresh mint;
    # `app.auth.tokens.resolve_bearer_token` rejects a token whose `expires_at` is not `NULL` and
    # has passed.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # mcp-oauth plan, task-01 (migration 0007) — see the class docstring's final paragraph.
    client_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
