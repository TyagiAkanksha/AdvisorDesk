"""Fixer-owned tests for phase-2 task-03 review round 1 (findings F1-F4).

HARD RULE (fix-round dispatch brief): `tests/test_routes_content.py`,
`tests/test_smoke.py`, and the other test-author-pinned files are never
touched by a fix round. New coverage for review findings lives here
instead — a fresh, fixer-owned module (CONVENTIONS.md §10: unique test-file
basenames), not an extension of any pinned file.

- F1 (`app.routes.errors::_validation_error_handler`): a 422 envelope's
  `message` is rebuilt from `RequestValidationError.errors()` using only
  `loc`+`msg` — never FastAPI 0.140's developer-form `str(exc)`, which
  leaked an absolute source path, the endpoint's stack frame, and the raw
  submitted `input` value verbatim, unauthenticated.
- F2 (`app.models.schemas.common.ErrorEnvelope` + `responses=` on
  `app.routes.content_routes`/`app.routes.auth_routes`): the committed
  `openapi.json` baseline now declares the real `{"error": {"code",
  "message"}}` shape (401/403/404/422 as applicable) instead of FastAPI's
  default validation-error schema, which no longer appears anywhere in the
  document.
- F3 (`app.models.schemas.content.ContentStatus`): `ContentResponse.status`
  and `?status=` are a closed `Literal["draft","published","archived"]`
  union — an unrecognized status value 422s instead of silently listing
  zero rows.
- F4 (`ContentCreate.title`/`ContentUpdate.title`): `Field(min_length=1)` —
  an empty-string title 422s instead of creating/updating a degenerate row.

CONVENTIONS.md §10: tests requesting `tmp_engine` skip cleanly (by fixture
name, `conftest.py`) when `TEST_DATABASE_URL` is unset; the OpenAPI-baseline
test is deliberately DB-less (`app.factory.create_app()` with no args must
succeed with no database, CONVENTIONS.md §5) and always runs. The fake
Google OAuth client (`auth_helpers.FakeGoogleOAuthClient`, driven via
`login_as`) is the only mocked collaborator, mirroring every other route
test module in this suite.
"""

from __future__ import annotations

from typing import Any

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app


def _build_settings() -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails="admin@example.com",
    )


def _build_client(tmp_engine: Engine) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with a fake OAuth seam injected.

    Local to this module (test_routes_content.py's own precedent: builder
    helpers are not shared across test files).
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# F1 — 422 envelope no longer leaks a filesystem path / frame / raw input
# ---------------------------------------------------------------------------


def test_callback_missing_query_params_422_message_has_no_filesystem_leak(
    tmp_engine: Engine,
) -> None:
    """Unauthenticated `GET /auth/callback` with no `code`/`state` 422s without leaking internals.

    Reviewer repro (finding F1): FastAPI 0.140's `str(RequestValidationError)`
    renders its *developer* form — an absolute source path (`/home/...`), the
    endpoint's stack frame (`File "..."`), and the raw submitted input. The
    fixed handler builds `message` from `loc`+`msg` only, so it still names
    *which* fields are missing (both `code` and `state`) without any of that.
    """
    client = _build_client(tmp_engine)

    response = client.get("/api/v1/auth/callback")

    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "validation_error"
    message = body["error"]["message"]
    assert isinstance(message, str) and message
    assert "code" in message
    assert "Field required" in message
    assert "/home/" not in message
    assert 'File "' not in message


def test_create_content_wrong_typed_field_422_message_excludes_the_submitted_value(
    tmp_engine: Engine,
) -> None:
    """`POST /content` with a wrong-typed field 422s without echoing the submitted value back.

    Reviewer repro (finding F1): `{"body_md": {"secret": "s3cr3t-value"}}` —
    `body_md` is typed `str`, so a dict fails validation. The old handler's
    `str(exc)` included `'input': {'secret': 's3cr3t-value'}` verbatim in an
    unauthenticated-adjacent response body; the fixed handler never surfaces
    `input`/`ctx`/`url`, so the sentinel must not appear anywhere in it.
    """
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    sentinel = "s3cr3t-value"

    response = client.post("/api/v1/content", json={"body_md": {"secret": sentinel}})

    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "validation_error"
    message = body["error"]["message"]
    assert isinstance(message, str) and message
    assert sentinel not in message
    assert sentinel not in response.text


# ---------------------------------------------------------------------------
# F2 — openapi.json declares the real envelope, not FastAPI's default
# ---------------------------------------------------------------------------


def test_openapi_baseline_declares_error_envelope_not_the_fastapi_default() -> None:
    """The DB-less OpenAPI document has no FastAPI-default validation-error schema.

    Builds `create_app()` directly (CONVENTIONS.md §5: must succeed with no
    DB/env vars — the same call `scripts/export_openapi.py` makes) rather
    than going through `TestClient`, since this is a schema-shape assertion,
    not an HTTP-behavior one.
    """
    schema: dict[str, Any] = create_app().openapi()

    schema_names = set(schema["components"]["schemas"].keys())
    assert "HTTPValidationError" not in schema_names
    assert "ValidationError" not in schema_names
    assert "ErrorEnvelope" in schema_names
    assert "ErrorDetail" in schema_names

    paths = schema["paths"]
    # A representative sample, not every operation: a list route, a by-id
    # route (gets the extra 404), and the OAuth callback (gets 403 instead
    # of 401, since it has no `require_admin` dependency).
    content_list_responses = paths["/api/v1/content"]["get"]["responses"]
    content_get_responses = paths["/api/v1/content/{content_id}"]["get"]["responses"]
    callback_responses = paths["/api/v1/auth/callback"]["get"]["responses"]

    for responses in (content_list_responses, content_get_responses, callback_responses):
        assert "422" in responses
        assert (
            responses["422"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/ErrorEnvelope"
        )

    assert "401" in content_list_responses
    assert "401" in content_get_responses
    assert "404" in content_get_responses
    assert "401" not in callback_responses
    assert "403" in callback_responses


# ---------------------------------------------------------------------------
# F3 — `?status=` and `ContentResponse.status` are a closed Literal union
# ---------------------------------------------------------------------------


def test_list_content_unrecognized_status_returns_validation_error_envelope(
    tmp_engine: Engine,
) -> None:
    """`?status=bogus` 422s with the §9 envelope (was previously a silent, empty 200)."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    response = client.get("/api/v1/content", params={"status": "bogus"})

    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


# ---------------------------------------------------------------------------
# F4 — degenerate (empty) titles are rejected
# ---------------------------------------------------------------------------


def test_create_content_empty_title_returns_validation_error_envelope(
    tmp_engine: Engine,
) -> None:
    """`POST /content` with `title=""` 422s instead of creating a degenerate row."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    response = client.post("/api/v1/content", json={"title": "", "body_md": "", "tags": []})

    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
