"""CLI to mint/list/revoke MCP bearer tokens (PRD §3, §9; phase-6 task-04).

`/api/v1/mcp` accepts an `Authorization: Bearer <token>` header (`app.auth.tokens`,
`app.mcp.server._AdminGatedMcpApp.__call__`) for a deployed Claude connector that can't send the
admin session cookie — this script is the ONLY way to create or revoke one; §5's REST surface
stays frozen (no route does this). Reads `DATABASE_URL` from the environment directly (not
`app.config.Settings`, which would also demand every other env var this one-shot CLI never
needs) and builds its own engine/session through `app.db`, mirroring
`scripts/export_mcp_tools.py`/`scripts/export_openapi.py`'s "session/engine setup from env, no
`Settings` object" convention.

`mint`/`revoke` are plain, session-taking functions — `main()`'s thin CLI/session wrapper around
them is the only thing that opens a real session or reads `DATABASE_URL`, so tests can drive the
business logic directly against a throwaway-schema `Session` (`tests/test_mcp_bearer_auth.py`)
without going through argv/env at all.

Phase-6 remediation task-09 (WR-02 residual, migration 0006): `mint()` now stamps every fresh row
with an `expires_at`. The TTL itself lives on `app.config.Settings.mcp_token_ttl_days` (design
pin), not read straight from `os.environ` the way `DATABASE_URL` above is — `mint()` builds one
throwaway `Settings()` ONLY to read that single field when the caller doesn't override it via the
new `ttl_days` keyword; `Settings()` succeeds with zero env vars set (CONVENTIONS.md §5), so this
does not reintroduce the "demands every other env var" problem `DATABASE_URL`'s own env-var read
was written to avoid — it just also picks up `MCP_TOKEN_TTL_DAYS` if the deployment sets it,
exactly like every other `Settings` field.

Usage:
    uv run python scripts/mint_mcp_token.py --mint --email admin@example.com --name "ci-connector"
    uv run python scripts/mint_mcp_token.py --list
    uv run python scripts/mint_mcp_token.py --revoke <token-id>
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.tokens import mint_token
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.models.api_tokens import ApiToken
from app.models.users import User
from app.services.queries import active_select


def mint(session: Session, *, email: str, name: str, ttl_days: int | None = None) -> str:
    """Mint a new bearer token for the ACTIVE `User` matching `email`, and insert its hashed row.

    Phase-6 remediation task-03 (WR-02, migration 0005): the new row is stamped with the owner's
    CURRENT `session_epoch` — a subsequent `/auth/logout` (which bumps that counter) revokes this
    token exactly as it already revokes every outstanding session cookie
    (`app.auth.tokens.resolve_bearer_token`).

    Phase-6 remediation task-09 (WR-02 residual, migration 0006): the new row is also stamped with
    `expires_at = now() + ttl_days` — `app.auth.tokens.resolve_bearer_token` rejects it once that
    passes.

    Args:
        session: an open `Session` the caller owns — flushed (to surface constraint errors and
            assign the new row's id eagerly) but never committed here; the caller commits.
        email: the token owner's email (normalized `strip().lower()` before lookup, mirroring
            `app.services.users.upsert_from_google`'s own normalization).
        name: a human-readable label for the token (e.g. `"ci-connector"`), stored verbatim.
        ttl_days: how many days from now the new token should live. `None` (the default — every
            pre-task-09 call site, including `tests/test_bearer_revocation.py`'s pinned 3-arg
            calls, keeps this OPTIONAL) falls back to `Settings().mcp_token_ttl_days` (90 by
            default; `MCP_TOKEN_TTL_DAYS`-overridable).

    Returns:
        The raw token string (`"adk_" + secrets.token_urlsafe(32)`) — the ONLY time it is ever
        available; only its sha256 hash is persisted.

    Raises:
        LookupError: no active (non-soft-deleted) `User` row matches `email` — covers both an
            unknown email and a soft-deleted one identically, since neither should ever be
            allowed to mint a working token.
    """
    normalized_email = email.strip().lower()
    user = session.execute(
        active_select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if user is None:
        raise LookupError(f"No active user found for email {email!r}.")

    resolved_ttl_days = ttl_days if ttl_days is not None else Settings().mcp_token_ttl_days
    raw_token, token_hash = mint_token()
    session.add(
        ApiToken(
            user_id=user.id,
            token_hash=token_hash,
            name=name,
            session_epoch=user.session_epoch,
            expires_at=datetime.now(UTC) + timedelta(days=resolved_ttl_days),
        )
    )
    session.flush()
    return raw_token


def revoke(session: Session, token_id: uuid.UUID) -> None:
    """Hard-delete the `ApiToken` row for `token_id` — immediate revocation, no restore path.

    Args:
        session: an open `Session` the caller owns — flushed but never committed here.
        token_id: the `ApiToken.id` to delete.

    Raises:
        LookupError: no `api_tokens` row matches `token_id`.
    """
    token = session.get(ApiToken, token_id)
    if token is None:
        raise LookupError(f"No api_tokens row found for id {token_id}.")
    session.delete(token)
    session.flush()


def _print_table(session: Session) -> None:
    """Print every token's `id`, `name`, owning user email, `created_at`, `expires_at`, and
    epoch-revoked state — never a hash or raw token.

    Phase-6 remediation task-09 (WR-02 residual, design pin #3): `--list` now surfaces both
    lifecycle signals an operator needs to reason about a token without touching the DB directly —
    `expires_at` (`"never"` for a `NULL` row — legacy or a deliberately-unlimited mint) and
    `revoked` (`"yes"` when `ApiToken.session_epoch` no longer matches the owning `User`'s CURRENT
    `session_epoch` — a since-run `/auth/logout`, phase-6 remediation task-03, WR-02 — even though
    the row itself is still physically present). Cheap: both columns come from the SAME join this
    function already runs, no extra query.
    """
    rows = session.execute(
        select(
            ApiToken.id,
            ApiToken.name,
            User.email,
            ApiToken.created_at,
            ApiToken.expires_at,
            ApiToken.session_epoch,
            User.session_epoch,
        )
        .join(User, ApiToken.user_id == User.id)
        .order_by(ApiToken.created_at)
    ).all()
    if not rows:
        print("No api_tokens rows.")
        return
    print(
        f"{'id':<36}  {'name':<24}  {'email':<32}  {'created_at':<26}  {'expires_at':<26}  revoked"
    )
    for token_id, name, email, created_at, expires_at, token_epoch, user_epoch in rows:
        expiry_display = expires_at if expires_at is not None else "never"
        revoked_display = "yes" if token_epoch != user_epoch else "no"
        print(
            f"{token_id!s:<36}  {name:<24}  {email:<32}  {created_at!s:<26}  "
            f"{expiry_display!s:<26}  {revoked_display}"
        )


def _session_factory_from_env() -> sessionmaker[Session]:
    """Build a session factory from `DATABASE_URL`, or exit 1 if it's unset/empty."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL is required (read from the environment).", file=sys.stderr)
        raise SystemExit(1)
    return make_session_factory(make_engine(database_url))


def _build_parser() -> argparse.ArgumentParser:
    """Build the `--mint` / `--list` / `--revoke` CLI (mutually exclusive actions)."""
    parser = argparse.ArgumentParser(
        description="Mint, list, or revoke MCP bearer tokens (DATABASE_URL read from env)."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--mint", action="store_true", help="Mint a new bearer token.")
    action.add_argument(
        "--list", action="store_true", help="List existing tokens (no hashes, no raw tokens)."
    )
    action.add_argument("--revoke", metavar="TOKEN_ID", help="Hard-delete a token by its id.")
    parser.add_argument("--email", help="Active admin's email — required with --mint.")
    parser.add_argument("--name", help="Human-readable label for the token — required with --mint.")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse argv, open one session from `DATABASE_URL`, dispatch to the requested action."""
    args = _build_parser().parse_args(argv)

    if args.mint and (not args.email or not args.name):
        print("--mint requires both --email and --name.", file=sys.stderr)
        raise SystemExit(1)

    session_factory = _session_factory_from_env()
    session = session_factory()
    try:
        if args.mint:
            try:
                raw_token = mint(session, email=args.email, name=args.name)
            except LookupError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
            session.commit()
            print("Token minted — shown ONCE, store it now, it cannot be retrieved again:")
            print(raw_token)
        elif args.list:
            _print_table(session)
        else:
            try:
                token_id = uuid.UUID(args.revoke)
            except ValueError as exc:
                print(f"Invalid token id: {args.revoke!r}", file=sys.stderr)
                raise SystemExit(1) from exc
            try:
                revoke(session, token_id)
            except LookupError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
            session.commit()
            print(f"Revoked token {token_id}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
