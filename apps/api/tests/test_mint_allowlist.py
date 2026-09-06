"""P7 remediation (fresh-review M4) — `scripts/mint_mcp_token.py::mint` now enforces the
`ADMIN_EMAILS` allowlist at MINT time, closing the "dead-on-arrival token" gap.

Before this fix, `mint()` looked up an ACTIVE `User` by email but never checked the email was in
`ADMIN_EMAILS` — removing an admin from `ADMIN_EMAILS` does not soft-delete their `users` row, so
an operator could still mint a token for a since-offboarded admin. `app.auth.tokens.
resolve_bearer_token`'s own allowlist re-check (WR-02 residual) made such a token inert in
production, but only as a SECOND gate — this task adds the FIRST one, so mint and resolve agree,
and an operator gets a clear, immediate error instead of a working-looking-but-inert credential.

`mint()`'s new `settings` parameter is OPTIONAL (defaults to `None`, which skips this check) so
every pre-existing pinned call site across `tests/test_bearer_revocation.py`/`tests/test_bearer_
expiry_allowlist.py`/`tests/test_mcp_bearer_auth.py` (none of which pass `settings` at all, and
several of which mint for arbitrary test emails belonging to no allowlist) keeps minting exactly
as before. This file exercises the NEW, opted-in behavior directly.

Imports `scripts/mint_mcp_token.py` via the sys.path-insertion technique every other bearer-auth
test file already uses (it is not an installed package) — duplicated locally rather than shared,
matching this repo's own established no-cross-test-file-import precedent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _import_mint_script() -> object:
    """Import `scripts/mint_mcp_token.py` by inserting `scripts/` onto `sys.path`."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import mint_mcp_token

    return mint_mcp_token


def test_mint_for_non_allowlisted_active_user_raises_when_settings_given(
    db_session: Session,
) -> None:
    """The core M4 pin: an ACTIVE (not soft-deleted) user whose email is NOT in the `Settings`
    given to `mint()` must raise `LookupError` — a mint that would otherwise succeed and produce
    a token that `resolve_bearer_token` would reject on its very first use."""
    mint_mcp_token = _import_mint_script()
    email = "offboarded-admin@example.com"
    user = User(email=email, name="Offboarded Admin")
    db_session.add(user)
    db_session.commit()

    settings = Settings(admin_emails="someone-else@example.com")

    with pytest.raises(LookupError):
        mint_mcp_token.mint(db_session, email=email, name="ci", settings=settings)


def test_mint_for_allowlisted_active_user_succeeds_when_settings_given(
    db_session: Session,
) -> None:
    """Symmetry check: an active user whose email IS in the supplied `Settings`' `ADMIN_EMAILS`
    mints normally — the new check must not reject a legitimately allowlisted operator."""
    mint_mcp_token = _import_mint_script()
    email = "current-admin@example.com"
    user = User(email=email, name="Current Admin")
    db_session.add(user)
    db_session.commit()

    settings = Settings(admin_emails=email)

    raw_token = mint_mcp_token.mint(db_session, email=email, name="ci", settings=settings)

    assert raw_token.startswith("adk_")


def test_mint_without_settings_still_skips_allowlist_check_for_backward_compatibility(
    db_session: Session,
) -> None:
    """`settings` stays OPTIONAL: a bare 3-arg `mint()` call (no `settings` at all) for an email
    belonging to no allowlist whatsoever must keep succeeding exactly as before this fix — this is
    the exact shape every pinned bearer-auth test file's existing `mint()` calls use, and none of
    them may break."""
    mint_mcp_token = _import_mint_script()
    email = "not-on-any-allowlist@example.com"
    user = User(email=email, name="Not On Any Allowlist")
    db_session.add(user)
    db_session.commit()

    raw_token = mint_mcp_token.mint(db_session, email=email, name="ci")

    assert raw_token.startswith("adk_")
