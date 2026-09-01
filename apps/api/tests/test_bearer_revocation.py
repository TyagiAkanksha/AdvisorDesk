"""Failing (RED) tests for bearer-token revocation via session epoch + auth audit logging.

Task brief: docs/plans/phase-6-remediation/task-03-bearer-lifecycle-and-audit-log.md.
Spec: advisordesk-prd.md §3 (MCP exposure), §9 (auth security). WR-02 (bearer revocation),
WR-05 (auth audit logging).

Today `api_tokens` has no `session_epoch` column, `resolve_bearer_token` never compares one, and
NOTHING in `app.auth.*`/`app.routes.auth_routes` logs anything at all (grepped: no
`logging.getLogger` in either). Every interface this task's implementer must add/change already
has an EXISTING module to attach to (`app.auth.tokens`, `app.models.api_tokens.ApiToken`,
`scripts/mint_mcp_token.py`, `app.routes.auth_routes`, `app.auth.deps`) — none of those modules
is new, so every test below imports its collaborators at MODULE scope (unlike
`tests/test_mcp_bearer_auth.py`'s per-test local-import RED split, which existed only because
`app.auth.tokens`/`app.models.api_tokens` didn't exist AT ALL at that task's authoring time).
RED mode here is therefore uniformly BEHAVIORAL: a `TypeError`/`AttributeError` from an
ApiToken constructor call or attribute read that doesn't exist yet, a real wrong-status-code or
wrong-envelope assertion, an empty caplog-records match, or (the migration test) a genuine
`alembic.util.exc.CommandError` for a revision id ("0005") that doesn't exist yet — never a
collection-time import error for this whole file.

INTERFACE ASSUMPTIONS / JUDGMENT CALLS (test-author decisions pinning the brief's design where
the interface doesn't exist yet — flagged here AND in the test-author report for adjudication):

  1. Design pin #3 ("Resolve ... reject (AuthRequiredError ...) when
     `token.session_epoch != user.session_epoch`") is ambiguous about WHERE the raise happens:
     literally inside `app.auth.tokens.resolve_bearer_token` (a behavior change from its current
     documented "never raises, returns `None`" contract), or via the SAME `if principal is None:
     raise AuthRequiredError(...)` `app.mcp.server._resolve_bearer_principal` already uses for an
     unknown token (i.e. `resolve_bearer_token` keeps returning `None` for a revoked token too).
     Both satisfy "same code/envelope, no oracle distinguishing the two from outside" — this file
     pins ONLY the outward HTTP/wire-level behavior (a revoked bearer 401s, byte-identical to an
     unknown one) and never asserts, at the Python level, whether `resolve_bearer_token` raises or
     returns `None` for the mismatch case specifically.

  2. Design pin #4's event 2, "login rejected (allowlist / soft-deleted)", is ONE named WARNING
     event with two reasons. `app.services.users.upsert_from_google` ALWAYS reactivates a
     soft-deleted `User` row on a successful Google identity exchange (PRD §4.1, existing,
     deliberate, undisturbed by this task) — so no *login* can ever be rejected FOR being
     soft-deleted; only an ALREADY-established cookie session whose `User` has since been
     soft-deleted can be. This file therefore maps the two reasons to two different, both
     EXISTING, call sites: `app.routes.auth_routes.auth_callback`'s `ForbiddenError` branch
     (reason "allowlist") and `app.auth.deps.require_admin`'s `user is None` branch (reason
     "soft-deleted"). The latter needs the implementer to add a NEW non-`active_select` email
     lookup at that branch (mirroring `bump_session_epoch`'s own precedent of a deliberate
     non-active lookup for a similar administrative purpose) — `get_active_user` alone cannot
     supply the email this event needs, since it excludes the very row being described. Flagged
     for controller/reviewer sign-off; not treated as "unimplementable" (it's ordinary, if
     non-trivial, plumbing), so this is a pinned assumption, not a NEEDS_CONTEXT stop.

  3. The brief authorizes "exact content pins" for the six audit events but gives exact wording
     only for two: event 2's reasons ("allowlist"/"soft-deleted", used here as literal,
     case-insensitive substrings) and event 6's four reasons ("malformed"/"unknown"/"revoked"/
     "inactive-user", ditto). For content it requires but doesn't word (event 4's "whether epoch
     bumped" boolean), this file pins a concrete, greppable rendering as ITS OWN spec, the same
     move `tests/test_metrics.py` makes for its `chat_latency p50=... count=...` line: the
     literal tokens `epoch_bumped=True` / `epoch_bumped=False` must appear in the logout INFO
     record alongside the user id. For content named but not further specified (events 1, 3, 5:
     "email", "no state value logged", "token row id ONLY"), only the named element's
     presence/absence is asserted — exact surrounding phrasing is left to the implementer.

  4. Migration round-trip: the brief says "mirror the `test_lifecycle` migration pattern" /
     "find the actual round-trip precedent via grep for 'downgrade'" — grepped, no hits
     (`tests/test_lifecycle.py`/`tests/test_lifecycle_transitions.py` are content-lifecycle
     tests, not migration tests; no test file anywhere in this repo exercises
     `alembic.command.downgrade`). This file's round-trip test is therefore built directly from
     `tests/conftest.py::tmp_engine`'s own Config-building steps (duplicated locally, since a
     round trip needs to pause at an INTERMEDIATE revision — 0004 — that the shared fixture's
     always-`head` migration never stops at) against its own dedicated throwaway schema, not by
     extending/importing that fixture.

Every DB-touching test below requests `tmp_engine`/`db_session` (skipped by fixture name when
`TEST_DATABASE_URL` is unset per `tests/conftest.py`) except the migration round-trip test, which
manages its own throwaway schema directly (see judgment call #4) and guards itself with an
explicit `pytest.skip` on a missing `TEST_DATABASE_URL`.

`auth_helpers.FakeGoogleOAuthClient`/`login_as`/`begin_login` (both `tests/test_mcp_bearer_auth.py`
and `tests/auth_helpers.py` are sha256-pinned/read-only for this task) are used as-is; every other
helper below (`_build_settings`, `_build_client`, `_fetch_user_by_email`, `_import_mint_script`,
`_begin_login_with_identity`) is duplicated locally rather than shared, matching this repo's own
established precedent (`tests/test_auth_hardening.py`'s module docstring: "kept local here rather
than imported ... same precedent `tests/test_auth_security.py`/`tests/test_auth_callback_redirect
.py` follow").
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sys
from pathlib import Path

import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config
from auth_helpers import FakeGoogleOAuthClient, begin_login, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAME
from app.auth.tokens import mint_token, resolve_bearer_token
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.factory import create_app
from app.models import User
from app.models.api_tokens import ApiToken

_MCP_PATH = "/api/v1/mcp"
_CALLBACK_PATH = "/api/v1/auth/callback"
_LOGOUT_PATH = "/api/v1/auth/logout"
_ME_PATH = "/api/v1/auth/me"
_STATE_COOKIE_NAME = "advisordesk_oauth_state"

# Copied from `test_mcp_bearer_auth.py` (kept local per that file's own no-cross-test-file
# dependency precedent): Streamable HTTP 406s before ever reaching auth/dispatch without both of
# these on `Accept`.
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


# ---------------------------------------------------------------------------
# Local helpers (duplicated rather than shared/imported — see module docstring)
# ---------------------------------------------------------------------------


def _build_settings(
    *, admin_emails: str = "admin@example.com", environment: str = "development"
) -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        environment=environment,
        mcp_http_enabled=True,
    )


def _build_client(
    tmp_engine: Engine,
    *,
    admin_emails: str = "admin@example.com",
    environment: str = "development",
) -> tuple[TestClient, FakeGoogleOAuthClient]:
    """Build a `TestClient` over a real, DB-backed, MCP-HTTP-enabled app with a fake OAuth seam."""
    oauth_client = FakeGoogleOAuthClient()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails, environment=environment),
        oauth_client=oauth_client,
    )
    return TestClient(app), oauth_client


def _fetch_user_by_email(engine: Engine, email: str) -> User | None:
    """Open a short-lived session and return the `User` row for the exact `email` given."""
    session = make_session_factory(engine)()
    try:
        return session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    finally:
        session.close()


def _import_mint_script() -> object:
    """Import `scripts/mint_mcp_token.py` by inserting `scripts/` onto `sys.path` (it is not an
    installed package). Mirrors `tests/test_mcp_bearer_auth.py::_import_mint_script` exactly."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import mint_mcp_token

    return mint_mcp_token


def _begin_login_with_identity(
    client: TestClient, email: str, *, name: str = "Test Identity"
) -> tuple[str, str]:
    """Like `auth_helpers.login_as`, but does NOT assert the callback succeeds — drives only the
    `/auth/login` + fake-identity-registration legs, returning `(code, state)` for a caller that
    wants to drive `/auth/callback` itself and assert a REJECTION (`login_as` always asserts
    success, so it cannot be reused for a non-allowlisted-email negative path)."""
    oauth_client: FakeGoogleOAuthClient = client.app.state.oauth_client  # type: ignore[attr-defined]
    code = secrets.token_urlsafe(16)
    oauth_client.identities[code] = {
        "email": email,
        "name": name,
        "avatar_url": "https://example.com/avatar.png",
    }
    state = begin_login(client)
    return code, state


def _api_tokens_columns(database_url: str, schema: str) -> dict[str, dict[str, object]]:
    """Return `{column_name: column_info}` for `api_tokens` in `schema`, via a fresh inspection
    connection opened and disposed per call, so each round-trip step sees the schema's CURRENT
    state rather than a stale cached reflection."""
    engine = make_engine(database_url, schema=schema)
    try:
        return {column["name"]: column for column in inspect(engine).get_columns("api_tokens")}
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Bullet 1: mint -> resolve OK (epoch match) — guards the backfill/mint path
# ---------------------------------------------------------------------------


def test_resolve_bearer_token_returns_principal_when_token_epoch_matches_user_epoch(
    db_session: Session,
) -> None:
    """Design pin #3: the epoch-compare check must not reject a token stamped with the owner's
    CURRENT `session_epoch` — the ordinary, never-logged-out case. Constructs the `ApiToken` row
    directly (bypassing `scripts/mint_mcp_token.py::mint`, covered separately below) so this test
    isolates PURELY the compare in `resolve_bearer_token`, independent of how the row got its
    `session_epoch` value. RED today: `ApiToken` has no `session_epoch` column, so the
    constructor call below raises `TypeError` (an unexpected keyword argument) — a clean
    behavioral failure, not a collection error."""
    owner = User(email="epoch-match@example.com", name="Epoch Match Owner")
    db_session.add(owner)
    db_session.flush()
    raw, token_hash = mint_token()
    db_session.add(
        ApiToken(
            user_id=owner.id,
            token_hash=token_hash,
            name="epoch-match-token",
            session_epoch=owner.session_epoch,
        )
    )
    db_session.flush()

    principal = resolve_bearer_token(db_session, raw)

    assert principal is not None
    assert principal.user_id == owner.id
    assert principal.email == owner.email


def test_script_mint_stamps_new_token_with_owners_current_session_epoch(
    db_session: Session,
) -> None:
    """Design pin #2: `scripts/mint_mcp_token.py::mint` must stamp the owner's CURRENT
    `session_epoch` on the freshly inserted `ApiToken` row — verified non-trivially by bumping
    the owner to a non-zero epoch (3) BEFORE minting, so a naive `session_epoch=0`
    default/omission would fail this assertion rather than passing it by coincidence. RED today:
    `mint()`'s `ApiToken(...)` construction doesn't pass `session_epoch` at all, so the inserted
    row has no such attribute — `token_row.session_epoch` raises `AttributeError`."""
    mint_mcp_token = _import_mint_script()
    owner = User(email="mint-stamps-epoch@example.com", name="Mint Stamps Epoch")
    db_session.add(owner)
    db_session.flush()
    owner.session_epoch = 3
    db_session.flush()

    raw = mint_mcp_token.mint(db_session, email="mint-stamps-epoch@example.com", name="ci")
    db_session.flush()

    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token_row = db_session.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    ).scalar_one()
    assert token_row.session_epoch == 3


# ---------------------------------------------------------------------------
# Bullet 2: mint -> logout (epoch bump) -> same token now 401; fresh mint works
# ---------------------------------------------------------------------------


def test_bearer_token_dies_after_logout_bumps_epoch_but_fresh_mint_after_logout_works(
    tmp_engine: Engine,
) -> None:
    """The core WR-02 acceptance pin: `/auth/logout` (which bumps `users.session_epoch`) revokes
    EVERY outstanding bearer token for that user, exactly as it already kills cookies — and a
    connector that re-mints after the fact keeps working. Full flow: login (cookie) -> mint a
    bearer token for that SAME user via the real CLI function -> bearer works -> logout via the
    cookie -> the SAME bearer token now 401s -> mint a FRESH token for the same user -> it works.
    """
    mint_mcp_token = _import_mint_script()
    email = "bearer-revocation@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        raw_before = mint_mcp_token.mint(session, email=email, name="pre-logout")
        session.commit()
    finally:
        session.close()

    pre_logout = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw_before}"},
    )
    assert pre_logout.status_code < 400, pre_logout.text

    logout_response = client.post(_LOGOUT_PATH)
    assert logout_response.status_code == 200

    post_logout = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw_before}"},
    )
    assert post_logout.status_code == 401
    assert post_logout.json()["error"]["code"] == "auth_required"

    session = session_factory()
    try:
        raw_after = mint_mcp_token.mint(session, email=email, name="post-logout")
        session.commit()
    finally:
        session.close()

    fresh_response = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw_after}"},
    )
    assert fresh_response.status_code < 400, fresh_response.text


# ---------------------------------------------------------------------------
# Bullet 3: revoked-token rejection is envelope-identical to unknown-token rejection
# ---------------------------------------------------------------------------


def test_revoked_bearer_and_unknown_bearer_return_byte_identical_401_envelope(
    tmp_engine: Engine,
) -> None:
    """Design pin #3's 'no oracle' requirement: a WELL-FORMED-but-revoked bearer token and a
    WELL-FORMED-but-unknown one must be indistinguishable from outside — same status code, same
    exact JSON envelope. Reuses the revocation flow above to produce a genuinely revoked token
    (not just a never-existed one), then compares its 401 body byte-for-byte against a garbage
    token's 401 body."""
    mint_mcp_token = _import_mint_script()
    email = "envelope-parity@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        raw = mint_mcp_token.mint(session, email=email, name="to-be-revoked")
        session.commit()
    finally:
        session.close()

    client.post(_LOGOUT_PATH)  # bumps session_epoch, revoking `raw`

    revoked_response = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw}"},
    )
    unknown_response = client.post(
        _MCP_PATH,
        json=_INITIALIZE_BODY,
        headers={**_MCP_HEADERS, "Authorization": "Bearer adk_totally-unknown-garbage-value"},
    )

    assert revoked_response.status_code == 401
    assert unknown_response.status_code == 401
    assert revoked_response.json() == unknown_response.json()


# ---------------------------------------------------------------------------
# Bullet 4: migration 0005 up/down/up round-trip clean
# ---------------------------------------------------------------------------


def test_migration_0005_session_epoch_column_round_trips_up_down_up() -> None:
    """Design pin #1: migration 0005 (chained after 0004) adds `api_tokens.session_epoch`
    (integer, not null) with a real per-row backfill (each existing row's OWNING user's CURRENT
    `session_epoch` — not a bare constant server default, since the value depends on a join to
    `users`). See module docstring judgment call #4 for why this test manages its own throwaway
    schema rather than reusing/extending `tmp_engine`.

    RED today: revision '0005' does not exist — `upgrade(cfg, "0005")` raises
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
            upgrade(alembic_cfg, "0004")
            assert "session_epoch" not in _api_tokens_columns(database_url, schema)

            upgrade(alembic_cfg, "0005")
            columns = _api_tokens_columns(database_url, schema)
            assert "session_epoch" in columns
            assert columns["session_epoch"]["nullable"] is False

            downgrade(alembic_cfg, "0004")
            assert "session_epoch" not in _api_tokens_columns(database_url, schema)

            upgrade(alembic_cfg, "0005")
            columns = _api_tokens_columns(database_url, schema)
            assert "session_epoch" in columns
            assert columns["session_epoch"]["nullable"] is False
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
# Bullet 5: caplog pins for all six audit events, including never-log assertions
# ---------------------------------------------------------------------------


def test_caplog_login_success_logs_info_with_email(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 1: a successful login logs INFO with the email. Exact wording is the implementer's
    freedom (the brief pins content, not phrasing) — this only requires an INFO-level record
    whose message contains the email that just logged in."""
    email = "login-success-audit@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)

    with caplog.at_level(logging.INFO):
        login_as(client, email)

    matches = [r for r in caplog.records if r.levelno == logging.INFO and email in r.getMessage()]
    assert matches, [r.getMessage() for r in caplog.records]


def test_caplog_login_rejected_non_allowlisted_email_logs_warning_with_allowlist_keyword(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 2 (the 'allowlist' reason, see judgment call #2): a login attempt for an email
    outside `ADMIN_EMAILS` must log WARNING with the email AND the literal reason keyword
    'allowlist' — the brief's own parenthetical vocabulary for this event, mirrored verbatim."""
    client, _ = _build_client(tmp_engine, admin_emails="admin@example.com")
    email = "not-allowlisted@example.com"
    code, state = _begin_login_with_identity(client, email)

    with caplog.at_level(logging.WARNING):
        response = client.get(
            _CALLBACK_PATH, params={"code": code, "state": state}, follow_redirects=False
        )

    assert response.status_code == 403
    matches = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and email in r.getMessage()
        and "allowlist" in r.getMessage().lower()
    ]
    assert matches, [r.getMessage() for r in caplog.records]


def test_caplog_require_admin_rejects_soft_deleted_session_logs_warning_with_soft_deleted_keyword(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 2 (the 'soft-deleted' reason, see judgment call #2): an ALREADY-established session
    whose `User` has since been soft-deleted must 401 at `require_admin` and log WARNING with the
    email AND the literal reason keyword 'soft-deleted'."""
    email = "soft-deleted-session@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)
    owner = _fetch_user_by_email(tmp_engine, email)
    assert owner is not None

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        row = session.get(User, owner.id)
        assert row is not None
        row.is_deleted = True
        session.commit()
    finally:
        session.close()

    with caplog.at_level(logging.WARNING):
        response = client.get(_ME_PATH)

    assert response.status_code == 401
    matches = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and email in r.getMessage()
        and "soft-deleted" in r.getMessage().lower()
    ]
    assert matches, [r.getMessage() for r in caplog.records]


def test_caplog_oauth_state_verification_failed_logs_warning_and_never_logs_state_value(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 3: a forged/mismatched `state` logs WARNING, and — the never-log pin — the state
    VALUE itself must never appear in any captured record. No reason keyword is pinned by the
    brief for this event (unlike events 2 and 6), so only level + never-log are asserted."""
    client, _ = _build_client(tmp_engine)
    forged_state = "forged-state-value-must-never-reach-any-log-line"
    client.cookies.set(_STATE_COOKIE_NAME, forged_state)

    with caplog.at_level(logging.WARNING):
        response = client.get(
            _CALLBACK_PATH,
            params={"code": "unregistered-code", "state": forged_state},
            follow_redirects=False,
        )

    assert response.status_code == 403
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, [r.getMessage() for r in caplog.records]
    assert forged_state not in caplog.text


def test_caplog_logout_logs_info_with_user_id_and_epoch_bumped_flag(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 4: logout logs INFO with the user id AND whether the epoch was bumped. See judgment
    call #3 for why this test pins the literal tokens `epoch_bumped=True`/`epoch_bumped=False` as
    its own concrete rendering of the brief's unworded boolean-content requirement. Exercises
    BOTH values on the SAME cookie: the first logout bumps (True); replaying the now-stale
    (pre-bump) cookie a second time hits `bump_session_epoch`'s own guard (the row already moved
    past that epoch), so the second logout's session data still resolves a user id but does NOT
    bump (False)."""
    email = "logout-audit@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)
    owner = _fetch_user_by_email(tmp_engine, email)
    assert owner is not None
    user_id = str(owner.id)
    stale_cookie = client.cookies.get(COOKIE_NAME)
    assert stale_cookie

    with caplog.at_level(logging.INFO):
        first = client.post(_LOGOUT_PATH)
    assert first.status_code == 200
    bumped_true = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO
        and user_id in r.getMessage()
        and "epoch_bumped=True" in r.getMessage()
    ]
    assert bumped_true, [r.getMessage() for r in caplog.records]

    caplog.clear()
    client.cookies.set(COOKIE_NAME, stale_cookie)
    with caplog.at_level(logging.INFO):
        second = client.post(_LOGOUT_PATH)
    assert second.status_code == 200
    bumped_false = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO
        and user_id in r.getMessage()
        and "epoch_bumped=False" in r.getMessage()
    ]
    assert bumped_false, [r.getMessage() for r in caplog.records]


def test_caplog_bearer_resolved_logs_info_with_token_id_only(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 5: a successfully-resolved bearer token logs INFO with the TOKEN ROW ID only —
    never the raw token, never the owner's email (the 'ONLY' in the brief's own wording). Mints
    via the real CLI path so the id under test is a genuine persisted row id."""
    mint_mcp_token = _import_mint_script()
    email = "bearer-resolved-audit@example.com"
    client, _ = _build_client(tmp_engine)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email=email, name="Bearer Resolved Owner")
        session.add(owner)
        session.commit()
        raw = mint_mcp_token.mint(session, email=email, name="resolved-audit")
        session.commit()
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        token_row = session.execute(
            select(ApiToken).where(ApiToken.token_hash == token_hash)
        ).scalar_one()
        token_id = str(token_row.id)
    finally:
        session.close()

    with caplog.at_level(logging.INFO):
        response = client.post(
            _MCP_PATH,
            json=_INITIALIZE_BODY,
            headers={**_MCP_HEADERS, "Authorization": f"Bearer {raw}"},
        )
    assert response.status_code < 400, response.text

    matches = [
        r for r in caplog.records if r.levelno == logging.INFO and token_id in r.getMessage()
    ]
    assert matches, [r.getMessage() for r in caplog.records]
    for record in matches:
        assert email not in record.getMessage()
    assert raw not in caplog.text


def _assert_bearer_rejected_with_reason(
    client: TestClient,
    headers: dict[str, str],
    reason_keyword: str,
    secret_marker: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Shared assertion body for the four 'bearer rejected' reason-keyword scenarios (event 6):
    401 + `auth_required` envelope, a WARNING record containing `reason_keyword` (one of the
    brief's own four literal words), and `secret_marker` (standing in for whatever the caller
    presented — a raw token or a malformed header value) absent from EVERY captured record."""
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


def test_caplog_bearer_rejected_unknown_token_logs_warning_and_never_logs_token(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 6, reason 'unknown': a syntactically-plausible but unregistered bearer token."""
    client, _ = _build_client(tmp_engine)
    marker = "adk_UNKNOWN-MARKER-" + secrets.token_hex(8)

    _assert_bearer_rejected_with_reason(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {marker}"}, "unknown", marker, caplog
    )


def test_caplog_bearer_rejected_revoked_token_logs_warning_and_never_logs_token(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 6, reason 'revoked': a token whose owner has since logged out (epoch bump)."""
    mint_mcp_token = _import_mint_script()
    email = "bearer-revoked-audit@example.com"
    client, _ = _build_client(tmp_engine, admin_emails=email)
    login_as(client, email)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        raw = mint_mcp_token.mint(session, email=email, name="to-be-revoked-audit")
        session.commit()
    finally:
        session.close()
    client.post(_LOGOUT_PATH)  # bumps session_epoch, revoking `raw`

    _assert_bearer_rejected_with_reason(
        client, {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"}, "revoked", raw, caplog
    )


def test_caplog_bearer_rejected_inactive_user_token_logs_warning_and_never_logs_token(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 6, reason 'inactive-user': a token whose owner has since been soft-deleted."""
    mint_mcp_token = _import_mint_script()
    email = "bearer-inactive-audit@example.com"
    client, _ = _build_client(tmp_engine)

    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        owner = User(email=email, name="Bearer Inactive Owner")
        session.add(owner)
        session.commit()
        raw = mint_mcp_token.mint(session, email=email, name="inactive-owner-audit")
        session.commit()
        owner.is_deleted = True
        session.commit()
    finally:
        session.close()

    _assert_bearer_rejected_with_reason(
        client,
        {**_MCP_HEADERS, "Authorization": f"Bearer {raw}"},
        "inactive-user",
        raw,
        caplog,
    )


def test_caplog_bearer_rejected_malformed_header_logs_warning_and_never_logs_header_value(
    tmp_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Event 6, reason 'malformed': an `Authorization` header present but not a well-formed
    `Bearer` credential (`app.mcp.server._extract_bearer_token`'s existing raise path)."""
    client, _ = _build_client(tmp_engine)
    marker = "MALFORMED-MARKER-" + secrets.token_hex(8)

    _assert_bearer_rejected_with_reason(
        client, {**_MCP_HEADERS, "Authorization": f"Basic {marker}"}, "malformed", marker, caplog
    )
