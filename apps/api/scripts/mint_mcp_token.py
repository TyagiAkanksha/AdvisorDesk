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

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.tokens import mint_token
from app.db import make_engine, make_session_factory
from app.models.api_tokens import ApiToken
from app.models.users import User
from app.services.queries import active_select


def mint(session: Session, *, email: str, name: str) -> str:
    """Mint a new bearer token for the ACTIVE `User` matching `email`, and insert its hashed row.

    Phase-6 remediation task-03 (WR-02, migration 0005): the new row is stamped with the owner's
    CURRENT `session_epoch` — a subsequent `/auth/logout` (which bumps that counter) revokes this
    token exactly as it already revokes every outstanding session cookie
    (`app.auth.tokens.resolve_bearer_token`).

    Args:
        session: an open `Session` the caller owns — flushed (to surface constraint errors and
            assign the new row's id eagerly) but never committed here; the caller commits.
        email: the token owner's email (normalized `strip().lower()` before lookup, mirroring
            `app.services.users.upsert_from_google`'s own normalization).
        name: a human-readable label for the token (e.g. `"ci-connector"`), stored verbatim.

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

    raw_token, token_hash = mint_token()
    session.add(
        ApiToken(
            user_id=user.id,
            token_hash=token_hash,
            name=name,
            session_epoch=user.session_epoch,
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
    """Print every token's `id`, `name`, owning user email, and `created_at` — never a hash or
    raw token."""
    rows = session.execute(
        select(ApiToken.id, ApiToken.name, User.email, ApiToken.created_at)
        .join(User, ApiToken.user_id == User.id)
        .order_by(ApiToken.created_at)
    ).all()
    if not rows:
        print("No api_tokens rows.")
        return
    print(f"{'id':<36}  {'name':<24}  {'email':<32}  created_at")
    for token_id, name, email, created_at in rows:
        print(f"{token_id!s:<36}  {name:<24}  {email:<32}  {created_at}")


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
