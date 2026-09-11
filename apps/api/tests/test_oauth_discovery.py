"""RFC 9728 protected-resource + RFC 8414 authorization-server metadata (DB-less).

docs/plans/mcp-oauth/task-02-discovery-docs.md; docs/plans/mcp-oauth/DESIGN.md
§"Endpoints" (RFC 9728 protected-resource metadata, RFC 8414 authorization-server
metadata). CONVENTIONS.md §5: `create_app()` must succeed with no database and no
env vars — every test here builds the app via `TestClient` with zero fixtures that
touch Postgres.

The helper module `app.auth.oauth_discovery` and the router
`app.routes.discovery_routes` do not exist yet (task 02 is RED at this point), so
the module-level import is deliberately deferred into the one test that needs it
(`test_www_authenticate_challenge_format`) via `importlib.import_module` — this
keeps the whole file collectible so the route-level tests below still run and fail
visibly (404, not a collection error) rather than the entire file being lost to a
single `ModuleNotFoundError` at collection time.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app

_ISSUER = "https://api.example"

_DISCOVERY_ENV = ["MCP_HTTP_ENABLED", "OAUTH_ISSUER_URL"]


@pytest.fixture
def clean_discovery_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the env vars this file's default-`Settings()` test depends on (CONVENTIONS §10).

    hygiene t08 (p8 t13 minor): `test_discovery_available_without_mcp_enabled` asserts the
    zero-env-var defaults; a developer shell exporting `MCP_HTTP_ENABLED=true` (or a custom
    issuer) made it fail for reasons unrelated to the code under test.
    """
    for name in _DISCOVERY_ENV:
        monkeypatch.delenv(name, raising=False)


_EXPECTED_PROTECTED_RESOURCE = {
    "resource": f"{_ISSUER}/api/v1/mcp",
    "authorization_servers": [_ISSUER],
    "scopes_supported": ["mcp"],
    "bearer_methods_supported": ["header"],
    "resource_name": "AdvisorDesk MCP",
}

_EXPECTED_AUTHORIZATION_SERVER = {
    "issuer": _ISSUER,
    "authorization_endpoint": f"{_ISSUER}/api/v1/oauth/authorize",
    "token_endpoint": f"{_ISSUER}/api/v1/oauth/token",
    "registration_endpoint": f"{_ISSUER}/api/v1/oauth/register",
    "revocation_endpoint": f"{_ISSUER}/api/v1/oauth/revoke",
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "code_challenge_methods_supported": ["S256"],
    "token_endpoint_auth_methods_supported": ["none"],
    "revocation_endpoint_auth_methods_supported": ["none"],
    "scopes_supported": ["mcp"],
}


def test_protected_resource_metadata_exact_shape() -> None:
    """GET /.well-known/oauth-protected-resource returns the exact RFC 9728 body."""
    settings = Settings(session_secret="test-secret", oauth_issuer_url=_ISSUER)
    client = TestClient(create_app(settings=settings))

    response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    assert response.json() == _EXPECTED_PROTECTED_RESOURCE
    assert response.json()["resource"] == f"{_ISSUER}/api/v1/mcp"
    assert response.json()["authorization_servers"] == [_ISSUER]


def test_protected_resource_metadata_path_suffixed_form_identical() -> None:
    """RFC 9728 §3.1 path-suffixed form (`/api/v1/mcp`) serves the identical document."""
    settings = Settings(session_secret="test-secret", oauth_issuer_url=_ISSUER)
    client = TestClient(create_app(settings=settings))

    root_response = client.get("/.well-known/oauth-protected-resource")
    suffixed_response = client.get("/.well-known/oauth-protected-resource/api/v1/mcp")

    assert suffixed_response.status_code == 200
    assert suffixed_response.json() == _EXPECTED_PROTECTED_RESOURCE
    assert suffixed_response.content == root_response.content


def test_authorization_server_metadata_exact_shape() -> None:
    """GET /.well-known/oauth-authorization-server returns the exact RFC 8414 body."""
    settings = Settings(session_secret="test-secret", oauth_issuer_url=_ISSUER)
    client = TestClient(create_app(settings=settings))

    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    body = response.json()
    assert body == _EXPECTED_AUTHORIZATION_SERVER
    assert body["issuer"] == _ISSUER
    assert body["code_challenge_methods_supported"] == ["S256"]


def test_discovery_cache_control_header() -> None:
    """All three discovery responses carry `Cache-Control: public, max-age=3600`."""
    settings = Settings(session_secret="test-secret", oauth_issuer_url=_ISSUER)
    client = TestClient(create_app(settings=settings))

    responses = [
        client.get("/.well-known/oauth-protected-resource"),
        client.get("/.well-known/oauth-protected-resource/api/v1/mcp"),
        client.get("/.well-known/oauth-authorization-server"),
    ]

    for response in responses:
        assert response.headers["cache-control"] == "public, max-age=3600"


def test_discovery_available_without_mcp_enabled(clean_discovery_env: None) -> None:
    """Default `Settings()` (MCP disabled) still serves both docs, at the default issuer."""
    settings = Settings()
    assert settings.mcp_http_enabled is False
    client = TestClient(create_app(settings=settings))

    protected_resource_response = client.get("/.well-known/oauth-protected-resource")
    authorization_server_response = client.get("/.well-known/oauth-authorization-server")

    assert protected_resource_response.status_code == 200
    assert protected_resource_response.json() == {
        "resource": "http://localhost:8000/api/v1/mcp",
        "authorization_servers": ["http://localhost:8000"],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
        "resource_name": "AdvisorDesk MCP",
    }
    assert authorization_server_response.status_code == 200
    assert authorization_server_response.json()["issuer"] == "http://localhost:8000"


def test_www_authenticate_challenge_format() -> None:
    """Pure unit: the WWW-Authenticate challenge string task 03 embeds in every MCP 401."""
    oauth_discovery = importlib.import_module("app.auth.oauth_discovery")
    settings = Settings(session_secret="test-secret", oauth_issuer_url=_ISSUER)

    challenge = oauth_discovery.www_authenticate_challenge(settings)

    assert challenge == (
        'Bearer resource_metadata="https://api.example/.well-known/oauth-protected-resource"'
    )


def test_openapi_contains_discovery_operation_ids() -> None:
    """CONVENTIONS.md §5: every route has an explicit, stable `operation_id`."""
    schema = create_app().openapi()

    operation_ids = {
        operation.get("operationId")
        for methods in schema["paths"].values()
        for operation in methods.values()
    }

    assert "oauth_protected_resource_metadata" in operation_ids
    assert "oauth_protected_resource_metadata_mcp_path" in operation_ids
    assert "oauth_authorization_server_metadata" in operation_ids
