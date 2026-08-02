"""Checkpoint fix, finding L-3 (controller follow-up to L-1): adapter-level argument repair.

A live proof of finding L-1's fix (actionable `ToolInputError` messages + one-retry
self-correction) showed one retry isn't reliably enough against the real pinned model
(`meta/llama-3.1-8b-instruct`, live-verified 2026-08-02): it sometimes regenerates the SAME
string-encoded-array malformation on its retry rather than switching to a real list. Per finding
C-1's own precedent (wire-format translation belongs to the ADAPTER, `app.agent.llm`, not the
loop, not `call_tool`), `app.agent.llm._repair_string_encoded_arguments` now repairs unambiguous
malformations — a string value where the tool's own JSON schema declares an `array`/`object`
property — before the arguments ever reach `call_tool`. `call_tool`, the tools, and the services
stay exactly as strict as before (finding L-1's actionable-error/retry chain is still the safety
net for anything this repair can't confidently fix).

This file is NEW (not a pinned test file) — `tests/test_agent_llm_client.py` is a t03
fix-round file the standing binding rules protect (verified: sha256 first-16
`abc61a26b8db84f4`, unchanged by this commit), so these tests live here instead, following that
file's own documented technique (a real `OpenAICompatibleAgentLLM` against a fake
`httpx.MockTransport` — zero network, real wire behavior) but mirrored/kept local rather than
imported cross-file, per that file's own convention.

Tests:
  (a) Python-repr string (`"['retirement']"`) for an array property -> a real `list` arrives on
      the `ToolCallStep`.
  (b) Quoted-valid-JSON string (`'["retirement"]'`) for an array property -> a real `list`.
  (b2) The same Python-repr repair applies to an OPTIONAL array property declared via `anyOf`
      (the shape Pydantic emits for `X | None`, e.g. the real `edit_content` tool's `tags`) —
      not just a flat top-level `"type"` (the shape `create_draft`'s required `tags` uses).
  (c) A `string`-typed property whose value looks like a JSON array (`body_md`) is left
      UNTOUCHED, even though it "looks" parseable — the schema type gates repair, not a guess.
  (d) An unparseable garbage string for an array property passes through UNCHANGED on the
      `ToolCallStep`, and feeding that same (still-broken) arguments dict into the real
      `call_tool` seam still raises the actionable `ToolInputError` finding L-1 produces — the
      existing strict-validation/self-correction chain is untouched by this fix.
  (e) Object-typed repair analog of (a)/(b) — no real MCP tool currently declares an
      object-typed property, so a synthetic tool schema covers it, per the dispatch's own
      allowance.

CONVENTIONS.md §10: the one test touching `call_tool` (part of (d)) requests `db_session` and is
skipped by fixture name when `TEST_DATABASE_URL` is unset; every other test here needs no DB.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

import httpx
import pytest
from openai import OpenAI
from sqlalchemy.orm import Session

from app.agent.llm import OpenAICompatibleAgentLLM
from app.agent.loop import ToolCallStep
from app.mcp.runtime import call_tool
from app.models import User
from app.services.errors import ToolInputError

# A local, minimal `create_draft`-shaped schema — mirrors the REAL tool's `mcp-tools.json` entry
# closely enough to exercise the repair (required array property `tags`, plain string property
# `body_md`) without importing the real registry (this file's fakes stay self-contained, per
# `tests/test_agent_llm_client.py`'s own local-`_TOOL_SCHEMAS` convention).
_CREATE_DRAFT_SCHEMA = {
    "name": "create_draft",
    "description": "Create a draft CMS content item.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body_md": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    },
}

# A local `edit_content`-shaped schema fragment: `tags` is OPTIONAL, so Pydantic emits it as
# `anyOf: [{"type": "array", ...}, {"type": "null"}]` rather than a flat top-level `"type"` (see
# the real `edit_content` entry in `mcp-tools.json`) — a distinct code path in
# `_schema_declares_type` from `_CREATE_DRAFT_SCHEMA`'s required `tags`.
_EDIT_CONTENT_SCHEMA = {
    "name": "edit_content",
    "description": "Partially update a content item.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "content_id": {"type": "string", "format": "uuid"},
            "tags": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]},
        },
    },
}

# No real MCP tool declares an `object`-typed property today — a synthetic schema covers finding
# L-3's `object` branch (test (e)), per the dispatch's own "if none exists, cover it with a
# synthetic schema" allowance.
_SYNC_METADATA_SCHEMA = {
    "name": "sync_metadata",
    "description": "A synthetic tool (test-only) with an object-typed property.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "content_id": {"type": "string", "format": "uuid"},
            "metadata": {"type": "object"},
        },
    },
}

_TOOL_SCHEMAS = [_CREATE_DRAFT_SCHEMA, _EDIT_CONTENT_SCHEMA, _SYNC_METADATA_SCHEMA]

_MESSAGES = [
    {"role": "system", "content": "SYSTEM PROMPT"},
    {"role": "user", "content": "Draft an article on Roth IRA conversion basics."},
]


def _agent_llm_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> OpenAICompatibleAgentLLM:
    """Build a real `OpenAICompatibleAgentLLM` wired to a fake HTTP transport — no network.

    Mirrors `tests/test_agent_llm_client.py::_agent_llm_with_transport` exactly (kept local, no
    cross-test-file import, per that file's own documented convention)."""
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="test-key",
        base_url="https://fake-provider.example/v1",
        http_client=http_client,
        max_retries=0,
    )
    return OpenAICompatibleAgentLLM(client=client, model="test-agent-model")


def _tool_call_response(name: str, raw_arguments: str) -> httpx.Response:
    """One non-streaming `chat.completion` response with a single tool call whose
    `function.arguments` is the RAW string given (never re-encoded) — lets a test put an
    arbitrary string value inside the arguments JSON object, exactly the shape a provider that
    string-encodes an array argument actually sends on the wire."""
    body = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-agent-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": raw_arguments},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    return httpx.Response(200, json=body)


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — mirrors `tests/test_mcp_read_tools.py::actor_id` (kept local,
    per that file's own no-cross-test-file-dependency precedent)."""
    user = User(email="arg-repair-admin@example.com", name="Arg Repair Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


# ---------------------------------------------------------------------------
# (a) Python-repr string -> real list
# ---------------------------------------------------------------------------


def test_python_repr_array_string_is_repaired_into_a_real_list() -> None:
    """`tags: "['retirement']"` (Python-repr, single-quoted — not valid JSON) is repaired via
    `ast.literal_eval` into a real `list` before `ToolCallStep` is built."""
    raw_arguments = json.dumps({"title": "Roth IRA Basics", "tags": "['retirement']"})

    def handler(request: httpx.Request) -> httpx.Response:
        return _tool_call_response("create_draft", raw_arguments)

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments["tags"] == ["retirement"]
    assert step.arguments["title"] == "Roth IRA Basics"


# ---------------------------------------------------------------------------
# (b) Quoted-valid-JSON string -> real list
# ---------------------------------------------------------------------------


def test_quoted_json_array_string_is_repaired_into_a_real_list() -> None:
    """`tags: '["retirement"]'` (the string's CONTENTS are already valid JSON, just wrapped in
    quotes — the live-proof failure mode) is repaired via `json.loads` into a real `list`."""
    raw_arguments = json.dumps({"title": "Roth IRA Basics", "tags": '["retirement"]'})

    def handler(request: httpx.Request) -> httpx.Response:
        return _tool_call_response("create_draft", raw_arguments)

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments["tags"] == ["retirement"]


def test_quoted_json_array_string_repaired_for_an_optional_anyof_typed_property() -> None:
    """(b2) The same repair applies to an OPTIONAL array property declared via `anyOf` (real
    `edit_content`'s `tags` shape), not just a required property's flat `"type": "array"`."""
    raw_arguments = json.dumps(
        {"content_id": "11111111-1111-1111-1111-111111111111", "tags": '["retirement"]'}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _tool_call_response("edit_content", raw_arguments)

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments["tags"] == ["retirement"]


# ---------------------------------------------------------------------------
# (c) A string-typed property is never touched, even if it looks like JSON.
# ---------------------------------------------------------------------------


def test_string_typed_property_that_looks_like_json_is_left_untouched() -> None:
    """`body_md` is declared `"type": "string"` — even though its value here happens to look
    like a JSON array, the schema-type gate (not a heuristic guess) means it is NEVER inspected
    or repaired. An article body could legitimately contain literal brackets."""
    raw_arguments = json.dumps({"title": "T", "body_md": '["not", "a", "tags", "field"]'})

    def handler(request: httpx.Request) -> httpx.Response:
        return _tool_call_response("create_draft", raw_arguments)

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments["body_md"] == '["not", "a", "tags", "field"]'
    assert isinstance(step.arguments["body_md"], str)


# ---------------------------------------------------------------------------
# (d) Unparseable garbage passes through unchanged; call_tool still raises actionably.
# ---------------------------------------------------------------------------


def test_unparseable_array_string_passes_through_unchanged_on_the_tool_call_step() -> None:
    """Neither `json.loads` nor `ast.literal_eval` can parse `"not a list, just garbage"` — the
    repair makes no change, and the ORIGINAL (still broken) string reaches `ToolCallStep`."""
    raw_arguments = json.dumps({"title": "T", "tags": "not a list, just garbage"})

    def handler(request: httpx.Request) -> httpx.Response:
        return _tool_call_response("create_draft", raw_arguments)

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments["tags"] == "not a list, just garbage"


def test_unparseable_array_string_still_raises_actionable_tool_input_error_via_call_tool(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """The repair's failure mode is a graceful pass-through, not a silent swallow: the SAME
    unrepaired arguments, fed to the real `call_tool` seam, still raise finding L-1's actionable
    `ToolInputError` (field named, list/array indicated, bracketed literal example) — proving
    finding L-3 never weakens `call_tool`'s own strict validation or the retry chain built on
    top of it."""
    arguments = {"title": "Roth IRA Basics", "tags": "not a list, just garbage"}

    with pytest.raises(ToolInputError) as exc_info:
        call_tool("create_draft", arguments, session=db_session, actor_id=actor_id)

    message = str(exc_info.value)
    assert "tags" in message
    assert "list" in message.lower() or "array" in message.lower()
    assert "[" in message and "]" in message


# ---------------------------------------------------------------------------
# (e) Object-typed repair analog (synthetic schema — no real tool has this shape yet).
# ---------------------------------------------------------------------------


def test_python_repr_object_string_is_repaired_into_a_real_dict() -> None:
    """`metadata: "{'source': 'newsletter'}"` (Python-repr, single-quoted dict) against a
    synthetic `object`-typed property is repaired via `ast.literal_eval` into a real `dict`."""
    raw_arguments = json.dumps(
        {
            "content_id": "11111111-1111-1111-1111-111111111111",
            "metadata": "{'source': 'newsletter'}",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _tool_call_response("sync_metadata", raw_arguments)

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments["metadata"] == {"source": "newsletter"}


def test_quoted_json_object_string_is_repaired_into_a_real_dict() -> None:
    """`metadata: '{"source": "newsletter"}'` (contents already valid JSON, wrapped in quotes)
    against the same synthetic `object`-typed property is repaired via `json.loads`."""
    raw_arguments = json.dumps(
        {
            "content_id": "11111111-1111-1111-1111-111111111111",
            "metadata": '{"source": "newsletter"}',
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _tool_call_response("sync_metadata", raw_arguments)

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments["metadata"] == {"source": "newsletter"}
