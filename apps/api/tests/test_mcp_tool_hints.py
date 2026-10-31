"""Failing (RED) tests for MCP tool annotations (vrf t01).

Brief: docs/plans/video-review-fixes/task-01-mcp-tool-annotations.md. Every registered tool must
advertise `readOnlyHint`/`destructiveHint` so hosts (claude.ai) run read tools without asking.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from app.agent.llm import _to_openai_tools
from app.mcp.runtime import list_tool_schemas
from app.mcp.server import _handle_list_tools

# tool -> (readOnlyHint, destructiveHint); exact table from the brief.
_EXPECTED: dict[str, tuple[bool, bool]] = {
    "search_content": (True, False),
    "count_content": (True, False),
    "list_proposals": (True, False),
    "report_content_gaps": (True, False),
    "report_weak_queries": (True, False),
    "delete_content": (False, True),
    "archive": (False, True),
    "edit_content": (False, True),
    "accept_proposal": (False, True),
    "create_draft": (False, False),
    "publish": (False, False),
    "tag_content": (False, False),
    "propose_content_fix": (False, False),
    "reject_proposal": (False, False),
}


def test_every_registered_tool_has_boolean_annotations() -> None:
    schemas = list_tool_schemas()
    assert schemas
    for schema in schemas:
        annotations = schema["annotations"]
        assert isinstance(annotations["readOnlyHint"], bool), schema["name"]
        assert isinstance(annotations["destructiveHint"], bool), schema["name"]


def test_registry_and_table_cover_the_same_tools() -> None:
    """A tool missing from the table (or a stale table row) fails here."""
    assert {s["name"] for s in list_tool_schemas()} == set(_EXPECTED)


@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_tool_annotations_match_the_brief_table(name: str) -> None:
    by_name = {s["name"]: s for s in list_tool_schemas()}
    read_only, destructive = _EXPECTED[name]
    assert by_name[name]["annotations"] == {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
    }


def test_tools_list_over_the_mcp_server_carries_annotations() -> None:
    result = asyncio.run(_handle_list_tools(cast(Any, None), None))
    by_name = {t.name: t for t in result.tools}
    search = by_name["search_content"].annotations
    delete = by_name["delete_content"].annotations
    assert search is not None
    assert search.read_only_hint is True
    assert delete is not None
    assert delete.destructive_hint is True


def test_openai_tool_definitions_do_not_leak_annotations() -> None:
    adapted = _to_openai_tools(list_tool_schemas())
    assert adapted
    for tool in adapted:
        assert "annotations" not in tool
        assert set(tool["function"]) == {"name", "description", "parameters"}
    # Also with annotations explicitly present on the input schema.
    with_ann = [{**s, "annotations": {"readOnlyHint": True}} for s in list_tool_schemas()]
    for tool in _to_openai_tools(with_ann):
        assert "annotations" not in tool
        assert "annotations" not in tool["function"]
