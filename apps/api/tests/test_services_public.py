"""Review-round regression tests for `app.services.content`'s public-read functions.

Phase-3 task-03 review round 1 (`.superpowers/sdd/phase-3/p3-t03-implementer-report.md`,
"Fix round 1"). `tests/test_public_content.py` is sha256-pinned by the test-author agent
and must not change — every new test the review round required lives here instead, one
file per the fix brief's hard rule.

Covers, one section per finding:

- F1 (Important I1): `get_published_by_slug` on a slug containing a NUL byte raises the
  same `NotFoundError`, with the same message shape, as any other not-found slug —
  never reaches Postgres (which would raise `DataError` on a NUL byte in a text
  comparison, previously surfacing as an undeclared, anonymous-accessible 500 on this
  app's only unauthenticated DB-touching route).
- F2 (Minor M1): `list_published_content`'s `Content.id.desc()` tiebreaker is exercised
  under a genuine `published_at` tie (not merely distinct dates, which leaves the
  tiebreaker's removal undetected) — mutation guard.
- F3 (Minor M2): direct service-level contract pins for `list_published_content`
  (published-only, deleted-excluded, ordering) and `get_published_by_slug`
  (published 200-path; draft/archived/deleted/unknown all `NotFoundError`) — the HTTP
  matrix in `test_public_content.py` already covers the route layer; these pin the
  service contract itself for callers (phase-4/5) that may invoke it directly.

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when
`TEST_DATABASE_URL` is set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import make_session_factory
from app.factory import create_app
from app.services import content as content_service
from app.services.errors import NotFoundError
from app.services.lifecycle import NoopChunkPipeline

_UNKNOWN_SLUG = "does-not-exist-slug"


def _build_client(tmp_engine: Engine) -> TestClient:
    """Mirrors `test_public_content.py::_build_client` — no OAuth client, no settings needed."""
    app = create_app(session_factory=make_session_factory(tmp_engine))
    return TestClient(app)


# ---------------------------------------------------------------------------
# F1 (Important I1): NUL-byte slug is a NotFoundError, not a DB error
# ---------------------------------------------------------------------------


def test_get_published_by_slug_nul_byte_raises_not_found_not_db_error(
    db_session: Session,
) -> None:
    """A slug can never legitimately contain a NUL byte (`_slugify` emits `[a-z0-9-]`
    only) — `get_published_by_slug` must short-circuit to `NotFoundError` BEFORE the
    query reaches Postgres, which raises `DataError` (not `NotFoundError`) on a NUL
    byte in a text comparison. This is the service-level half of finding I1; no seed
    data is needed since the guard fires before any query runs.
    """
    with pytest.raises(NotFoundError):
        content_service.get_published_by_slug(db_session, "abc\x00def")


def test_public_content_get_nul_byte_slug_404s_identically_in_shape_to_unknown_slug(
    tmp_engine: Engine,
) -> None:
    """Route-level half of finding I1: `GET /public/content/abc%00def` 404s with the
    typed `not_found` envelope — the SAME shape (`{"error": {"code", "message"}}`,
    same `code`) as a slug that simply never existed, not the undeclared 500 the
    catch-all handler previously produced. No DB seeding needed: neither slug ever
    matches a row, NUL byte or not.
    """
    client = _build_client(tmp_engine)
    nul_slug = "abc\x00def"

    nul_response = client.get("/api/v1/public/content/abc%00def")
    unknown_response = client.get(f"/api/v1/public/content/{_UNKNOWN_SLUG}")

    assert nul_response.status_code == 404, nul_response.text
    assert unknown_response.status_code == 404, unknown_response.text
    nul_body = nul_response.json()
    unknown_body = unknown_response.json()

    # Same envelope shape: top-level keys, `error` sub-keys, and error code.
    assert set(nul_body.keys()) == set(unknown_body.keys()) == {"error"}
    assert set(nul_body["error"].keys()) == set(unknown_body["error"].keys()) == {"code", "message"}
    assert nul_body["error"]["code"] == unknown_body["error"]["code"] == "not_found"

    # Message is the same `f"content slug {slug!r} not found"` construction for both —
    # a pure function of the caller-supplied slug, echoed exactly as received.
    assert nul_body["error"]["message"] == f"content slug {nul_slug!r} not found"
    assert unknown_body["error"]["message"] == f"content slug {_UNKNOWN_SLUG!r} not found"


# ---------------------------------------------------------------------------
# F2 (Minor M1): list_published_content's id-tiebreaker, mutation-guarded
# ---------------------------------------------------------------------------


def test_list_published_content_orders_by_id_desc_on_published_at_ties(
    db_session: Session,
) -> None:
    """Mutation guard: `test_public_content.py`'s own ordering test
    (`test_public_content_list_orders_published_items_newest_first`) uses two
    well-separated `published_at` values, so it stays green even if
    `list_published_content`'s `Content.id.desc()` tiebreaker were deleted — exactly
    the phase-2 `list_content`/`created_at`-tie regression shape
    (`test_services_content_edges.py`'s F1) reproduced for the published-content read
    path. Publishes N items, then stamps them all to the IDENTICAL `published_at` in
    one transaction (mirroring `test_public_content.py`'s
    `_seed_published_pair_with_published_at` override pattern, since two `publish_content`
    calls in the same test process do not naturally tie under wall-clock `now()`), and
    asserts the list order is stable and matches `id` DESC across repeated calls.
    """
    pipeline = NoopChunkPipeline()
    tied_published_at = datetime(2025, 1, 1, tzinfo=UTC)
    items = []
    for i in range(10):
        content = content_service.create_draft(db_session, title=f"Tie Item {i}", actor_id=None)
        content_service.publish_content(db_session, content.id, actor_id=None, pipeline=pipeline)
        content.published_at = tied_published_at
        items.append(content)
    db_session.flush()

    expected_order = sorted((item.id for item in items), reverse=True)

    for _ in range(3):  # repeated calls: order must be stable, not merely correct once
        result = content_service.list_published_content(db_session)
        assert [item.id for item in result] == expected_order


# ---------------------------------------------------------------------------
# F3 (Minor M2): direct service-level contract pins
# ---------------------------------------------------------------------------


def test_list_published_content_returns_only_published_non_deleted(
    db_session: Session,
) -> None:
    """`list_published_content` excludes drafts, archived items, and soft-deleted
    (still `status='published'`) items — only the genuinely published-and-active row
    is returned."""
    pipeline = NoopChunkPipeline()
    content_service.create_draft(db_session, title="Draft", actor_id=None)

    published = content_service.create_draft(db_session, title="Published", actor_id=None)
    content_service.publish_content(db_session, published.id, actor_id=None, pipeline=pipeline)

    archived = content_service.create_draft(db_session, title="Archived", actor_id=None)
    content_service.publish_content(db_session, archived.id, actor_id=None, pipeline=pipeline)
    content_service.archive_content(db_session, archived.id, actor_id=None, pipeline=pipeline)

    deleted = content_service.create_draft(db_session, title="Deleted", actor_id=None)
    content_service.publish_content(db_session, deleted.id, actor_id=None, pipeline=pipeline)
    content_service.delete_content(db_session, deleted.id, actor_id=None, pipeline=pipeline)

    result = content_service.list_published_content(db_session)

    assert [item.id for item in result] == [published.id]


def test_list_published_content_orders_newest_published_first(db_session: Session) -> None:
    """Distinct `published_at` values: newest-published-first ordering (PRD §5.3)."""
    pipeline = NoopChunkPipeline()
    older = content_service.create_draft(db_session, title="Older", actor_id=None)
    content_service.publish_content(db_session, older.id, actor_id=None, pipeline=pipeline)
    older.published_at = datetime(2024, 1, 1, tzinfo=UTC)

    newer = content_service.create_draft(db_session, title="Newer", actor_id=None)
    content_service.publish_content(db_session, newer.id, actor_id=None, pipeline=pipeline)
    newer.published_at = datetime(2025, 1, 1, tzinfo=UTC)
    db_session.flush()

    result = content_service.list_published_content(db_session)

    assert [item.id for item in result] == [newer.id, older.id]


def test_get_published_by_slug_returns_the_published_row(db_session: Session) -> None:
    """The published 200-path: returns the row itself (not just truthy), body_md included."""
    pipeline = NoopChunkPipeline()
    content = content_service.create_draft(
        db_session, title="Roth IRA Basics", body_md="full body", actor_id=None
    )
    content_service.publish_content(db_session, content.id, actor_id=None, pipeline=pipeline)

    result = content_service.get_published_by_slug(db_session, content.slug)

    assert result.id == content.id
    assert result.body_md == "full body"


@pytest.mark.parametrize("state", ["draft", "archived", "deleted", "unknown"])
def test_get_published_by_slug_raises_not_found_for_non_published_and_unknown(
    db_session: Session, state: str
) -> None:
    """A draft's slug, an archived item's slug, a soft-deleted (still `status='published'`)
    item's slug, and a slug that never existed each raise `NotFoundError`."""
    pipeline = NoopChunkPipeline()
    draft = content_service.create_draft(db_session, title="Draft", actor_id=None)

    archived = content_service.create_draft(db_session, title="Archived", actor_id=None)
    content_service.publish_content(db_session, archived.id, actor_id=None, pipeline=pipeline)
    content_service.archive_content(db_session, archived.id, actor_id=None, pipeline=pipeline)

    deleted = content_service.create_draft(db_session, title="Deleted", actor_id=None)
    content_service.publish_content(db_session, deleted.id, actor_id=None, pipeline=pipeline)
    content_service.delete_content(db_session, deleted.id, actor_id=None, pipeline=pipeline)

    slugs = {
        "draft": draft.slug,
        "archived": archived.slug,
        "deleted": deleted.slug,
        "unknown": _UNKNOWN_SLUG,
    }

    with pytest.raises(NotFoundError):
        content_service.get_published_by_slug(db_session, slugs[state])
