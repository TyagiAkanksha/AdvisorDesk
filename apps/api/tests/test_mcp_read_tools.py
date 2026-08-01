"""Failing (RED) tests for the MCP in-process seam + the two read tools (task-01 Step 1).

Task brief: docs/plans/phase-5-mcp-agent/task-01-mcp-server-read-tools.md,
Step 1. Everything here goes through `app.mcp.runtime.call_tool` /
`list_tool_schemas` directly (no `TestClient`, no HTTP) — this is exactly
the seam the agent loop (task-03) calls; `tests/test_mcp_exposure.py`
covers the HTTP-exposure rule separately.

`app.mcp.runtime` does not exist yet (only `app/mcp/__init__.py`'s
docstring does), and neither do `ToolNotFoundError`/`ToolInputError` on
`app.services.errors` — every test in this module is expected to fail at
collection with `ModuleNotFoundError: No module named 'app.mcp.runtime'`
(the first import below) until the implementer (a separate agent) creates
`app/mcp/{server,runtime,tools_read}.py` and adds the two error classes to
the family. That `ModuleNotFoundError` IS the RED evidence this file
exists to produce (binding rule 3: this is the anticipated/established
failure mode for a read-tool test file reaching into a not-yet-created
`app.mcp` package).

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when
`TEST_DATABASE_URL` is set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`) — every DB-touching
test here requests `db_session`.
"""

from __future__ import annotations  # noqa: I001 — app.mcp.runtime doesn't exist yet (RED); its
# eventual creation moves it into the first-party block below, where it's placed from the start
# (task brief binding rule 4's documented I001 flip hazard) rather than where ruff's isort would
# put it today (grouped with third-party pytest/sqlalchemy, since it can't yet resolve on disk).

import uuid

import pytest
from sqlalchemy.orm import Session

from app.mcp.runtime import call_tool, list_tool_schemas
from app.models import Content, User
from app.services import content as content_service
from app.services.errors import ToolInputError, ToolNotFoundError
from app.services.lifecycle import NoopChunkPipeline

_TOOL_NAMES = {"search_content", "count_content"}


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` `call_tool` takes (PRD §4.1).

    Mirrors `tests/test_services_content.py::actor_id` and
    `tests/test_routes_content.py`'s builder helpers: kept local rather
    than imported, per this suite's own no-cross-test-file-dependency
    precedent (see that module's docstring).
    """
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


def _seed_status_tag_matrix(session: Session, actor_id: uuid.UUID) -> dict[str, Content]:
    """Build the `count_content` brief's seeded matrix: draft/published/archived x tags,
    plus one soft-deleted row (brief: "a seeded matrix... mix of draft/published/archived x
    tags, with at least one soft-deleted row").

    Active rows (5 total):
      - "draft_tax":               draft,     tags=[tax-planning]
      - "draft_retirement":        draft,     tags=[retirement]
      - "published_tax":           published, tags=[tax-planning]
      - "published_retirement":    published, tags=[retirement]
      - "archived_tax":            archived,  tags=[tax-planning]
    Plus one excluded row:
      - "deleted_draft_tax":       draft, tags=[tax-planning], then soft-deleted

    So: total active = 5; status="draft" -> 2; tag="tax-planning" -> 3;
    status="draft" AND tag="tax-planning" -> 1 (only "draft_tax" — the
    matching soft-deleted row is excluded).
    """
    pipeline = NoopChunkPipeline()
    rows: dict[str, Content] = {}

    rows["draft_tax"] = content_service.create_draft(
        session, title="Draft Tax Item", tags=["tax-planning"], actor_id=actor_id
    )
    rows["draft_retirement"] = content_service.create_draft(
        session, title="Draft Retirement Item", tags=["retirement"], actor_id=actor_id
    )

    published_tax = content_service.create_draft(
        session, title="Published Tax Item", tags=["tax-planning"], actor_id=actor_id
    )
    rows["published_tax"] = content_service.publish_content(
        session, published_tax.id, actor_id=actor_id, pipeline=pipeline
    )

    published_retirement = content_service.create_draft(
        session, title="Published Retirement Item", tags=["retirement"], actor_id=actor_id
    )
    rows["published_retirement"] = content_service.publish_content(
        session, published_retirement.id, actor_id=actor_id, pipeline=pipeline
    )

    archived_tax = content_service.create_draft(
        session, title="Archived Tax Item", tags=["tax-planning"], actor_id=actor_id
    )
    content_service.publish_content(session, archived_tax.id, actor_id=actor_id, pipeline=pipeline)
    rows["archived_tax"] = content_service.archive_content(
        session, archived_tax.id, actor_id=actor_id, pipeline=pipeline
    )

    deleted_tax = content_service.create_draft(
        session, title="Deleted Tax Item", tags=["tax-planning"], actor_id=actor_id
    )
    content_service.delete_content(session, deleted_tax.id, actor_id=actor_id, pipeline=pipeline)
    rows["deleted_draft_tax"] = deleted_tax

    return rows


# ---------------------------------------------------------------------------
# search_content — happy paths
# ---------------------------------------------------------------------------


def test_search_content_finds_by_title_substring(db_session: Session, actor_id: uuid.UUID) -> None:
    """`q` searches by (case-insensitive) title substring (PRD §6)."""
    match = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    content_service.create_draft(db_session, title="529 Plans for Education", actor_id=actor_id)

    result = call_tool("search_content", {"q": "Roth"}, session=db_session, actor_id=actor_id)

    assert [item["id"] for item in result["items"]] == [str(match.id)]
    assert result["count"] == 1
    item = result["items"][0]
    assert set(item.keys()) == {"id", "title", "slug", "status", "tags"}
    assert item["title"] == "Roth IRA Basics"
    assert item["slug"] == "roth-ira-basics"
    assert item["status"] == "draft"
    assert item["tags"] == []


def test_search_content_filters_by_status_and_tag_together(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`status` and `tag` narrow the search together, not just each alone (PRD §6)."""
    pipeline = NoopChunkPipeline()
    content_service.create_draft(
        db_session, title="Draft Tax Item", tags=["tax-planning"], actor_id=actor_id
    )
    content_service.create_draft(
        db_session, title="Draft Retirement Item", tags=["retirement"], actor_id=actor_id
    )
    published_tax = content_service.create_draft(
        db_session, title="Published Tax Item", tags=["tax-planning"], actor_id=actor_id
    )
    content_service.publish_content(
        db_session, published_tax.id, actor_id=actor_id, pipeline=pipeline
    )
    published_retirement = content_service.create_draft(
        db_session, title="Published Retirement Item", tags=["retirement"], actor_id=actor_id
    )
    content_service.publish_content(
        db_session, published_retirement.id, actor_id=actor_id, pipeline=pipeline
    )

    result = call_tool(
        "search_content",
        {"status": "published", "tag": "tax-planning"},
        session=db_session,
        actor_id=actor_id,
    )

    assert [item["id"] for item in result["items"]] == [str(published_tax.id)]
    assert result["count"] == 1


def test_search_content_respects_limit(db_session: Session, actor_id: uuid.UUID) -> None:
    """`limit` bounds the number of items returned (PRD §6, default 10)."""
    for i in range(3):
        content_service.create_draft(db_session, title=f"Limit Item {i}", actor_id=actor_id)

    result = call_tool(
        "search_content", {"q": "Limit Item", "limit": 2}, session=db_session, actor_id=actor_id
    )

    # Only "respects limit" (item-count truncation) is pinned here — whether
    # `count` reflects the truncated item count or the untruncated total
    # match count is genuinely unspecified by the brief/PRD §6 (which only
    # fixes the *shape* `{items, count}`, not this interaction). Left to the
    # implementer; see the test-author report's ambiguity list. Every other
    # test in this file only exercises `count` in scenarios where total
    # matches <= limit, where both readings agree.
    assert len(result["items"]) == 2


def test_search_content_excludes_soft_deleted(db_session: Session, actor_id: uuid.UUID) -> None:
    """§6 pin: a soft-deleted row never appears in `items`, and is not counted."""
    kept = content_service.create_draft(db_session, title="Roth IRA Basics", actor_id=actor_id)
    deleted = content_service.create_draft(db_session, title="Roth 401k Guide", actor_id=actor_id)
    content_service.delete_content(
        db_session, deleted.id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    result = call_tool("search_content", {"q": "Roth"}, session=db_session, actor_id=actor_id)

    ids = [item["id"] for item in result["items"]]
    assert ids == [str(kept.id)]
    assert str(deleted.id) not in ids
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# count_content — happy paths
# ---------------------------------------------------------------------------


def test_count_content_matches_seeded_matrix_with_no_filter(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """No filter counts every active row in the seeded matrix (5), excluding the deleted one."""
    _seed_status_tag_matrix(db_session, actor_id)

    result = call_tool("count_content", {}, session=db_session, actor_id=actor_id)

    assert result == {"count": 5}


def test_count_content_filters_by_status(db_session: Session, actor_id: uuid.UUID) -> None:
    _seed_status_tag_matrix(db_session, actor_id)

    result = call_tool("count_content", {"status": "draft"}, session=db_session, actor_id=actor_id)

    assert result == {"count": 2}


def test_count_content_filters_by_tag(db_session: Session, actor_id: uuid.UUID) -> None:
    _seed_status_tag_matrix(db_session, actor_id)

    result = call_tool(
        "count_content", {"tag": "tax-planning"}, session=db_session, actor_id=actor_id
    )

    assert result == {"count": 3}


def test_count_content_filters_by_status_and_tag_together(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    _seed_status_tag_matrix(db_session, actor_id)

    result = call_tool(
        "count_content",
        {"status": "draft", "tag": "tax-planning"},
        session=db_session,
        actor_id=actor_id,
    )

    assert result == {"count": 1}


def test_count_content_excludes_soft_deleted_row(db_session: Session, actor_id: uuid.UUID) -> None:
    """A dedicated, minimal exclusion pin: one row, soft-deleted, counts as zero."""
    content = content_service.create_draft(db_session, title="To Delete", actor_id=actor_id)
    content_service.delete_content(
        db_session, content.id, actor_id=actor_id, pipeline=NoopChunkPipeline()
    )

    result = call_tool("count_content", {}, session=db_session, actor_id=actor_id)

    assert result == {"count": 0}


# ---------------------------------------------------------------------------
# Failures — §9 floor: one failure path per tool, plus the shared unknown-tool case
# ---------------------------------------------------------------------------


def test_search_content_bad_limit_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`limit="x"` (not an int) -> `ToolInputError` whose message names the `limit` field."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("search_content", {"limit": "x"}, session=db_session, actor_id=actor_id)

    assert "limit" in str(exc_info.value)


def test_count_content_bad_status_type_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`status=123` (not a str) -> `ToolInputError` whose message names the `status` field.

    count_content's own args (`status`, `tag`) are both plain optional
    strings, so `limit="x"`'s "wrong type" shape doesn't apply verbatim;
    this is the closest equivalent bad-arg case for this tool's own
    args model (test-author decision — see report ambiguity list).
    """
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("count_content", {"status": 123}, session=db_session, actor_id=actor_id)

    assert "status" in str(exc_info.value)


def test_call_tool_unknown_name_raises_tool_not_found_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(ToolNotFoundError):
        call_tool("does_not_exist", {}, session=db_session, actor_id=actor_id)


# ---------------------------------------------------------------------------
# list_tool_schemas — lightly pinned (controller decision: don't pin schema internals)
# ---------------------------------------------------------------------------


def test_list_tool_schemas_returns_both_read_tools_with_name_description_and_schema() -> None:
    """Both read tools are present by name, each with a description and *some* JSON-schema-shaped
    field for its args — the exact key/internal shape of that schema field is deliberately not
    pinned here (controller decision: "don't pin exact schema internals — the export script
    formats them"). Needs no DB, so this test alone runs even without `TEST_DATABASE_URL`."""
    schemas = list_tool_schemas()

    assert isinstance(schemas, list)
    by_name = {entry["name"]: entry for entry in schemas}
    assert _TOOL_NAMES <= set(by_name)

    for name in _TOOL_NAMES:
        entry = by_name[name]
        assert isinstance(entry["description"], str) and entry["description"]
        schema_fields = {
            key: value
            for key, value in entry.items()
            if key not in {"name", "description"} and isinstance(value, dict)
        }
        assert schema_fields, f"{name} entry has no dict-shaped JSON-schema field: {entry!r}"
