"""Failing (RED) tests for lifecycle hardening: idempotent publish + guarded archive.

Task brief: docs/plans/phase-5-mcp-agent/task-00-lifecycle-hardening.md, Steps 1
+ 2. Today `app.services.content.publish_content` unconditionally resets
`published_at` and re-calls `pipeline.rebuild_chunks` on every publish
(no idempotent guard for `published`/`archived` -> `publish`), and
`archive_content` has no status guard at all (an already-`archived` or
still-`draft` item can be "archived" again with no error). Every test below
that exercises one of the brief's pinned matrix's illegal/idempotent cells
is expected to FAIL against current code — either an assertion mismatch
(`published_at` differs across calls, an extra pipeline call recorded) or
`pytest.raises(ConflictError)` not raising at all — never a collection or
import error, since `ConflictError` and every function under test already
exist. The tests that pin the matrix's already-legal cells (draft->publish,
published->archive) are expected to PASS today; they stay in this file as a
guard against the implementer over-tightening the new checks.

Step 1 (service layer) mirrors `tests/test_services_content.py`'s
`db_session` + recording-fake-pipeline idiom. Step 2 (route layer) mirrors
`tests/test_routes_content.py`'s authenticated-`TestClient` + §9-envelope
idiom, including that file's own precedent of defining a local recording
fake / client builder rather than importing one from another test module
(no cross-test-file dependency).
"""

from __future__ import annotations

import uuid
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
from app.models import Content, User
from app.services import content as content_service
from app.services.errors import ConflictError


@dataclass
class RecordingChunkPipeline:
    """Recording fake matching the `ChunkPipeline` protocol shape (`app.services.lifecycle`).

    `rebuild_chunks(session, content) -> int` / `remove_chunks(session, content_id) -> int` —
    records every call's argument so tests can assert exactly-once /
    never-called-again behavior across a sequence of transitions, without
    depending on the real (phase-3) embedding pipeline. Shared by both the
    service-level (Step 1) and route-level (Step 2) tests below since both
    live in this one file already — no cross-test-file import needed.
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


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` content-service writes stamp (PRD §4.1)."""
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


# ---------------------------------------------------------------------------
# Step 1: service-layer tests (app.services.content.publish_content / archive_content)
# ---------------------------------------------------------------------------


def test_publish_content_twice_is_idempotent_and_preserves_published_at(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Matrix cell `published -> publish`: idempotent guard — the second publish preserves the
    first call's `published_at` exactly (equality, not approx) and never re-calls the pipeline;
    `rebuild_chunks` is called exactly ONCE across both calls, and the second call still returns
    `status='published'` (brief Step 1, bullet 1)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()

    first = content_service.publish_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )
    published_at_after_first = first.published_at

    second = content_service.publish_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )

    assert second.published_at == published_at_after_first
    assert pipeline.rebuild_calls == [content.id]
    assert second.status == "published"


def test_republish_after_archive_preserves_published_at_and_rebuilds_chunks(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Matrix cell `archived -> publish`: re-publish — `published_at` stays the value stamped on
    the very first publish (the `published_at` rule: stamped iff currently `NULL`, never
    overwritten), but `rebuild_chunks` runs again since archive removed the chunks; `rebuild_calls`
    is `[id, id]` (twice total) and status ends `published` (brief Step 1, bullet 2)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()
    first = content_service.publish_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )
    published_at_after_first = first.published_at
    content_service.archive_content(db_session, content.id, actor_id=actor_id, pipeline=pipeline)

    republished = content_service.publish_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )

    assert republished.published_at == published_at_after_first
    assert republished.status == "published"
    assert pipeline.rebuild_calls == [content.id, content.id]


def test_archive_content_from_draft_raises_conflict_error_and_leaves_row_untouched(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Matrix cell `draft -> archive`: illegal — `ConflictError` whose message names both states
    (current `draft` and the `archive` action/target state), and the row is untouched: `status`
    stays `draft`, no `remove_chunks` call (brief Step 1, bullet 3)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()

    with pytest.raises(ConflictError) as exc_info:
        content_service.archive_content(
            db_session, content.id, actor_id=actor_id, pipeline=pipeline
        )

    message = str(exc_info.value)
    assert "draft" in message
    assert "archiv" in message.lower()
    assert content.status == "draft"
    assert pipeline.remove_calls == []


def test_archive_content_from_archived_raises_conflict_error_and_does_not_remove_chunks_again(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Matrix cell `archived -> archive`: illegal — `ConflictError`, and `remove_chunks` is NOT
    called a second time (no redundant pipeline call on an already-archived item, brief Step 1,
    bullet 4)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()
    content_service.publish_content(db_session, content.id, actor_id=actor_id, pipeline=pipeline)
    content_service.archive_content(db_session, content.id, actor_id=actor_id, pipeline=pipeline)

    with pytest.raises(ConflictError) as exc_info:
        content_service.archive_content(
            db_session, content.id, actor_id=actor_id, pipeline=pipeline
        )

    assert "archiv" in str(exc_info.value).lower()
    assert pipeline.remove_calls == [content.id]


def test_publish_content_from_draft_sets_published_at_once_legal_path_still_passes(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Legal path guard (brief Step 1, bullet 5): matrix cell `draft -> publish` is unchanged —
    still sets `status='published'` + `published_at`, and still calls `rebuild_chunks` exactly
    once. Pinned here too so the new idempotent-publish guard cannot accidentally swallow the
    first, legitimate publish."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()

    published = content_service.publish_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )

    assert published.status == "published"
    assert published.published_at is not None
    assert pipeline.rebuild_calls == [content.id]


def test_archive_content_from_published_removes_chunks_legal_path_still_passes(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Legal path guard (brief Step 1, bullet 5): matrix cell `published -> archive` is
    unchanged — still sets `status='archived'` and still removes chunks. Pinned here too so the
    new archive status guard cannot accidentally reject the one archive transition PRD §2 actually
    wants (`published -> archived`)."""
    content = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    pipeline = RecordingChunkPipeline()
    content_service.publish_content(db_session, content.id, actor_id=actor_id, pipeline=pipeline)

    archived = content_service.archive_content(
        db_session, content.id, actor_id=actor_id, pipeline=pipeline
    )

    assert archived.status == "archived"
    assert pipeline.remove_calls == [content.id]


# ---------------------------------------------------------------------------
# Step 2: route-layer tests (POST /content/{id}/publish, /archive)
# ---------------------------------------------------------------------------


def _build_settings(*, admin_emails: str = "admin@example.com") -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
    )


def _build_client(tmp_engine: Engine) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with fake OAuth.

    Mirrors `tests/test_routes_content.py::_build_client` (kept local here,
    per that module's own precedent of not sharing builder helpers across
    test files) — no `chunk_pipeline` injection needed since Step 2 asserts
    only HTTP status codes and response bodies, not pipeline call counts.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )
    return TestClient(app)


def _create_content(client: TestClient, *, title: str = "Sample Content") -> dict[str, Any]:
    """POST `/api/v1/content` and return the parsed `ContentResponse` body."""
    response = client.post(
        "/api/v1/content",
        json={"title": title, "body_md": "", "tags": []},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_archive_route_on_draft_returns_409_conflict_envelope(tmp_engine: Engine) -> None:
    """Matrix cell `draft -> archive` at the route layer: POST `/content/{id}/archive` on a
    draft -> HTTP 409, body exactly `{"error": {"code": "conflict", "message": ...}}` (brief
    Step 2)."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    content = _create_content(client, title="Draft Item")

    response = client.post(f"/api/v1/content/{content['id']}/archive")

    assert response.status_code == 409
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == "conflict"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_publish_route_twice_returns_200_both_times_with_identical_published_at(
    tmp_engine: Engine,
) -> None:
    """Matrix cell `published -> publish` at the route layer: double POST
    `/content/{id}/publish` -> 200 both times, `published_at` identical in both response bodies
    (brief Step 2)."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    content = _create_content(client, title="Roth IRA Basics")

    first_response = client.post(f"/api/v1/content/{content['id']}/publish")
    second_response = client.post(f"/api/v1/content/{content['id']}/publish")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_body = first_response.json()
    second_body = second_response.json()
    assert first_body["published_at"] is not None
    assert first_body["published_at"] == second_body["published_at"]
