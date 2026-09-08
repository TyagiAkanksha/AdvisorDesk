"""Failing (RED) tests for the RFC 7591/6749-shaped `OAuthError` family + its handler
(mcp-oauth plan, task 04).

Task brief: docs/plans/mcp-oauth/task-04-dcr-register.md. Spec: docs/plans/mcp-oauth/DESIGN.md
§"Error handling" ("OAuth endpoints return RFC-shaped `{"error": "...", "error_description":
"..."}` with correct status codes") and its Global Constraints §"OAuth error shape" (all
`/api/v1/oauth/*` endpoints answer this bare two-field body, never the rest of the app's nested
`{"error": {"code", "message"}}` §9 envelope, plus `Cache-Control: no-store` + `Pragma:
no-cache`); RFC 6749 §5.2 (the error response shape this handler renders — `error` +
`error_description`); RFC 7591 §3 (the DCR-specific error codes `invalid_client_metadata`/
`invalid_redirect_uri` a later task-04 route raises through this same `OAuthError` type).

Today `app.services.errors.OAuthError` does not exist at all, so every test below fails at
COLLECTION (`ImportError: cannot import name 'OAuthError' from 'app.services.errors'`) —
including `test_app_error_envelope_unchanged`, which never itself raises `OAuthError`: a module
is one import unit, so the single missing name at the top blocks every test in the file from
ever running. This mirrors `tests/test_ratelimit.py`'s own module docstring for its
not-yet-existing `RateLimiter` import — that collection failure IS the RED evidence this file
exists to produce for all four tests; see the test-author report for the literal command output.

CONVENTIONS.md §5 throwaway-route pattern (`tests/test_app_factory.py::
test_registered_error_maps_to_exact_envelope`): each test below registers its own probe route on
a DB-less `create_app()` app purely to exercise one `OAuthError`/`NotFoundError` raise end to end
— never a permanent route.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.services.errors import NotFoundError, OAuthError


def test_oauth_error_renders_rfc_shape() -> None:
    """RFC 6749 §5.2: an `OAuthError` renders as a bare `{"error", "error_description"}` body —
    no `{"error": {"code": ...}}` nesting like the rest of the §9 `AppError` family gets.
    """
    app = create_app(settings=Settings(session_secret="s"))
    probe_router = APIRouter()

    @probe_router.get("/__oauth_err", operation_id="probe_oauth_err")
    def _raise_oauth_error() -> None:
        raise OAuthError("invalid_grant", "bad", status_code=400)

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/__oauth_err")

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_grant", "error_description": "bad"}


def test_oauth_error_no_store_headers() -> None:
    """Global Constraints "OAuth error shape": every OAuth error response carries
    `Cache-Control: no-store` + `Pragma: no-cache` so an intermediary never caches a body that
    can carry sensitive authorization-flow detail.
    """
    app = create_app(settings=Settings(session_secret="s"))
    probe_router = APIRouter()

    @probe_router.get("/__oauth_err", operation_id="probe_oauth_err")
    def _raise_oauth_error() -> None:
        raise OAuthError("invalid_grant", "bad", status_code=400)

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/__oauth_err")

    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("pragma") == "no-cache"


def test_oauth_error_status_code_honoured() -> None:
    """`OAuthError`'s `status_code` kwarg (default 400) is honoured verbatim — RFC 6749 §5.2's
    `invalid_client` case is the one DCR/token error the DESIGN.md error table answers with 401,
    not 400.
    """
    app = create_app(settings=Settings(session_secret="s"))
    probe_router = APIRouter()

    @probe_router.get("/__oauth_err_401", operation_id="probe_oauth_err_401")
    def _raise_oauth_error_401() -> None:
        raise OAuthError("invalid_client", "who", status_code=401)

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/__oauth_err_401")

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_client", "error_description": "who"}


def test_app_error_envelope_unchanged() -> None:
    """Registering the new `OAuthError` handler must not disturb the existing §9 envelope for
    the rest of the `AppError` family: a throwaway route raising `NotFoundError` still renders
    `{"error": {"code": "not_found", "message": "x"}}`, exactly as `tests/test_app_factory.py::
    test_registered_error_maps_to_exact_envelope` already pins — Starlette resolves handlers by
    walking `type(exc).__mro__`, so a new `OAuthError`-specific handler must never shadow the
    generic `AppError` one for an unrelated subtype.
    """
    app = create_app(settings=Settings(session_secret="s"))
    probe_router = APIRouter()

    @probe_router.get("/__not_found", operation_id="probe_not_found_oauth_file")
    def _raise_not_found() -> None:
        raise NotFoundError("x")

    app.include_router(probe_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/__not_found")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "x"}}
