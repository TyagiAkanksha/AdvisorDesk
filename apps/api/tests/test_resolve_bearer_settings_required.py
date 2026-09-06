"""P7 remediation (fresh-review M2) — `resolve_bearer_token`'s `settings` parameter is now
REQUIRED, closing the fail-OPEN default it used to have.

Before this fix, `settings: Settings | None = None` meant a 2-arg call (`resolve_bearer_token
(session, raw_token)`) silently SKIPPED the `ADMIN_EMAILS` allowlist re-check — WR-02's actual
revocation mechanism — a fail-open default on the highest-value gate in `app.auth.tokens`. The
one production caller (`app.mcp.server._resolve_bearer_principal`) always passed a live
`Settings`, so this was latent, not live, but it was a foot-gun for any future caller (a new
script, a test copied as a template, a second MCP mount) that might call the 2-arg form and
silently lose allowlist revocation while keeping full write access.

This file pins the fix at the Python-signature level (a bare 2-arg call now fails loudly with a
`TypeError`, not a silent skip) — the existing HTTP-level allowlist-recheck behavior itself
(`app.mcp.server._resolve_bearer_principal` always supplying a live `Settings`) stays exactly as
pinned by `tests/test_bearer_expiry_allowlist.py`'s own end-to-end tests; this file does not
duplicate those.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy.orm import Session

from app.auth.tokens import mint_token, resolve_bearer_token
from app.config import Settings
from app.models import User
from app.models.api_tokens import ApiToken


def test_resolve_bearer_token_signature_has_no_default_for_settings() -> None:
    """The fix itself: `settings` must be a required parameter (no default value at all) — a
    static, no-DB pin that fails immediately if a future edit reintroduces the fail-open
    `= None` default."""
    signature = inspect.signature(resolve_bearer_token)
    settings_param = signature.parameters["settings"]

    assert settings_param.default is inspect.Parameter.empty


def test_resolve_bearer_token_without_settings_raises_type_error(db_session: Session) -> None:
    """Behavioral pin mirroring the signature pin above: the OLD 2-arg call shape
    (`resolve_bearer_token(session, raw_token)`, no `settings`) must now raise `TypeError` rather
    than silently resolving with the allowlist check skipped."""
    owner = User(email="settings-required@example.com", name="Settings Required Owner")
    db_session.add(owner)
    db_session.flush()
    raw, token_hash = mint_token()
    db_session.add(
        ApiToken(
            user_id=owner.id,
            token_hash=token_hash,
            name="settings-required-token",
            session_epoch=owner.session_epoch,
        )
    )
    db_session.flush()

    with pytest.raises(TypeError):
        resolve_bearer_token(db_session, raw)  # type: ignore[call-arg]


def test_resolve_bearer_token_with_explicit_settings_still_enforces_allowlist(
    db_session: Session,
) -> None:
    """Regression guard for the underlying WR-02 behavior this signature change protects: a
    well-formed, non-expired, non-revoked token whose owner is NOT in the supplied `Settings`'
    `ADMIN_EMAILS` must still resolve to `None` — the required parameter is not merely present,
    it is actually consulted."""
    owner = User(email="not-on-the-list@example.com", name="Not On The List")
    db_session.add(owner)
    db_session.flush()
    raw, token_hash = mint_token()
    db_session.add(
        ApiToken(
            user_id=owner.id,
            token_hash=token_hash,
            name="not-on-the-list-token",
            session_epoch=owner.session_epoch,
        )
    )
    db_session.flush()

    principal = resolve_bearer_token(
        db_session, raw, Settings(admin_emails="someone-else@example.com")
    )

    assert principal is None
