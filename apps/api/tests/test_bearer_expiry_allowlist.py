"""Failing (RED) tests for bearer-token expiry + ADMIN_EMAILS re-check on resolve (WR-02 residual).

Task brief: docs/plans/phase-6-remediation/task-09-bearer-expiry-allowlist.md.
Spec: advisordesk-prd.md §3 (MCP exposure), §9 (auth security). WR-02 residual — the expiry and
allowlist-recheck halves 6R-03 (session_epoch revocation, f189453) deliberately left open.

Today `api_tokens` has no `expires_at` column, `Settings` has no `mcp_token_ttl_days` field, and
`resolve_bearer_token` never compares either the token's expiry or the resolved user's email
against `ADMIN_EMAILS`. Every collaborator this task's implementer touches already exists
(`app.auth.tokens`, `app.models.api_tokens.ApiToken`, `app.config.Settings`,
`scripts/mint_mcp_token.py`) — none is new, so this file imports them all at MODULE scope (mirrors
`tests/test_bearer_revocation.py`'s own "every collaborator module already exists" precedent, not
`tests/test_mcp_bearer_auth.py`'s per-test local-import split). RED is uniformly BEHAVIORAL: a
`TypeError` from an `ApiToken(...)` constructor call passing a not-yet-mapped `expires_at` kwarg,
an `AttributeError` reading `token_row.expires_at` off a freshly-minted row, a real
wrong-status-code/wrong-envelope assertion, an empty caplog-records match, or (the migration test)
a genuine `alembic.util.exc.CommandError` for revision "0006" — never a collection-time import
error for this whole file.

INTERFACE ASSUMPTIONS / JUDGMENT CALLS (test-author decisions pinning the brief's design where the
interface doesn't exist yet — flagged here AND in the test-author report for adjudication):

  1. Default TTL: the brief says "pick a sane value — 90 days — and document it" without pinning
     the exact number as a hard requirement. This file pins **90 days** as `_DEFAULT_TTL_DAYS`,
     using the brief's own suggested value verbatim, and asserts `mint()`'s stamped `expires_at`
     falls in a narrow `[before, after] + timedelta(days=90)` bracket around the mint call itself
     (the same before/after-bracket style `tests/test_retrieval.py`/`test_public_chat.py` use for
     `published_at=datetime.now(UTC)` stamps) rather than freezing the clock — no `freezegun`/
     `time-machine` dependency exists in this project (grepped `pyproject.toml`/`uv.lock`, no
     hits), so a real, tight wall-clock bracket is the available substitute for "fake-clock or
     freeze". This file does NOT test `MCP_TOKEN_TTL_DAYS` env-var overridability — the brief's
     test-author bullet only requires pinning the mint-stamps-a-real-expiry behavior, not the
     override knob, and pinning an exact env-var-reads-through-Settings-vs-raw-env implementation
     choice here would over-constrain the implementer (see judgment call 2).

  2. `scripts/mint_mcp_token.py` deliberately reads `DATABASE_URL` straight from `os.environ`
     rather than through `app.config.Settings` (this script's own module docstring: "not
     `app.config.Settings`, which would also demand every other env var this one-shot CLI never
     needs") — yet design pin #1 puts the new TTL knob ON `Settings` (`mcp_token_ttl_days`). This
     file does not referee that tension: it calls `mint()` with the SAME three-arg
     `(session, email=..., name=...)` shape `tests/test_bearer_revocation.py`'s pinned calls
     already use (any new TTL parameter the implementer adds to `mint()` must therefore be
     OPTIONAL with a default — a required new parameter would break that pinned file's own
     unmodified call sites) and asserts only the OUTWARD default-TTL behavior, leaving HOW the
     script/Settings wire the value to each other as the implementer's call.

  3. `resolve_bearer_token`'s existing signature is `(session, raw_token) -> AdminPrincipal |
     None` — two positional/keyword args, no `Settings`/`admin_email_set` input. The brief's
     allowlist re-check needs the CURRENT `ADMIN_EMAILS` set, which lives on `Settings`, not on
     anything already reachable from inside `resolve_bearer_token`'s existing parameters.
     Design pin #2 doesn't specify the new parameter's shape, and `tests/test_bearer_revocation.py`
     (pinned, e.g.
     `test_resolve_bearer_token_returns_principal_when_token_epoch_matches_user_epoch`)
     calls `resolve_bearer_token(db_session, raw)` with exactly two args and an owner email that is
     a member of NO allowlist at all — so whatever new parameter the implementer adds MUST be
     optional (defaulting to either "skip the check" or "resolve against the live `Settings()`"),
     or that pinned call breaks. This file sidesteps pinning that exact shape: expiry-rejection
     tests call `resolve_bearer_token(session, raw)` directly (mirroring the pinned file's own
     direct-call style, since expiry needs no `Settings` input at all), while allowlist-recheck
     tests exercise the behavior ONLY through the full HTTP surface (`client.post(_MCP_PATH, ...)`
     against a `TestClient` whose `app.state.settings.admin_emails` is mutated live between two
     requests on the SAME client) — mirroring how `tests/test_bearer_revocation.py`'s own
     allowlist-adjacent event 2 tests (`test_caplog_login_rejected_non_allowlisted_email_...`)
     drive their behavior end-to-end through the app rather than by calling an internal function
     with a guessed-at new keyword. `Settings` carries no `model_config` forbidding mutation
     (pydantic v2 `BaseSettings` instances are ordinary mutable objects by default — grepped, no
     `frozen`/`model_config` override in `app/config.py`), and `admin_email_set` is a `@property`
     recomputed from `self.admin_emails` on every access rather than cached at construction, so
     mutating `client.app.state.settings.admin_emails` between two requests on one `TestClient`
     is a legitimate way to simulate "the operator edited `ADMIN_EMAILS` and the process picked it
     up" without needing a second app/process.

  4. Migration 0006 chains after 0005 (mirrors 0004->0005's own chaining) and adds
     `api_tokens.expires_at TIMESTAMPTZ NULL` in ONE step — unlike 0005's session_epoch (added
     nullable, backfilled via an `UPDATE ... FROM users` join, THEN tightened to `NOT NULL`),
     design pin #1 wants NULL to MEAN "no expiry" permanently, so the column stays nullable
     forever and needs no backfill UPDATE at all — every pre-existing row's `expires_at` is NULL
     "for free" the instant the column is added, which is exactly the brief's own "existing rows
     backfill NULL" pin. This mirrors the existing `content.published_at` column
     (`app/models/content.py`: `Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
     nullable=True)`) rather than `api_tokens.session_epoch`'s NOT-NULL-with-real-backfill shape.
     The round-trip test below still proves the "backfills NULL for an EXISTING row" pin
     empirically (inserts a row at 0005, upgrades to 0006, reads that SAME row's `expires_at`
     back as NULL) rather than assuming it from the column's nullability alone.

  5. Reason keywords: the brief names them explicitly — `expired` and `not-allowlisted` — used
     here as literal, case-insensitive substrings, mirroring
     `tests/test_bearer_revocation.py`'s own treatment of its four event-6 reason keywords
     (`unknown`/`revoked`/`inactive-user`/`malformed`).

  6. Pinned-file stop rule: `tests/test_bearer_revocation.py` (sha256 5e8ece9e) and the registry
     hashes it belongs to are READ-ONLY for this task — nothing below imports from it (this
     repo's established no-cross-test-file-import precedent; every local helper below is
     duplicated rather than shared, matching `tests/test_bearer_revocation.py`'s own module
     docstring rationale for doing the same relative to `tests/test_mcp_bearer_auth.py`).

Every DB-touching test below requests `tmp_engine`/`db_session` (skipped by fixture name when
`TEST_DATABASE_URL` is unset per `tests/conftest.py`) except the migration round-trip test, which
manages its own throwaway schema directly (mirrors `tests/test_bearer_revocation.py`'s own
migration test for the identical reason: a round trip needs to pause at an INTERMEDIATE revision,
0005, that the shared `tmp_engine` fixture's always-`head` migration never stops at) and guards
itself with an explicit `pytest.skip` on a missing `TEST_DATABASE_URL`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from app.auth.tokens import mint_token, resolve_bearer_token
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.factory import create_app
from app.models import User
from app.models.api_tokens import ApiToken

_MCP_PATH = "/api/v1/mcp"

# Copied from `test_mcp_bearer_auth.py`/`test_bearer_revocation.py` (kept local per those files'
# own no-cross-test-file-dependency precedent): Streamable HTTP 406s before ever reaching
# auth/dispatch without both of these on `Accept`.
_MCP_HEADERS = {"Accept": "application/json, text/event-stream"}

_INITIALIZE_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.1"},
    },
}

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_ALEMBIC_SCRIPT_LOCATION = Path(__file__).resolve().parent.parent / "alembic"

# Judgment call 1: the brief's own suggested default TTL, pinned verbatim.
_DEFAULT_TTL_DAYS = 90


# ---------------------------------------------------------------------------
# Local helpers (duplicated rather than shared/imported — see module docstring, judgment call 6)
# ---------------------------------------------------------------------------


def _build_settings(*, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        environment="development",
        mcp_http_enabled=True,
    )


def _build_client(tmp_engine: Engine, *, admin_emails: str = "admin@example.com") -> TestClient:
    """Build a `TestClient` over a real, DB-backed, MCP-HTTP-enabled app.

    No OAuth seam is wired (`oauth_client` left `None`) — every test in this file drives only the
    MCP bearer path and direct DB setup, never `/auth/login`/`/auth/callback`.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
    )
    return TestClient(app)


def _import_mint_script() -> object:
    """Import `scripts/mint_mcp_token.py` by inserting `scripts/` onto `sys.path` (it is not an
    installed package). Mirrors `tests/test_mcp_bearer_auth.py::_import_mint_script` exactly."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import mint_mcp_token

    return mint_mcp_token


def _fetch_token_by_hash(session: Session, raw_token: str) -> ApiToken:
    """Look up the persisted `ApiToken` row matching `raw_token`'s sha256 hash."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return session.execute(select(ApiToken).where(ApiToken.token_hash == token_hash)).scalar_one()


def _api_tokens_columns(database_url: str, schema: str) -> dict[str, dict[str, object]]:
    """Return `{column_name: column_info}` for `api_tokens` in `schema`, via a fresh inspection
    connection opened and disposed per call, so each round-trip step sees the schema's CURRENT
    state rather than a stale cached reflection. Duplicated from
    `tests/test_bearer_revocation.py`'s identically-named helper (judgment call 6)."""
    engine = make_engine(database_url, schema=schema)
    try:
        return {column["name"]: column for column in inspect(engine).get_columns("api_tokens")}
    finally:
        engine.dispose()


def _insert_legacy_user_and_token(database_url: str, schema: str) -> uuid.UUID:
    """Insert one `users` row and one `api_tokens` row directly via SQL (bypassing the ORM, which
    doesn't yet know about `expires_at` at the pre-0006 revision this is called at) — simulates a
    row that already existed BEFORE migration 0006 ever ran, so the round-trip test can prove that
    specific row backfills a NULL `expires_at` rather than merely that a column default exists.

    Returns:
        The inserted `api_tokens.id`, for a later SELECT of its `expires_at`.
    """
    engine = make_engine(database_url, schema=schema)
    try:
        with engine.begin() as conn:
            user_id = conn.execute(
                text(
                    "INSERT INTO users (email, name, session_epoch) "
                    "VALUES (:email, :name, 0) RETURNING id"
                ),
                {"email": "legacy-migration-row@example.com", "name": "Legacy Row"},
            ).scalar_one()
            token_id = conn.execute(
                text(
                    "INSERT INTO api_tokens (user_id, token_hash, name, session_epoch) "
                    "VALUES (:user_id, :token_hash, :name, 0) RETURNING id"
                ),
                {
                    "user_id": user_id,
                    "token_hash": hashlib.sha256(b"legacy-row-token").hexdigest(),
                    "name": "legacy-pre-0006-row",
                },
            ).scalar_one()
        return token_id
    finally:
        engine.dispose()


def _select_token_expires_at(database_url: str, schema: str, token_id: uuid.UUID) -> object:
    """Read back `api_tokens.expires_at` for `token_id` via raw SQL (the ORM's `ApiToken` model
    may or may not have caught up with the migration inside this same round-trip test)."""
    engine = make_engine(database_url, schema=schema)
    try:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT expires_at FROM api_tokens WHERE id = :id"), {"id": token_id}
            ).scalar_one()
    finally:
        engine.dispose()


def _assert_bearer_rejected_with_reason(
    client: TestClient,
    headers: dict[str, str],
    reason_keyword: str,
    secret_marker: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Shared assertion body for the 'bearer rejected' reason-keyword scenarios this file adds
    (`expired` / `not-allowlisted`): 401 + `auth_required` envelope, a WARNING record containing
    `reason_keyword`, and `secret_marker` (the raw token presented) absent from EVERY captured
    record. Mirrors `tests/test_bearer_revocation.py::_assert_bearer_rejected_with_reason` and
    `tests/test_auth_log_hygiene.py::_assert_hash_never_logged` (judgment call 6: duplicated, not
    imported)."""
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        response = client.post(_MCP_PATH, json=_INITIALIZE_BODY, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    matches = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and reason_keyword in r.getMessage().lower()
    ]
    assert matches, [r.getMessage() for r in caplog.records]
    assert secret_marker not in caplog.text
    token_hash = hashlib.sha256(secret_marker.encode()).hexdigest()
    assert token_hash not in caplog.text


# ---------------------------------------------------------------------------
# Bullet 1: mint stamps expires_at = now + ttl; expired/NULL/future direct-call behavior
# ---------------------------------------------------------------------------


def test_script_mint_stamps_new_token_with_expires_at_default_ttl_from_now(
    db_session: Session,
) -> None:
    """Design pin #1: `scripts/mint_mcp_token.py::mint` stamps `expires_at` to
    `now() + <default ttl>` on every freshly minted row. See judgment call 1 for why this brackets
    `[before, after] + timedelta(days=_DEFAULT_TTL_DAYS)` rather than freezing the clock. RED
    today: `mint()`'s `ApiToken(...)` construction doesn't pass `expires_at` at all, so the
    inserted row has no such attribute — `token_row.expires_at` raises `AttributeError`."""
    mint_mcp_token = _import_mint_script()
    owner = User(email="mint-stamps-expiry@example.com", name="Mint Stamps Expiry")
    db_session.add(owner)
    db_session.flush()

    before = datetime.now(UTC)
    raw = mint_mcp_token.mint(db_session, email="mint-stamps-expiry@example.com", name="ci")  # type: ignore[attr-defined]
    db_session.flush()
    after = datetime.now(UTC)

    token_row = _fetch_token_by_hash(db_session, raw)
    assert token_row.expires_at is not None
    assert before + timedelta(days=_DEFAULT_TTL_DAYS) <= token_row.expires_at
    assert token_row.expires_at <= after + timedelta(days=_DEFAULT_TTL_DAYS)


def test_resolve_bearer_token_rejects_token_past_expiry(db_session: Session) -> None:
    """Design pin #2(a): a well-formed, known, non-revoked token whose `expires_at` is in the
    past must resolve to `None` (the same "reject silently" contract `resolve_bearer_token`
    already has for an unknown/revoked token). Constructs the `ApiToken` row directly with an
    explicit past `expires_at` (bypassing `mint()`, which always stamps a FUTURE expiry) so this
    test isolates purely the expiry compare. RED today: `ApiToken(..., expires_at=...)` raises
    `TypeError` (an unexpected keyword argument) — a clean behavioral failure, not a collection
    error.

    P7 remediation (fresh-review M2): `resolve_bearer_token`'s `settings` parameter is now
    REQUIRED — passes an explicit `Settings` allowlisting the owner's own email, so the expiry
    check (not an incidental allowlist mismatch) is what this test isolates."""
    owner = User(email="past-expiry@example.com", name="Past Expiry Owner")
    db_session.add(owner)
    db_session.flush()
    raw, token_hash = mint_token()
    db_session.add(
        ApiToken(
            user_id=owner.id,
            token_hash=token_hash,
            name="past-expiry-token",
            session_epoch=owner.session_epoch,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.flush()

    principal = resolve_bearer_token(
        db_session, raw, Settings(admin_emails="past-expiry@example.com")
    )

    assert principal is None


def test_resolve_bearer_token_accepts_token_with_null_expires_at(db_session: Session) -> None:
    """Design pin #1's 'NULL = no expiry' contract: a legacy (pre-migration-0006-equivalent)
    token with an explicit `expires_at=None` must still authenticate — this is the backward
    compatibility guarantee that keeps every already-deployed connector token alive across the
    migration. RED today: `ApiToken(..., expires_at=None)` raises `TypeError`.

    P7 remediation (fresh-review M2): `resolve_bearer_token`'s `settings` parameter is now
    REQUIRED — passes an explicit `Settings` allowlisting the owner's own email."""
    owner = User(email="null-expiry@example.com", name="Null Expiry Owner")
    db_session.add(owner)
    db_session.flush()
    raw, token_hash = mint_token()
    db_session.add(
        ApiToken(
            user_id=owner.id,
            token_hash=token_hash,
            name="null-expiry-token",
            session_epoch=owner.session_epoch,
            expires_at=None,
        )
    )
    db_session.flush()

    principal = resolve_bearer_token(
        db_session, raw, Settings(admin_emails="null-expiry@example.com")
    )

    assert principal is not None
    assert principal.user_id == owner.id


def test_resolve_bearer_token_accepts_token_with_future_expires_at(db_session: Session) -> None:
    """Symmetry check for design pin #2(a)'s boundary: a token whose `expires_at` is still in the
    FUTURE must resolve normally — the expiry check must not reject a token merely for HAVING an
    `expires_at` value. RED today: `ApiToken(..., expires_at=...)` raises `TypeError`.

    P7 remediation (fresh-review M2): `resolve_bearer_token`'s `settings` parameter is now
    REQUIRED — passes an explicit `Settings` allowlisting the owner's own email."""
    owner = User(email="future-expiry@example.com", name="Future Expiry Owner")
    db_session.add(owner)
    db_session.flush()
    raw, token_hash = mint_token()
    db_session.add(
        ApiToken(
            user_id=owner.id,
            token_hash=token_hash,
            name="future-expiry-token",
            session_epoch=owner.session_epoch,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db_session.flush()

    principal = resolve_bearer_token(
        db_session, raw, Settings(admin_emails="future-expiry@example.com")
    )

    assert principal is not None
    assert principal.user_id == owner.id


# ---------------------------------------------------------------------------
# Bullet 1 (continued) + Bullet 2: envelope parity with "unknown" at the HTTP boundary
# ---------------------------------------------------------------------------


def test_expired_bearer_and_unknown_bearer_return_byte_identical_401_envelope(
    tmp_engine: Engine,
) -> None:
    """The 'no oracle' requirement extended to expiry: a WELL-FORMED-but-expired bearer token and
    a WELL-FORMED-but-unknown one must be indistinguishable from outside — same status code, same
    exact JSON envelope. The owner's email is included in `ADMIN_EMAILS` so only the expiry check
    (not an allowlist rejection) can be responsible for the 401, isolating this pin from bullet 2's
    allowlist-recheck pin below."""
    email = "expired-envelope-parity@example.com"
    client = _build_client(tmp_engine, admin_emails=email)
    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email=email, name="Expired Envelope Owner")
        session.add(owner)
        session.flush()
        raw, token_hash = mint_token()
        session.add(
            ApiToken(
                user_id=owner.id,
                token_hash=token_hash,
                name="expired-envelope-token",
                session_epoch=owner.session_epoch,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        session.commit()
    finally:
        session.close()

    expired_response = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw}"},
    )
    unknown_response = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": "Bearer adk_totally-unknown-garbage-value"},
    )

    assert expired_response.status_code == 401
    assert unknown_response.status_code == 401
    assert expired_response.json() == unknown_response.json()


def test_allowlist_removed_admin_bearer_and_unknown_bearer_return_byte_identical_401_envelope(
    tmp_engine: Engine,
) -> None:
    """Design pin #2(b)'s acceptance pin: mint a token for a user whose email IS in
    `ADMIN_EMAILS`, confirm it resolves, then remove that email from `ADMIN_EMAILS` (mutating the
    live `Settings` instance on `app.state` — judgment call 3) and confirm the SAME token now
    401s, with an envelope byte-identical to an unknown token's. RED today: `resolve_bearer_token`
    never consults `ADMIN_EMAILS` at all, so the post-removal request still succeeds (< 400)
    instead of 401ing — a real, behavioral assertion failure."""
    mint_mcp_token = _import_mint_script()
    email = "allowlist-recheck@example.com"
    client = _build_client(tmp_engine, admin_emails=email)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email=email, name="Allowlist Recheck Owner")
        session.add(owner)
        session.commit()
        raw = mint_mcp_token.mint(session, email=email, name="allowlist-recheck-token")  # type: ignore[attr-defined]
        session.commit()
    finally:
        session.close()

    pre_removal = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw}"},
    )
    assert pre_removal.status_code < 400, pre_removal.text

    client.app.state.settings.admin_emails = ""  # type: ignore[attr-defined]

    post_removal = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw}"},
    )
    unknown_response = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": "Bearer adk_totally-unknown-garbage-value"},
    )

    assert post_removal.status_code == 401
    assert unknown_response.status_code == 401
    assert post_removal.json() == unknown_response.json()


# ---------------------------------------------------------------------------
# Bullet 3: migration 0006 up/down/up round-trip; existing rows backfill NULL
# ---------------------------------------------------------------------------


def test_migration_0006_expires_at_column_round_trips_and_backfills_null_for_existing_row() -> None:
    """Design pin #1: migration 0006 (chained after 0005) adds `api_tokens.expires_at`
    (`TIMESTAMPTZ`, nullable, no backfill UPDATE needed — see judgment call 4). Inserts one
    `api_tokens` row BEFORE running 0006 (at revision 0005) via raw SQL, then upgrades and reads
    that SAME row's `expires_at` back as NULL — proving the "existing rows backfill NULL" pin
    empirically for a row that predates the migration, not merely that the column defaults to NULL
    for future inserts.

    RED today: revision '0006' does not exist — `upgrade(cfg, "0006")` raises
    `alembic.util.exc.CommandError` (a real behavioral failure, not a collection error)."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not set")

    schema = f"advisordesk_test_{secrets.token_hex(4)}"
    admin_engine = make_engine(database_url)
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    admin_engine.dispose()

    try:
        alembic_cfg = Config(str(_ALEMBIC_INI))
        alembic_cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
        alembic_cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
        previous_migrate_schema = os.environ.get("MIGRATE_SCHEMA")
        os.environ["MIGRATE_SCHEMA"] = schema
        try:
            upgrade(alembic_cfg, "0005")
            assert "expires_at" not in _api_tokens_columns(database_url, schema)

            token_id = _insert_legacy_user_and_token(database_url, schema)

            upgrade(alembic_cfg, "0006")
            columns = _api_tokens_columns(database_url, schema)
            assert "expires_at" in columns
            assert columns["expires_at"]["nullable"] is True
            assert _select_token_expires_at(database_url, schema, token_id) is None

            downgrade(alembic_cfg, "0005")
            assert "expires_at" not in _api_tokens_columns(database_url, schema)

            upgrade(alembic_cfg, "0006")
            columns = _api_tokens_columns(database_url, schema)
            assert "expires_at" in columns
            assert columns["expires_at"]["nullable"] is True
        finally:
            if previous_migrate_schema is None:
                os.environ.pop("MIGRATE_SCHEMA", None)
            else:
                os.environ["MIGRATE_SCHEMA"] = previous_migrate_schema
    finally:
        admin_engine = make_engine(database_url)
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


# ---------------------------------------------------------------------------
# Bullet 4: audit-log pins for `expired` / `not-allowlisted` + never-log assertions
# ---------------------------------------------------------------------------


def test_caplog_bearer_rejected_expired_token_logs_warning_and_never_logs_token(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event: bearer rejected, reason 'expired' (judgment call 5). The owner's email is in
    `ADMIN_EMAILS` so only the expiry check can be responsible for the rejection."""
    email = "caplog-expired@example.com"
    client = _build_client(tmp_engine, admin_emails=email)
    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email=email, name="Caplog Expired Owner")
        session.add(owner)
        session.flush()
        raw, token_hash = mint_token()
        session.add(
            ApiToken(
                user_id=owner.id,
                token_hash=token_hash,
                name="caplog-expired-token",
                session_epoch=owner.session_epoch,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        session.commit()
    finally:
        session.close()

    _assert_bearer_rejected_with_reason(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}, "expired", raw, caplog
    )


def test_caplog_bearer_rejected_not_allowlisted_token_logs_warning_and_never_logs_token(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event: bearer rejected, reason 'not-allowlisted' (judgment call 5). Mints via the real CLI
    path (so `expires_at` is the default future TTL — not expired), confirms it resolves while the
    owner is still allowlisted, THEN removes the owner's email from `ADMIN_EMAILS` (judgment call
    3's live-settings-mutation technique) before asserting the rejection and its log line."""
    mint_mcp_token = _import_mint_script()
    email = "caplog-not-allowlisted@example.com"
    client = _build_client(tmp_engine, admin_emails=email)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email=email, name="Caplog Not Allowlisted Owner")
        session.add(owner)
        session.commit()
        raw = mint_mcp_token.mint(session, email=email, name="caplog-not-allowlisted-token")  # type: ignore[attr-defined]
        session.commit()
    finally:
        session.close()

    pre_removal = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw}"},
    )
    assert pre_removal.status_code < 400, pre_removal.text

    client.app.state.settings.admin_emails = ""  # type: ignore[attr-defined]

    _assert_bearer_rejected_with_reason(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}, "not-allowlisted", raw, caplog
    )
