"""DB tests for the OAuth data model: migration 0007's four new tables, the three new nullable
`api_tokens` columns, cascade/uniqueness constraints, and the mint script's new `resource`/
`client_id` stamping (docs/plans/mcp-oauth/task-01-data-model-migration.md; DESIGN.md §"Token &
data model").

All tests use the `db_session`/`tmp_engine` fixtures (`tests/conftest.py`, CONVENTIONS.md §10) —
a throwaway `advisordesk_test_<hex8>` Postgres schema migrated to `alembic upgrade head`, so
these only run for real when `TEST_DATABASE_URL` is set (skipped by fixture name otherwise).

RED today: `app.models.oauth` does not exist at all, so the module-level import below fails at
collection with `ImportError`, taking down every test in this file — the natural shape for four
not-yet-existing models (task-01 test-author instructions sanction this: a whole-module
collection-time ImportError is acceptable RED). Once `app.models.oauth` exists but migration 0007
hasn't been written yet, `tmp_engine`'s own `alembic upgrade head` fixture setup would instead
fail with a missing-table error for any test that touches the DB — also acceptable RED, just not
what happens at the CURRENT (pre-`app/models/oauth.py`) state of the tree.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.models.api_tokens import ApiToken
from app.models.oauth import OAuthAuthorizationCode, OAuthClient, OAuthConsent, OAuthRefreshToken

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _import_mint_script() -> object:
    """Import `scripts/mint_mcp_token.py` by inserting `scripts/` onto `sys.path` — duplicated
    from `tests/test_mint_allowlist.py::_import_mint_script` rather than shared, matching this
    repo's own established no-cross-test-file-import precedent for that script."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import mint_mcp_token

    return mint_mcp_token


def test_migration_head_creates_oauth_tables(tmp_engine: Engine) -> None:
    """Migration 0007 creates all four new OAuth tables (task-01 brief Interfaces block),
    schema-aware like `tests/test_models_schema.py::test_inspector_sees_hnsw_and_fk_indexes` —
    `tmp_engine` is already pinned to the throwaway schema's search_path, so a plain
    `get_table_names()` (no explicit `schema=` arg needed) reflects only that schema."""
    inspector = sa.inspect(tmp_engine)

    table_names = set(inspector.get_table_names())

    assert {
        "oauth_clients",
        "oauth_authorization_codes",
        "oauth_refresh_tokens",
        "oauth_consents",
    } <= table_names


def test_api_tokens_has_new_nullable_columns(tmp_engine: Engine) -> None:
    """`api_tokens` gains `client_id`, `resource`, `last_used_at`, each nullable — additive
    columns so every existing `ApiToken(...)` call site keeps working (task-01 brief)."""
    inspector = sa.inspect(tmp_engine)
    columns = {column["name"]: column for column in inspector.get_columns("api_tokens")}

    for column_name in ("client_id", "resource", "last_used_at"):
        assert column_name in columns
        assert columns[column_name]["nullable"] is True


def test_legacy_api_token_constructor_still_inserts(db_session: Session) -> None:
    """A pre-existing 3-kwarg `ApiToken(user_id=..., token_hash=..., name=...)` constructor call
    — the shape every pre-task-01 call site across the test suite uses — must keep inserting, and
    the three new columns must read back `None` on a real round-trip (task-01 brief: "all
    nullable so every existing ApiToken(...) call site keeps working")."""
    user = User(email="legacy-api-token-ctor@example.com", name="Legacy Ctor")
    db_session.add(user)
    db_session.flush()

    token = ApiToken(user_id=user.id, token_hash="legacy-ctor-hash", name="legacy-token")
    db_session.add(token)
    db_session.flush()
    db_session.expire(token)

    stored = db_session.get(ApiToken, token.id)
    assert stored is not None
    assert stored.client_id is None
    assert stored.resource is None
    assert stored.last_used_at is None


def test_deleting_client_cascades_to_dependents(db_session: Session) -> None:
    """Deleting an `oauth_clients` row cascades (DB-level `ON DELETE CASCADE`, per the task-01
    brief's Interfaces block) to every dependent row: its authorization code, refresh token,
    consent, and any `api_tokens` row minted for it.

    The four dependent rows are inserted through the ORM but the delete itself is DB-side —
    SQLAlchemy's identity map does not know the DB cascaded the delete, so a `.get()` right after
    `flush()` would return the stale, still-cached Python object instead of re-querying (a false
    negative even once the cascade is correctly wired). `db_session.expire_all()` forces the
    follow-up `.get()` calls to hit the database for real.
    """
    user = User(email="cascade-user@example.com", name="Cascade User")
    db_session.add(user)
    db_session.flush()

    client = OAuthClient(
        client_id="client-cascade-1",
        client_name="Cascade Client",
        redirect_uris=["https://example.com/callback"],
    )
    db_session.add(client)
    db_session.flush()

    now = datetime.now(UTC)
    auth_code = OAuthAuthorizationCode(
        code_hash="cascade-code-hash",
        client_id=client.client_id,
        user_id=user.id,
        redirect_uri="https://example.com/callback",
        code_challenge="cascade-challenge",
        resource="https://api.example/api/v1/mcp",
        scope="mcp",
        expires_at=now + timedelta(seconds=60),
    )
    refresh_token = OAuthRefreshToken(
        token_hash="cascade-refresh-hash",
        client_id=client.client_id,
        user_id=user.id,
        family_id=uuid.uuid4(),
        resource="https://api.example/api/v1/mcp",
        scope="mcp",
        expires_at=now + timedelta(days=30),
    )
    consent = OAuthConsent(user_id=user.id, client_id=client.client_id, scope="mcp")
    api_token = ApiToken(
        user_id=user.id,
        token_hash="cascade-api-token-hash",
        name="cascade-token",
        client_id=client.client_id,
    )
    db_session.add_all([auth_code, refresh_token, consent, api_token])
    db_session.flush()

    auth_code_id, refresh_token_id, consent_id, api_token_id = (
        auth_code.id,
        refresh_token.id,
        consent.id,
        api_token.id,
    )

    db_session.delete(client)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(OAuthAuthorizationCode, auth_code_id) is None
    assert db_session.get(OAuthRefreshToken, refresh_token_id) is None
    assert db_session.get(OAuthConsent, consent_id) is None
    assert db_session.get(ApiToken, api_token_id) is None


def test_consent_unique_per_user_client(db_session: Session) -> None:
    """A second `OAuthConsent` row for the same `(user_id, client_id)` pair violates
    `uq_oauth_consents_user_id_client_id` and raises `IntegrityError` on flush (task-01 brief
    Interfaces block: `UniqueConstraint("user_id", "client_id", ...)`)."""
    user = User(email="consent-unique@example.com", name="Consent Unique")
    db_session.add(user)
    db_session.flush()

    client = OAuthClient(
        client_id="client-consent-unique",
        client_name="Consent Unique Client",
        redirect_uris=["https://example.com/callback"],
    )
    db_session.add(client)
    db_session.flush()

    db_session.add(OAuthConsent(user_id=user.id, client_id=client.client_id, scope="mcp"))
    db_session.flush()

    db_session.add(OAuthConsent(user_id=user.id, client_id=client.client_id, scope="mcp"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_refresh_token_hash_unique(db_session: Session) -> None:
    """A duplicate `token_hash` across two `OAuthRefreshToken` rows raises `IntegrityError` on
    flush (task-01 brief Interfaces block: `token_hash: Mapped[str]  # Text, unique, not null`)."""
    user = User(email="refresh-hash-unique@example.com", name="Refresh Hash Unique")
    db_session.add(user)
    db_session.flush()

    client = OAuthClient(
        client_id="client-refresh-hash-unique",
        client_name="Refresh Hash Unique Client",
        redirect_uris=["https://example.com/callback"],
    )
    db_session.add(client)
    db_session.flush()

    now = datetime.now(UTC)
    shared_hash = "duplicate-refresh-token-hash"
    db_session.add(
        OAuthRefreshToken(
            token_hash=shared_hash,
            client_id=client.client_id,
            user_id=user.id,
            family_id=uuid.uuid4(),
            resource="https://api.example/api/v1/mcp",
            scope="mcp",
            expires_at=now + timedelta(days=30),
        )
    )
    db_session.flush()

    db_session.add(
        OAuthRefreshToken(
            token_hash=shared_hash,
            client_id=client.client_id,
            user_id=user.id,
            family_id=uuid.uuid4(),
            resource="https://api.example/api/v1/mcp",
            scope="mcp",
            expires_at=now + timedelta(days=30),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_mint_script_stamps_resource_and_null_client(db_session: Session) -> None:
    """`scripts/mint_mcp_token.py::mint` stamps every fresh `ApiToken` row with
    `resource=settings.mcp_resource_url` and `client_id=None` (task-01 brief: "The CLI mint
    script starts stamping `resource`")."""
    mint_mcp_token = _import_mint_script()
    email = "oauth-mint-stamp@example.com"
    user = User(email=email, name="OAuth Mint Stamp")
    db_session.add(user)
    db_session.flush()

    settings = Settings(
        session_secret="s", admin_emails=email, oauth_issuer_url="https://api.example"
    )

    raw_token = mint_mcp_token.mint(db_session, email=email, name="ci-oauth", settings=settings)

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token_row = db_session.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    ).scalar_one()

    assert token_row.resource == "https://api.example/api/v1/mcp"
    assert token_row.client_id is None
