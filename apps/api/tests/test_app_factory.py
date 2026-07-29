"""DB-less `create_app()` tests: healthz, error envelope, CORS, OpenAPI baseline (task-03).

CONVENTIONS.md §5: `create_app()` must succeed with no database and no env
vars — every test here builds the app via `TestClient` with zero fixtures
that touch Postgres.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.services.errors import NotFoundError


def test_create_app_with_no_args_succeeds() -> None:
    """CONVENTIONS.md §5: zero DB, zero env vars — `create_app()` still builds an app."""
    app = create_app()

    assert app is not None


def test_healthz_returns_ok_envelope() -> None:
    """PRD §9 / CONVENTIONS.md §5: `GET /api/v1/healthz` needs no auth and no DB."""
    client = TestClient(create_app())

    response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_registered_error_maps_to_exact_envelope() -> None:
    """`register_error_handlers` builds the PRD §9 `{error:{code,message}}` envelope.

    Registers a throwaway probe route on the app under test (not a
    permanent route) purely to exercise `NotFoundError` -> 404 end to end.
    """
    app = create_app()
    probe_router = APIRouter()

    @probe_router.get("/_probe/not-found", operation_id="probe_not_found")
    def _raise_not_found() -> None:
        raise NotFoundError("widget not found")

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/_probe/not-found")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "widget not found"}}


def test_cors_preflight_allows_configured_origin() -> None:
    """PRD §9 CORS: an origin present in `CORS_ORIGINS` gets the ACAO header."""
    settings = Settings(cors_origins="http://a,http://b")
    client = TestClient(create_app(settings=settings))

    response = client.options(
        "/api/v1/healthz",
        headers={"Origin": "http://a", "Access-Control-Request-Method": "GET"},
    )

    assert response.headers["access-control-allow-origin"] == "http://a"


def test_cors_preflight_rejects_unlisted_origin() -> None:
    """PRD §9 CORS: an origin absent from `CORS_ORIGINS` gets no ACAO header."""
    settings = Settings(cors_origins="http://a,http://b")
    client = TestClient(create_app(settings=settings))

    response = client.options(
        "/api/v1/healthz",
        headers={"Origin": "http://unlisted.example", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_openapi_contains_healthz_operation_id() -> None:
    """CONVENTIONS.md §5: every route has an explicit, stable `operation_id`."""
    schema = create_app().openapi()

    operation_ids = {
        operation.get("operationId")
        for methods in schema["paths"].values()
        for operation in methods.values()
    }

    assert "healthz" in operation_ids
