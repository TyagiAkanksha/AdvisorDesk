"""Failing (RED) route tests for the admin CMS REST surface (task-03, PRD §5.2).

Task brief: docs/plans/phase-2-auth-cms-crud/task-03-admin-rest-routes.md, Step 1
+ the envelope-completion amendment. `app.routes.content_routes` and
`app.models.schemas.{content,tags,stats,common}` do not exist yet, and
`app.routes.errors::register_error_handlers` does not yet register handlers
for `RequestValidationError`/Starlette's `HTTPException` — every test here is
expected to fail today (404 "not found" from the router, `ModuleNotFoundError`
at collection, or a FastAPI/Starlette-native `{"detail": ...}` body where the
§9 envelope is pinned), not on assertion logic against a working
implementation. That failure IS the RED evidence this file exists to produce.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when
`TEST_DATABASE_URL` is set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`) — every test in this file
requests `tmp_engine`, so the whole module skips cleanly without a DB. The
fake Google OAuth client (`auth_helpers.FakeGoogleOAuthClient`, driven via
`login_as`) is the only mocked collaborator; the `RecordingChunkPipeline`
below is a locally-defined test double for the injectable `ChunkPipeline`
seam (`app.factory.create_app(chunk_pipeline=...)`) — deliberately NOT
imported from `tests/test_services_content.py::FakeChunkPipeline` (brief:
"define your own recording fake") so this file has no cross-test-file
dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import Content

_CONTENT_RESPONSE_FIELDS = {
    "id",
    "title",
    "slug",
    "body_md",
    "status",
    "tags",
    "author_id",
    "updated_by",
    "published_at",
    "created_at",
    "updated_at",
}
_CONTENT_LIST_RESPONSE_FIELDS = {"items", "total", "page", "page_size"}
_TAG_WITH_COUNT_FIELDS = {"id", "name", "count"}
_STATS_RESPONSE_FIELDS = {"by_status", "by_tag"}


@dataclass
class RecordingChunkPipeline:
    """Recording fake matching the `ChunkPipeline` protocol shape (`app.services.lifecycle`).

    `rebuild_chunks(session, content) -> int` / `remove_chunks(session, content_id) -> int` —
    records every call's argument (rather than doing any real chunking/embedding)
    so route tests can assert exactly-once / never-called behavior for the
    publish -> archive -> delete transition flow without depending on the
    real (phase-3) embedding pipeline. Injected via
    `create_app(chunk_pipeline=...)` in `_build_client` below, in place of
    the phase-2 default `NoopChunkPipeline` (which is not observable).
    """

    rebuild_return: int = 0
    remove_return: int = 0
    rebuild_calls: list[uuid.UUID] = field(default_factory=list)
    remove_calls: list[uuid.UUID] = field(default_factory=list)

    def rebuild_chunks(self, session: Session, content: Content) -> int:
        self.rebuild_calls.append(content.id)
        return self.rebuild_return

    def remove_chunks(self, session: Session, content_id: uuid.UUID) -> int:
        self.remove_calls.append(content_id)
        return self.remove_return


def _build_settings(*, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
    )


def _build_client(
    tmp_engine: Engine, *, admin_emails: str = "admin@example.com"
) -> tuple[TestClient, RecordingChunkPipeline]:
    """Build a `TestClient` over a real DB-backed app with fake OAuth + a recording chunk pipeline.

    Mirrors `tests/test_auth_endpoints.py::_build_client` (kept local here,
    per that module's own precedent of not sharing builder helpers across
    test files) with `chunk_pipeline` additionally wired to a
    `RecordingChunkPipeline` so the transition-flow test can assert on it.
    """
    pipeline = RecordingChunkPipeline()
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(admin_emails=admin_emails),
        oauth_client=FakeGoogleOAuthClient(),
        chunk_pipeline=pipeline,
    )
    return TestClient(app), pipeline


def _create_content(
    client: TestClient,
    *,
    title: str = "Sample Content",
    body_md: str = "",
    tags: Sequence[str] | None = None,
) -> dict[str, Any]:
    """POST `/api/v1/content` and return the parsed `ContentResponse` body.

    Asserts 201 eagerly so a failure here (e.g. the route not existing yet,
    RED phase) surfaces at the call site rather than a confusing `KeyError`
    deeper in the calling test.
    """
    response = client.post(
        "/api/v1/content",
        json={"title": title, "body_md": body_md, "tags": list(tags) if tags else []},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 401 matrix — every one of the nine §5.2 admin routes, no session
# ---------------------------------------------------------------------------


def _unauthenticated_route_cases() -> list[tuple[str, str, str, dict[str, str] | None]]:
    """One case per §5.2 admin route (task-03 Interfaces block) — the 401 matrix.

    Returns `(operation_id, method, path, json_body)` tuples. `path` embeds a
    syntactically valid but nonexistent content id so a route that (bug)
    checks existence before auth cannot accidentally return 404 instead of
    401.
    """
    content_id = str(uuid.uuid4())
    return [
        ("content_list", "GET", "/api/v1/content", None),
        ("content_create", "POST", "/api/v1/content", {"title": "Whatever"}),
        ("content_get", "GET", f"/api/v1/content/{content_id}", None),
        ("content_update", "PATCH", f"/api/v1/content/{content_id}", {"title": "Whatever"}),
        ("content_delete", "DELETE", f"/api/v1/content/{content_id}", None),
        ("content_publish", "POST", f"/api/v1/content/{content_id}/publish", None),
        ("content_archive", "POST", f"/api/v1/content/{content_id}/archive", None),
        ("tags_list", "GET", "/api/v1/tags", None),
        ("stats_get", "GET", "/api/v1/stats", None),
    ]


_UNAUTH_ROUTE_CASES = _unauthenticated_route_cases()


@pytest.mark.parametrize(
    "operation_id,method,path,json_body",
    _UNAUTH_ROUTE_CASES,
    ids=[case[0] for case in _UNAUTH_ROUTE_CASES],
)
def test_admin_route_without_session_returns_401_auth_required_envelope(
    tmp_engine: Engine,
    operation_id: str,
    method: str,
    path: str,
    json_body: dict[str, str] | None,
) -> None:
    """PRD §9: every §5.2 admin route 401s with `{"error":{"code":"auth_required",...}}`."""
    client, _ = _build_client(tmp_engine)

    response = client.request(method, path, json=json_body)

    assert response.status_code == 401, (
        f"{operation_id}: {method} {path} -> {response.status_code} {response.text}"
    )
    body = response.json()
    assert body["error"]["code"] == "auth_required"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


# ---------------------------------------------------------------------------
# CRUD happy path: create -> get -> patch -> list
# ---------------------------------------------------------------------------


def test_create_get_patch_list_happy_path(tmp_engine: Engine) -> None:
    """PRD §5.2 Step 1: POST create -> GET by id -> PATCH title/body/tags -> GET list."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    create_response = client.post(
        "/api/v1/content",
        json={"title": "Roth IRA Basics", "body_md": "", "tags": []},
    )

    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert set(created.keys()) == _CONTENT_RESPONSE_FIELDS
    assert created["title"] == "Roth IRA Basics"
    assert created["slug"] == "roth-ira-basics"
    assert created["status"] == "draft"
    assert created["tags"] == []
    assert created["body_md"] == ""
    assert created["published_at"] is None
    assert created["author_id"] is not None
    assert created["updated_by"] == created["author_id"]
    content_id = created["id"]

    get_response = client.get(f"/api/v1/content/{content_id}")
    assert get_response.status_code == 200
    assert get_response.json() == created

    patch_response = client.patch(
        f"/api/v1/content/{content_id}",
        json={
            "title": "Roth IRA Basics (Revised)",
            "body_md": "new body",
            "tags": ["tax-planning", "retirement"],
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert set(patched.keys()) == _CONTENT_RESPONSE_FIELDS
    assert patched["title"] == "Roth IRA Basics (Revised)"
    assert patched["body_md"] == "new body"
    assert patched["slug"] == "roth-ira-basics"  # slug is immutable (PRD §4.1)
    assert patched["tags"] == ["retirement", "tax-planning"]  # sorted alphabetically

    list_response = client.get("/api/v1/content")
    assert list_response.status_code == 200
    listing = list_response.json()
    assert set(listing.keys()) == _CONTENT_LIST_RESPONSE_FIELDS
    assert listing["total"] == 1
    assert listing["page"] == 1
    assert len(listing["items"]) == 1
    listed_item = listing["items"][0]
    assert set(listed_item.keys()) == _CONTENT_RESPONSE_FIELDS
    assert listed_item["id"] == content_id
    assert listed_item["title"] == "Roth IRA Basics (Revised)"


def test_content_response_tags_are_sorted_alphabetically(tmp_engine: Engine) -> None:
    """`ContentResponse.tags` returns tag names sorted alphabetically (`tags_for_contents`)."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    created = _create_content(
        client,
        title="Multi-tag Item",
        tags=["tax-planning", "estate-planning", "retirement"],
    )

    assert created["tags"] == ["estate-planning", "retirement", "tax-planning"]


# ---------------------------------------------------------------------------
# List filters + pagination totals
# ---------------------------------------------------------------------------


def test_list_content_filters_by_status_tag_and_q(tmp_engine: Engine) -> None:
    """PRD §5.2: `status`, `tag`, `q` each narrow the list independently."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    draft = _create_content(client, title="Draft Item", tags=["tax-planning"])
    to_publish = _create_content(client, title="Published Item", tags=["retirement"])
    publish_response = client.post(f"/api/v1/content/{to_publish['id']}/publish")
    assert publish_response.status_code == 200

    status_resp = client.get("/api/v1/content", params={"status": "draft"})
    assert status_resp.status_code == 200
    assert [item["id"] for item in status_resp.json()["items"]] == [draft["id"]]
    assert status_resp.json()["total"] == 1

    tag_resp = client.get("/api/v1/content", params={"tag": "retirement"})
    assert tag_resp.status_code == 200
    assert [item["id"] for item in tag_resp.json()["items"]] == [to_publish["id"]]

    q_resp = client.get("/api/v1/content", params={"q": "draft"})
    assert q_resp.status_code == 200
    assert [item["id"] for item in q_resp.json()["items"]] == [draft["id"]]


def test_list_content_q_omitted_and_q_empty_string_both_return_full_set(
    tmp_engine: Engine,
) -> None:
    """Brief pin: `q` omitted and `q=""` both return the full set — empty string is not a filter."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    first = _create_content(client, title="Roth IRA Basics")
    second = _create_content(client, title="529 Plans")

    omitted_resp = client.get("/api/v1/content")
    empty_q_resp = client.get("/api/v1/content", params={"q": ""})

    assert omitted_resp.status_code == 200
    assert empty_q_resp.status_code == 200
    assert omitted_resp.json()["total"] == 2
    assert empty_q_resp.json()["total"] == 2
    expected_ids = {first["id"], second["id"]}
    assert {item["id"] for item in omitted_resp.json()["items"]} == expected_ids
    assert {item["id"] for item in empty_q_resp.json()["items"]} == expected_ids


def test_list_content_pagination_totals(tmp_engine: Engine) -> None:
    """`page`/`page_size` slice the results; `total` reflects the full filtered count."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    created = [_create_content(client, title=f"Item {i}") for i in range(5)]

    page1 = client.get("/api/v1/content", params={"page": 1, "page_size": 2}).json()
    page2 = client.get("/api/v1/content", params={"page": 2, "page_size": 2}).json()
    page3 = client.get("/api/v1/content", params={"page": 3, "page_size": 2}).json()

    assert page1["total"] == page2["total"] == page3["total"] == 5
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert len(page3["items"]) == 1
    seen_ids = (
        {item["id"] for item in page1["items"]}
        | {item["id"] for item in page2["items"]}
        | {item["id"] for item in page3["items"]}
    )
    assert seen_ids == {c["id"] for c in created}


# ---------------------------------------------------------------------------
# Transition flow: publish -> archive -> delete, observed via the fake pipeline
# ---------------------------------------------------------------------------


def test_publish_archive_delete_transition_flow_via_pipeline(tmp_engine: Engine) -> None:
    """PRD §4/§5.2: publish rebuilds chunks once, archive removes them, delete removes them
    again and returns 204 — the item then vanishes from both the list and stats."""
    client, pipeline = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    content = _create_content(client, title="Transition Item")
    content_id = uuid.UUID(content["id"])

    publish_resp = client.post(f"/api/v1/content/{content['id']}/publish")
    assert publish_resp.status_code == 200
    published = publish_resp.json()
    assert set(published.keys()) == _CONTENT_RESPONSE_FIELDS
    assert published["status"] == "published"
    assert published["published_at"] is not None
    assert pipeline.rebuild_calls == [content_id]
    assert pipeline.remove_calls == []

    archive_resp = client.post(f"/api/v1/content/{content['id']}/archive")
    assert archive_resp.status_code == 200
    archived = archive_resp.json()
    assert archived["status"] == "archived"
    assert pipeline.remove_calls == [content_id]
    assert pipeline.rebuild_calls == [content_id]  # unchanged since publish

    delete_resp = client.delete(f"/api/v1/content/{content['id']}")
    assert delete_resp.status_code == 204
    assert delete_resp.content == b""
    assert pipeline.remove_calls == [content_id, content_id]

    list_resp = client.get("/api/v1/content")
    assert list_resp.status_code == 200
    assert content["id"] not in [item["id"] for item in list_resp.json()["items"]]
    assert list_resp.json()["total"] == 0

    stats_resp = client.get("/api/v1/stats")
    assert stats_resp.status_code == 200
    assert stats_resp.json()["by_status"] == {}


# ---------------------------------------------------------------------------
# Soft-deleted id -> 404 on every by-id operation (PRD §5 blanket rule)
# ---------------------------------------------------------------------------


def test_soft_deleted_content_404s_on_all_by_id_operations(tmp_engine: Engine) -> None:
    """PRD §5 intro: a soft-deleted row 404s on get/patch/publish/archive/delete alike."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    content = _create_content(client, title="To Delete")
    content_id = content["id"]
    delete_resp = client.delete(f"/api/v1/content/{content_id}")
    assert delete_resp.status_code == 204

    cases: list[tuple[str, str, dict[str, str] | None]] = [
        ("GET", f"/api/v1/content/{content_id}", None),
        ("PATCH", f"/api/v1/content/{content_id}", {"title": "New Title"}),
        ("POST", f"/api/v1/content/{content_id}/publish", None),
        ("POST", f"/api/v1/content/{content_id}/archive", None),
        ("DELETE", f"/api/v1/content/{content_id}", None),
    ]
    for method, path, body in cases:
        response = client.request(method, path, json=body)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"
        envelope = response.json()
        assert envelope["error"]["code"] == "not_found"
        assert isinstance(envelope["error"]["message"], str) and envelope["error"]["message"]


def test_get_unknown_content_id_returns_not_found_envelope(tmp_engine: Engine) -> None:
    """Envelope-completion amendment: a valid-UUID, never-existed content id also 404s."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    response = client.get(f"/api/v1/content/{uuid.uuid4()}")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# GET /tags — counts exclude soft-deleted content
# ---------------------------------------------------------------------------


def test_tags_list_returns_counts_excluding_deleted_content(tmp_engine: Engine) -> None:
    """PRD §5.2: `GET /tags` returns non-deleted tags with usage counts over active content only."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    _create_content(client, title="Kept", tags=["tax-planning"])
    deleted = _create_content(client, title="Deleted", tags=["tax-planning"])
    delete_resp = client.delete(f"/api/v1/content/{deleted['id']}")
    assert delete_resp.status_code == 204

    response = client.get("/api/v1/tags")

    assert response.status_code == 200
    tags = response.json()
    assert isinstance(tags, list)
    matching = [t for t in tags if t["name"] == "tax-planning"]
    assert len(matching) == 1
    tag = matching[0]
    assert set(tag.keys()) == _TAG_WITH_COUNT_FIELDS
    assert tag["count"] == 1


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------


def test_stats_returns_by_status_and_by_tag(tmp_engine: Engine) -> None:
    """PRD §5.2: `GET /stats` returns counts by status and by tag."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    _create_content(client, title="Draft Item", tags=["tax-planning"])
    to_publish = _create_content(client, title="Publish Item", tags=["retirement"])
    publish_resp = client.post(f"/api/v1/content/{to_publish['id']}/publish")
    assert publish_resp.status_code == 200

    response = client.get("/api/v1/stats")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == _STATS_RESPONSE_FIELDS
    assert body["by_status"]["draft"] == 1
    assert body["by_status"]["published"] == 1
    assert body["by_tag"]["tax-planning"] == 1
    assert body["by_tag"]["retirement"] == 1


# ---------------------------------------------------------------------------
# Envelope completion (phase-1 final-review decision, task-03 brief amendment)
# ---------------------------------------------------------------------------


def test_create_content_missing_title_returns_validation_error_envelope(
    tmp_engine: Engine,
) -> None:
    """A bad body (missing required `title`) 422s with the §9 envelope, not FastAPI's `detail`."""
    client, _ = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    response = client.post("/api/v1/content", json={"body_md": "no title here"})

    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert "detail" not in body


def test_unknown_path_under_api_v1_returns_http_404_envelope(tmp_engine: Engine) -> None:
    """An unmatched route under `/api/v1` 404s with the §9 envelope (code `http_404`)."""
    client, _ = _build_client(tmp_engine)

    response = client.get("/api/v1/this-route-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "http_404"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert "detail" not in body
