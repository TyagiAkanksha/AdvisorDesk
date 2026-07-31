"""Failing (RED) route tests for the unauthenticated public content API (task-03, PRD §5.3).

Task brief: docs/plans/phase-3-publish-client-content/task-03-public-content-api.md, Step 1.
`app.routes.public_routes`, `app.models.schemas.public`, and
`app.services.content::get_published_by_slug` do not exist yet. This file never imports any of
them directly — it only drives the HTTP surface via `TestClient` — so collection succeeds today
and every test instead fails at the assertion (`GET /api/v1/public/content*` currently 404s with
the framework-native "unmatched route" envelope, code `http_404`, via
`app.routes.errors::_http_exception_handler`, since `app.factory.create_app` does not include a
public router yet) rather than at import time. That failure IS the RED evidence this file exists
to produce.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL` is
set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`) — every test here requests `tmp_engine`
and/or `db_session`, so the whole module skips cleanly without a DB.

No test in this file imports `auth_helpers.login_as` or attaches any cookie to any request — PRD
§5.3's public routes take no session at all; the 200s below are the positive-path proof that
`require_admin` is not wired onto either route (see
`test_public_routes_work_with_no_session_and_are_not_behind_require_admin`).

Seeding is done directly through the real content services (`create_draft`/`publish_content`/
`archive_content`/`delete_content`), never through the admin HTTP routes — those require an
authenticated session this file deliberately never establishes, and the deleted-published state
needs two chained transitions (publish then delete) that are simplest to drive directly.
`NoopChunkPipeline` (the existing phase-2 default, `app.services.lifecycle`) is used throughout:
embeddings are irrelevant to these read-only public routes, so no embedder fake is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import make_session_factory
from app.factory import create_app
from app.models import Content
from app.services import content as content_service
from app.services.lifecycle import NoopChunkPipeline

# §5.3 Interfaces block, pinned verbatim by the brief.
_PUBLIC_SUMMARY_FIELDS = {"title", "slug", "tags", "published_at"}
_PUBLIC_DETAIL_FIELDS = {"title", "slug", "body_md", "tags", "published_at"}

_PUBLISHED_BODY = "Published body content."
_PUBLISHED_TAGS = ["tax-planning", "retirement"]  # deliberately unsorted input
_PUBLISHED_TAGS_SORTED = ["retirement", "tax-planning"]

_UNKNOWN_SLUG = "does-not-exist-slug"


def _build_client(tmp_engine: Engine) -> TestClient:
    """Build a bare `TestClient` over a real DB-backed app — no OAuth client, no settings.

    Deliberately omits `settings`/`oauth_client`/`chunk_pipeline`
    (contrast `test_routes_content.py::_build_client`, which wires a fake
    Google OAuth client for its admin-route login flow): `/public/content*`
    never depends on auth or the chunk pipeline (PRD §5.3, read-only, no
    `require_admin`), so a public-route test has nothing to fake.
    `Settings()`'s zero-env-var defaults (CONVENTIONS.md §5) are exactly
    what's needed here.
    """
    app = create_app(session_factory=make_session_factory(tmp_engine))
    return TestClient(app)


def _seed_visibility_matrix(session: Session) -> dict[str, Content]:
    """Seed one `Content` row per PRD §5.3/§9 visibility state, via the real services.

    - `draft`: created, never published — must never appear on either public route.
    - `published`: created then published, with two tags given in unsorted order (pins
      the route's tag-sorting behavior) and a non-empty body (pins the detail route's
      `body_md`).
    - `archived`: created, published, then archived — no longer `status='published'`,
      must 404/be absent same as draft.
    - `deleted`: created, published, then soft-deleted. §9 public soft-delete pin:
      `delete_content` never touches `status`/`published_at` (PRD §4.1) — this row's
      `status` stays `'published'` with `is_deleted=True`. A route that filters only on
      `status == 'published'` and forgets `is_deleted` would wrongly surface it; that is
      exactly what this fixture exists to catch.

    Commits once at the end so the seeded rows are visible to the `TestClient`'s own,
    independent `Session` (a different connection off the same `tmp_engine`/schema) —
    `app.services.content` functions only `flush()`, never `commit()` (CONVENTIONS.md §3).
    `actor_id=None` throughout, mirroring the seed-script case PRD §4.1 documents
    (`author_id`/`updated_by` nullable) — no `User` row is needed for these tests.
    """
    pipeline = NoopChunkPipeline()

    draft = content_service.create_draft(session, title="Draft Item", actor_id=None)

    published = content_service.create_draft(
        session,
        title="Published Item",
        body_md=_PUBLISHED_BODY,
        tags=_PUBLISHED_TAGS,
        actor_id=None,
    )
    content_service.publish_content(session, published.id, actor_id=None, pipeline=pipeline)

    archived = content_service.create_draft(session, title="Archived Item", actor_id=None)
    content_service.publish_content(session, archived.id, actor_id=None, pipeline=pipeline)
    content_service.archive_content(session, archived.id, actor_id=None, pipeline=pipeline)

    deleted = content_service.create_draft(session, title="Deleted Published Item", actor_id=None)
    content_service.publish_content(session, deleted.id, actor_id=None, pipeline=pipeline)
    content_service.delete_content(session, deleted.id, actor_id=None, pipeline=pipeline)

    session.commit()
    return {"draft": draft, "published": published, "archived": archived, "deleted": deleted}


def _seed_published_pair_with_published_at(
    session: Session, *, older: datetime, newer: datetime
) -> tuple[Content, Content]:
    """Seed two published items with explicit, well-separated `published_at` values.

    Overrides `publish_content`'s own `datetime.now(UTC)` stamp with a direct ORM
    assignment post-publish, so the two rows' relative order is deterministic instead of
    depending on real-clock resolution between two fast successive calls in the same test
    process (both could otherwise tie under `now()`).
    """
    pipeline = NoopChunkPipeline()

    first = content_service.create_draft(session, title="Older Published Item", actor_id=None)
    content_service.publish_content(session, first.id, actor_id=None, pipeline=pipeline)
    first.published_at = older

    second = content_service.create_draft(session, title="Newer Published Item", actor_id=None)
    content_service.publish_content(session, second.id, actor_id=None, pipeline=pipeline)
    second.published_at = newer

    session.flush()
    session.commit()
    return first, second


# ---------------------------------------------------------------------------
# GET /public/content — visibility matrix (list)
# ---------------------------------------------------------------------------


def test_public_content_list_returns_only_the_published_item_with_sorted_tags(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §5.3/§9: the list contains ONLY the published-and-non-deleted item, tags sorted."""
    seeded = _seed_visibility_matrix(db_session)
    client = _build_client(tmp_engine)

    response = client.get("/api/v1/public/content")

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    entry = body[0]
    assert set(entry.keys()) == _PUBLIC_SUMMARY_FIELDS
    assert entry["title"] == "Published Item"
    assert entry["slug"] == seeded["published"].slug
    assert entry["tags"] == _PUBLISHED_TAGS_SORTED
    assert entry["published_at"] is not None


def test_public_content_list_orders_published_items_newest_first(
    tmp_engine: Engine, db_session: Session
) -> None:
    """Resolved ambiguity (test-author judgment call): task-03.md's Interfaces block pins no
    explicit ordering for `GET /public/content` ("Pagination/params: the brief pins none for the
    public list"). Reading PRD §5.3's "list with tags" as a public content feed, the natural
    default is newest-published-first — pinned here. If the controller intends a different order
    (e.g. title, oldest-first), this is the one test that needs revisiting, not a redesign.
    """
    older = datetime(2024, 1, 1, tzinfo=UTC)
    newer = datetime(2025, 6, 1, tzinfo=UTC)
    first, second = _seed_published_pair_with_published_at(db_session, older=older, newer=newer)
    client = _build_client(tmp_engine)

    response = client.get("/api/v1/public/content")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [entry["slug"] for entry in body] == [second.slug, first.slug]


# ---------------------------------------------------------------------------
# GET /public/content/{slug} — visibility matrix (detail)
# ---------------------------------------------------------------------------


def test_public_content_get_returns_full_detail_for_the_published_slug(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §5.3: by-slug detail 200s for the published-and-non-deleted item, exact DTO shape."""
    seeded = _seed_visibility_matrix(db_session)
    client = _build_client(tmp_engine)

    response = client.get(f"/api/v1/public/content/{seeded['published'].slug}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == _PUBLIC_DETAIL_FIELDS
    assert body["title"] == "Published Item"
    assert body["slug"] == seeded["published"].slug
    assert body["body_md"] == _PUBLISHED_BODY
    assert body["tags"] == _PUBLISHED_TAGS_SORTED
    assert body["published_at"] is not None


@pytest.mark.parametrize("state", ["draft", "archived", "deleted", "unknown"])
def test_public_content_get_404s_for_non_published_and_unknown_slugs(
    tmp_engine: Engine, db_session: Session, state: str
) -> None:
    """PRD §5.3: a draft's slug, an archived item's slug, a soft-deleted (still
    `status='published'`) item's slug, and a slug that never existed all 404 with the typed
    `not_found` envelope — a deleted item's slug is never reassigned (PRD §4.1), so it 404s
    forever, not merely until some other item claims it.
    """
    seeded = _seed_visibility_matrix(db_session)
    client = _build_client(tmp_engine)
    slug = seeded[state].slug if state != "unknown" else _UNKNOWN_SLUG

    response = client.get(f"/api/v1/public/content/{slug}")

    assert response.status_code == 404, f"{state}: {response.status_code} {response.text}"
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


# ---------------------------------------------------------------------------
# No-cookie / not-behind-require_admin proof
# ---------------------------------------------------------------------------


def test_public_routes_work_with_no_session_and_are_not_behind_require_admin(
    tmp_engine: Engine, db_session: Session
) -> None:
    """PRD §5.3: `/public/content*` are unauthenticated, unlike every §5.2 admin route
    (`test_routes_content.py`'s 401-without-session matrix). This file never imports
    `auth_helpers.login_as`; `client` below starts with an empty cookie jar and nothing here
    ever populates it — the 200s are the positive-path proof that neither route depends on
    `require_admin`/a session cookie at all.
    """
    seeded = _seed_visibility_matrix(db_session)
    client = _build_client(tmp_engine)
    assert not client.cookies

    list_response = client.get("/api/v1/public/content")
    detail_response = client.get(f"/api/v1/public/content/{seeded['published'].slug}")

    assert list_response.status_code == 200, list_response.text
    assert detail_response.status_code == 200, detail_response.text
