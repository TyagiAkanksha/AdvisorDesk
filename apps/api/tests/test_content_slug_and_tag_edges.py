"""Fixer-owned tests for final-review finding F6 (t02 #5 + t03 whitespace titles).

Degenerate-input edges the phase-2 whole-branch final review carried as
minors: a symbols-only/whitespace-only/unicode-only title slugifies to `""`
(`app.services.content.generate_slug`), a symbols-only tag name normalizes
to `""` (`app.services.tags.get_or_create_tags`), and a whitespace-only
title byte-string passes `ContentCreate`/`ContentUpdate`'s bare
`min_length=1` check. `tests/test_services_content.py`,
`tests/test_services_tags_stats.py`, and `tests/test_routes_content.py` are
test-author-pinned files and are not touched here (CONVENTIONS.md §10) —
this is a fresh, fixer-owned module, mirroring `tests/test_routes_errors.py`'s
own local `Settings`/`TestClient` builder precedent.
"""

from __future__ import annotations

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import Tag
from app.services import content as content_service
from app.services import tags as tags_service


def _build_client(tmp_engine: Engine) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with a fake OAuth seam injected.

    Local to this module, matching `tests/test_routes_errors.py`'s own precedent.
    """
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=Settings(
            session_secret="test-secret",
            google_client_id="test-google-client-id",
            google_client_secret="test-google-client-secret",
            admin_emails="admin@example.com",
        ),
        oauth_client=FakeGoogleOAuthClient(),
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# generate_slug: symbols-only/whitespace-only titles fall back to "untitled"
# ---------------------------------------------------------------------------


def test_generate_slug_falls_back_to_untitled_for_a_symbols_only_title(
    db_session: Session,
) -> None:
    """A title with no `[a-z0-9]` characters at all slugifies to `"untitled"`, not `""`."""
    assert content_service.generate_slug(db_session, "!!!") == "untitled"


def test_generate_slug_untitled_fallback_still_collision_suffixes(db_session: Session) -> None:
    """A second symbols-only title collides on `"untitled"` and gets the same `-2` suffix any
    other slug collision would (PRD §4 slug rules)."""
    first = content_service.create_draft(db_session, title="!!!", actor_id=None)
    assert first.slug == "untitled"

    assert content_service.generate_slug(db_session, "???") == "untitled-2"

    second = content_service.create_draft(db_session, title="???", actor_id=None)
    assert second.slug == "untitled-2"


def test_generate_slug_falls_back_to_untitled_for_a_whitespace_only_title(
    db_session: Session,
) -> None:
    """A whitespace-only title (all stripped away) also falls back to `"untitled"`."""
    assert content_service.generate_slug(db_session, "   ") == "untitled"


# ---------------------------------------------------------------------------
# get_or_create_tags: a symbols-only tag name is skipped, never creates a ""-named Tag
# ---------------------------------------------------------------------------


def test_get_or_create_tags_skips_a_symbols_only_name(db_session: Session) -> None:
    """`["!!!"]` normalizes to `[""]` — no `Tag` row is created for it at all."""
    result = tags_service.get_or_create_tags(db_session, ["!!!"])

    assert result == []


def test_get_or_create_tags_skips_only_the_blank_entries_among_others(
    db_session: Session,
) -> None:
    """A mix of a real name and a symbols-only name creates only the real one."""
    result = tags_service.get_or_create_tags(db_session, ["Tax Planning", "!!!"])

    assert [tag.name for tag in result] == ["tax-planning"]


def test_create_draft_with_only_a_symbols_only_tag_creates_no_tag_row(
    db_session: Session,
) -> None:
    """End-to-end through `create_draft`: a content item created with `tags=["!!!"]` has no
    tags, and no `""`-named `Tag` row exists in the database afterward."""
    content_service.create_draft(db_session, title="Untagged", tags=["!!!"], actor_id=None)

    blank_tag = db_session.execute(select(Tag).where(Tag.name == "")).scalar_one_or_none()
    assert blank_tag is None


# ---------------------------------------------------------------------------
# ContentCreate/ContentUpdate.title: whitespace-only is a 422, not min_length=1's blind spot
# ---------------------------------------------------------------------------


def test_create_content_whitespace_only_title_returns_422(tmp_engine: Engine) -> None:
    """`POST /content` with `title="   "` 422s — `min_length=1` alone would accept this."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")

    response = client.post("/api/v1/content", json={"title": "   ", "body_md": "", "tags": []})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"


def test_update_content_whitespace_only_title_returns_422(tmp_engine: Engine) -> None:
    """`PATCH /content/{id}` with `title="   "` 422s the same way."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    created = client.post(
        "/api/v1/content", json={"title": "Real Title", "body_md": "", "tags": []}
    ).json()

    response = client.patch(f"/api/v1/content/{created['id']}", json={"title": "   "})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"


def test_update_content_omitted_title_is_still_unaffected(tmp_engine: Engine) -> None:
    """Sanity: omitting `title` entirely from a PATCH (leave-untouched) still 200s — the new
    whitespace check only fires when `title` is actually given."""
    client = _build_client(tmp_engine)
    login_as(client, "admin@example.com")
    created = client.post(
        "/api/v1/content", json={"title": "Real Title", "body_md": "old body", "tags": []}
    ).json()

    response = client.patch(f"/api/v1/content/{created['id']}", json={"body_md": "new body"})

    assert response.status_code == 200
    assert response.json()["title"] == "Real Title"
    assert response.json()["body_md"] == "new body"
