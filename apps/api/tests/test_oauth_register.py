"""Failing (RED) tests for `POST /api/v1/oauth/register` — RFC 7591 dynamic client registration
(mcp-oauth plan, task 04).

Task brief: docs/plans/mcp-oauth/task-04-dcr-register.md. Spec: docs/plans/mcp-oauth/DESIGN.md
§"End-to-end flow" step 4 ("Claude -> `POST /register` (DCR) with its `redirect_uris` + name ->
`{ client_id, ... }` (public client, no secret)") and §"Security / threat model" ("DCR is open
per MCP, so cap client creation + prune stale/unused clients"); its Global Constraints
§"Redirect Uris" (exact-match registration rule: `https://...` or `http://localhost|127.0.0.1|
[::1]` any port/path, never a fragment), §"Scope" (`mcp`, absent defaults to `mcp`, anything else
-> `invalid_scope`), §"Token formats" (`client_id = "adkc_" + token_urlsafe(24)`), §"OAuth error
shape", and §"Rate limiting" (`oauth_rate_limit_per_min`, DCR cap `oauth_max_clients`, 24h stale
unused-client pruning); RFC 7591 §3 (the DCR request/response fields and error codes this route
implements); RFC 6749 §5.2 (the error shape every 4xx below renders through `OAuthError`).

Today `POST /api/v1/oauth/register` does not exist at all — `app.factory.create_app` never
includes an `oauth_router`, so every request below 404s (rendered as the existing
`http_404`-coded §9 envelope by `app.routes.errors._http_exception_handler`) instead of
producing the 201/400/422/429 this file pins. No not-yet-existing name is imported at module
level here (`OAuthClient`/`OAuthConsent`/`User` all exist since task 01; request bodies are
built as plain dicts, never through the not-yet-existing `app.models.schemas.oauth` DTOs), so
this file collects cleanly and every test below fails at ASSERTION time, not at collection — see
the test-author report for the literal per-test failure output.

CONVENTIONS.md §10: every test here requests `tmp_engine` (skipped by fixture name when
`TEST_DATABASE_URL` is unset). `_build_app`/`_build_settings` mirror `tests/
test_mcp_www_authenticate.py`'s own `_build_app`/`_build_settings` shape, trimmed to what DCR
registration needs (no Google OAuth client, no admin-cookie login) and pinned to
`oauth_issuer_url="https://api.example"` per the task brief's own test-author instruction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import ApiToken, User
from app.models.oauth import OAuthClient, OAuthConsent, OAuthRefreshToken

_ISSUER = "https://api.example"


def _build_settings(
    *, oauth_max_clients: int = 200, oauth_rate_limit_per_min: int = 30
) -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        oauth_issuer_url=_ISSUER,
        oauth_max_clients=oauth_max_clients,
        oauth_rate_limit_per_min=oauth_rate_limit_per_min,
    )


def _build_app(tmp_engine: Engine, *, settings: Settings | None = None) -> FastAPI:
    """Build a real, DB-backed app — `settings` defaults to `_build_settings()`'s defaults."""
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=settings if settings is not None else _build_settings(),
    )


# ---------------------------------------------------------------------------
# Happy-path shape: 201, RFC 7591 response fields, echoed request fields, DB row.
# ---------------------------------------------------------------------------


def test_register_minimal_returns_201_and_client(tmp_engine: Engine) -> None:
    """A minimal, valid registration returns 201 with every RFC 7591 response field pinned by
    the task brief's Interfaces block, and persists a matching `OAuthClient` row.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "client_name": "Claude",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["client_id"].startswith("adkc_")
    assert isinstance(body["client_id_issued_at"], int)
    assert body["client_name"] == "Claude"
    assert body["redirect_uris"] == ["https://claude.ai/api/mcp/auth_callback"]
    assert body["token_endpoint_auth_method"] == "none"
    assert body["grant_types"] == ["authorization_code", "refresh_token"]
    assert body["response_types"] == ["code"]
    assert body["scope"] == "mcp"

    session_factory = make_session_factory(tmp_engine)
    verify_session = session_factory()
    try:
        row = verify_session.get(OAuthClient, body["client_id"])
        assert row is not None
        assert row.redirect_uris == ["https://claude.ai/api/mcp/auth_callback"]
    finally:
        verify_session.close()


def test_register_ignores_unknown_fields(tmp_engine: Engine) -> None:
    """`ClientRegistrationRequest`'s `extra="ignore"` must let claude.ai's extra DCR fields
    (`client_uri`, `contacts`, an arbitrary `foo`, ...) through without a 422 — the acceptance
    criterion's own "claude.ai's extra DCR fields ... never 422" pin.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "client_name": "Claude",
            "foo": 1,
            "client_uri": "https://claude.ai",
            "contacts": ["ops@claude.ai"],
        },
    )

    assert response.status_code == 201, response.text


def test_register_default_client_name(tmp_engine: Engine) -> None:
    """No `client_name` supplied -> the response's `client_name` defaults to `"Unnamed
    client"` (route ordering block: "Default client_name 'Unnamed client' when absent/blank").
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]},
    )

    assert response.status_code == 201, response.text
    assert response.json()["client_name"] == "Unnamed client"


# ---------------------------------------------------------------------------
# Metadata validation: redirect_uris, redirect-URI shape, auth method, grant/response types,
# scope, client_name length.
# ---------------------------------------------------------------------------


def test_register_requires_redirect_uris(tmp_engine: Engine) -> None:
    """Both a missing `redirect_uris` and an explicitly empty list are `invalid_client_metadata`
    — "required at the ROUTE level" per the DTO's own field comment.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    for body in ({}, {"redirect_uris": []}):
        response = client.post("/api/v1/oauth/register", json=body)
        assert response.status_code == 400, response.text
        assert response.json()["error"] == "invalid_client_metadata"


def test_register_rejects_http_non_localhost(tmp_engine: Engine) -> None:
    """Global Constraints "Redirect Uris": a plain `http://` URI whose host is neither
    `localhost`, `127.0.0.1`, nor `[::1]` is `invalid_redirect_uri`.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register", json={"redirect_uris": ["http://evil.example/cb"]}
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_redirect_uri"


def test_register_accepts_localhost_variants(tmp_engine: Engine) -> None:
    """Global Constraints "Redirect Uris": `http://localhost`, `http://127.0.0.1`, and
    `http://[::1]` are all accepted, at any port/path — the loopback carve-out for a local
    development client.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    for uri in ("http://localhost:3000/cb", "http://127.0.0.1/cb", "http://[::1]:8/cb"):
        response = client.post("/api/v1/oauth/register", json={"redirect_uris": [uri]})
        assert response.status_code == 201, response.text


def test_register_rejects_fragment(tmp_engine: Engine) -> None:
    """Global Constraints "Redirect Uris": "never a fragment" — a `https://` URI with a `#frag`
    component is `invalid_redirect_uri` even though its scheme/host are otherwise fine.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register", json={"redirect_uris": ["https://a.example/cb#frag"]}
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_redirect_uri"


def test_register_rejects_malformed_bracket_authority(tmp_engine: Engine) -> None:
    """Fix round 1, finding I-1: `urlsplit` raises `ValueError` on a bracket-mismatched IPv6
    authority (an unclosed or unopened `[`/`]`) — previously uncaught, so it escaped the route's
    no-`try/except` rule as an unauthenticated 500 instead of a 400. `validate_redirect_uri` now
    catches it and re-raises the same RFC-shaped `invalid_redirect_uri` `OAuthError` every other
    rejection in this module produces (400, RFC body, `Cache-Control: no-store`).
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    for uri in ("http://[::1", "http://localhost]/cb"):
        response = client.post("/api/v1/oauth/register", json={"redirect_uris": [uri]})

        assert response.status_code == 400, response.text
        body = response.json()
        assert body["error"] == "invalid_redirect_uri"
        assert "error_description" in body
        assert response.headers.get("cache-control") == "no-store"


def test_register_rejects_backslash_or_userinfo_redirect_uri(tmp_engine: Engine) -> None:
    """Fix round 1, findings I-2/M-1: a backslash or userinfo (`user[:pass]@`) component in the
    authority is rejected before the host check. `http://evil.example\\@localhost/cb` is a
    Python/WHATWG parser differential — Python's `urlsplit` resolves its host as `localhost`
    (accepting it under the loopback carve-out) while every browser resolves it to `evil.example`
    (a non-loopback, non-TLS destination) — closed by rejecting any backslash or `@` in the
    netloc outright, which also rejects plain userinfo (`http://user:pass@localhost/cb`).
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    for uri in (
        r"http://evil.example\@localhost/cb",  # raw string: one literal backslash, not an escape
        "http://user:pass@localhost/cb",
    ):
        response = client.post("/api/v1/oauth/register", json={"redirect_uris": [uri]})

        assert response.status_code == 400, response.text
        body = response.json()
        assert body["error"] == "invalid_redirect_uri"
        assert "error_description" in body
        assert response.headers.get("cache-control") == "no-store"


def test_register_rejects_empty_fragment(tmp_engine: Engine) -> None:
    """Fix round 1, finding I-3: `https://a.example/cb#` (a lone trailing `#`, no fragment text)
    previously passed the original `if parts.fragment:` truthiness check — `urlsplit(...)
    .fragment == ""` for a bare trailing `#`, even though RFC 6749 §3.1.2's forbidden fragment
    COMPONENT is present. Testing the raw string for `"#"` (not the parsed `.fragment`) catches
    the empty-fragment case `test_register_rejects_fragment` above doesn't exercise.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register", json={"redirect_uris": ["https://a.example/cb#"]}
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "invalid_redirect_uri"
    assert response.headers.get("cache-control") == "no-store"


def test_register_rejects_overlong_redirect_uri(tmp_engine: Engine) -> None:
    """Fix round 1, finding M-2: a single `redirect_uris` entry over
    `app.services.oauth_clients.MAX_REDIRECT_URI_LENGTH` (2000) characters is
    `invalid_redirect_uri` — DCR is an open, unauthenticated endpoint, so an unbounded per-URI
    length is a persisted-size DoS vector against the unbounded `oauth_clients.redirect_uris`
    column.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    base = "https://a.example/cb?x="
    overlong = base + ("a" * (2001 - len(base)))
    assert len(overlong) == 2001

    response = client.post("/api/v1/oauth/register", json={"redirect_uris": [overlong]})

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "invalid_redirect_uri"
    assert response.headers.get("cache-control") == "no-store"


def test_register_rejects_too_many_redirect_uris(tmp_engine: Engine) -> None:
    """Fix round 1, finding M-2: more than `app.services.oauth_clients.MAX_REDIRECT_URIS` (10)
    entries in a single registration is `invalid_redirect_uri` — DCR is an open, unauthenticated
    endpoint, so an unbounded `redirect_uris` list is a persisted-size DoS vector, the same
    rationale as the per-URI length cap above applied to the list as a whole.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    uris = [f"https://a{i}.example/cb" for i in range(11)]

    response = client.post("/api/v1/oauth/register", json={"redirect_uris": uris})

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "invalid_redirect_uri"
    assert response.headers.get("cache-control") == "no-store"


def test_register_rejects_non_none_auth_method(tmp_engine: Engine) -> None:
    """`token_endpoint_auth_method` must be `None` or `"none"` (this is a public client, no
    secret) — any other value is `invalid_client_metadata`.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={
            "redirect_uris": ["https://a.example/cb"],
            "token_endpoint_auth_method": "client_secret_basic",
        },
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_client_metadata"


def test_register_rejects_unknown_grant_type(tmp_engine: Engine) -> None:
    """`grant_types` must be a subset of `{"authorization_code", "refresh_token"}` — `implicit`
    is `invalid_client_metadata`.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://a.example/cb"], "grant_types": ["implicit"]},
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_client_metadata"


def test_register_rejects_unknown_response_type(tmp_engine: Engine) -> None:
    """`response_types` must be a subset of `{"code"}` — `token` is `invalid_client_metadata`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://a.example/cb"], "response_types": ["token"]},
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_client_metadata"


def test_register_rejects_bad_scope(tmp_engine: Engine) -> None:
    """Global Constraints "Scope": anything other than `mcp` (absent is fine, defaults to `mcp`)
    is `invalid_scope`, a DISTINCT RFC 7591 §3 error code from `invalid_client_metadata`.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://a.example/cb"], "scope": "admin"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_scope"


def test_register_rejects_long_name(tmp_engine: Engine) -> None:
    """`client_name` over `ClientRegistrationRequest`'s `max_length=200` fails FastAPI's own
    Pydantic body validation (422), never reaching the route's own `OAuthError` validation —
    status only, per the task brief's own "assert status only" instruction.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://a.example/cb"], "client_name": "x" * 201},
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Cap, pruning, rate limit — the three server-side guards around DCR being open per MCP.
# ---------------------------------------------------------------------------


def test_register_cap_enforced(tmp_engine: Engine) -> None:
    """`oauth_max_clients=2`: two registrations succeed, a third is `invalid_client_metadata`
    with the exact message the route's ordering block pins.
    """
    app = _build_app(tmp_engine, settings=_build_settings(oauth_max_clients=2))
    client = TestClient(app)

    for _ in range(2):
        response = client.post(
            "/api/v1/oauth/register", json={"redirect_uris": ["https://a.example/cb"]}
        )
        assert response.status_code == 201, response.text

    response = client.post(
        "/api/v1/oauth/register", json={"redirect_uris": ["https://a.example/cb"]}
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "invalid_client_metadata"
    assert body["error_description"] == "Too many registered clients; try again later."


def test_register_prunes_stale_unused_clients(tmp_engine: Engine) -> None:
    """`prune_stale_clients` runs on every `/register`: a client older than 24h with no
    consent/api_token/refresh-token rows is deleted, but an equally-stale client that owns an
    `OAuthConsent`, `ApiToken`, or `OAuthRefreshToken` row survives — Global Constraints "Rate
    limiting" ("clients older than 24h with no consent/tokens are pruned") and the Interfaces
    block's own `prune_stale_clients` docstring ("Delete clients with created_at < now - 24h that
    have no oauth_consents, no api_tokens, and no oauth_refresh_tokens rows").

    Fix round 1, finding I-4: the original test pinned only the `oauth_consents` branch of the
    three-way `NOT EXISTS` — the `api_tokens`/`oauth_refresh_tokens` branches were unpinned, the
    worst possible gap given `oauth_clients`' `ondelete="CASCADE"` FKs (a wrong join would delete
    a LIVE client and cascade away its tokens). Extended with a client owning an `ApiToken`
    (`client_id` set) and a client owning an `OAuthRefreshToken`, both equally stale — both must
    survive exactly like the consented one.
    """
    session_factory = make_session_factory(tmp_engine)
    stale_cutoff = datetime.now(UTC) - timedelta(hours=25)

    setup_session = session_factory()
    try:
        unused_client = OAuthClient(
            client_id="adkc_stale_unused",
            client_name="Stale Unused",
            redirect_uris=["https://a.example/cb"],
        )
        unused_client.created_at = stale_cutoff
        setup_session.add(unused_client)

        consented_client = OAuthClient(
            client_id="adkc_stale_consented",
            client_name="Stale Consented",
            redirect_uris=["https://a.example/cb"],
        )
        consented_client.created_at = stale_cutoff
        setup_session.add(consented_client)

        tokened_client = OAuthClient(
            client_id="adkc_stale_tokened",
            client_name="Stale Tokened",
            redirect_uris=["https://a.example/cb"],
        )
        tokened_client.created_at = stale_cutoff
        setup_session.add(tokened_client)

        refreshed_client = OAuthClient(
            client_id="adkc_stale_refreshed",
            client_name="Stale Refreshed",
            redirect_uris=["https://a.example/cb"],
        )
        refreshed_client.created_at = stale_cutoff
        setup_session.add(refreshed_client)
        setup_session.flush()

        owner = User(email="prune-test@example.com", name="Prune Test Owner")
        setup_session.add(owner)
        setup_session.flush()

        setup_session.add(
            OAuthConsent(user_id=owner.id, client_id="adkc_stale_consented", scope="mcp")
        )
        setup_session.add(
            ApiToken(
                user_id=owner.id,
                token_hash="a" * 64,
                name="Stale Tokened Token",
                client_id="adkc_stale_tokened",
            )
        )
        setup_session.add(
            OAuthRefreshToken(
                token_hash="b" * 64,
                client_id="adkc_stale_refreshed",
                user_id=owner.id,
                family_id=uuid.uuid4(),
                resource="https://api.example/api/v1/mcp",
                scope="mcp",
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
        setup_session.commit()
    finally:
        setup_session.close()

    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        "/api/v1/oauth/register", json={"redirect_uris": ["https://fresh.example/cb"]}
    )

    assert response.status_code == 201, response.text

    verify_session = session_factory()
    try:
        assert verify_session.get(OAuthClient, "adkc_stale_unused") is None
        assert verify_session.get(OAuthClient, "adkc_stale_consented") is not None
        assert verify_session.get(OAuthClient, "adkc_stale_tokened") is not None
        assert verify_session.get(OAuthClient, "adkc_stale_refreshed") is not None
    finally:
        verify_session.close()


def test_register_rate_limited(tmp_engine: Engine) -> None:
    """`oauth_rate_limit_per_min=1`: a second `/register` call from the same IP within the same
    minute 429s with the §9 `rate_limited` envelope (NOT the bare OAuthError shape — the rate
    limiter raises `RateLimitedError`, rendered by the pre-existing generic `AppError` handler).
    """
    app = _build_app(tmp_engine, settings=_build_settings(oauth_rate_limit_per_min=1))
    client = TestClient(app)

    first = client.post("/api/v1/oauth/register", json={"redirect_uris": ["https://a.example/cb"]})
    assert first.status_code == 201, first.text

    second = client.post("/api/v1/oauth/register", json={"redirect_uris": ["https://a.example/cb"]})

    assert second.status_code == 429, second.text
    envelope = second.json()
    assert envelope["error"]["code"] == "rate_limited"
    assert isinstance(envelope["error"]["message"], str) and envelope["error"]["message"]


# ---------------------------------------------------------------------------
# Cross-cutting: OAuth error headers, OpenAPI baseline.
# ---------------------------------------------------------------------------


def test_register_error_headers(tmp_engine: Engine) -> None:
    """Any 400 from `/register` carries `Cache-Control: no-store` (the shared OAuthError
    handler's headers), not just the happy-path 201.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post("/api/v1/oauth/register", json={"redirect_uris": []})

    assert response.status_code == 400, response.text
    assert response.headers.get("cache-control") == "no-store"


def test_openapi_has_register_operation(tmp_engine: Engine) -> None:
    """`/openapi.json` lists the `oauth_register` operation — CONVENTIONS.md §5's "every route
    has a stable unique operation_id", codegen-visible for both frontend apps.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    operation_ids = {
        operation.get("operationId")
        for methods in response.json()["paths"].values()
        for operation in methods.values()
    }
    assert "oauth_register" in operation_ids
