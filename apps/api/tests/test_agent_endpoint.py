"""Failing (RED) tests for `POST /api/v1/agent/chat` (task-03 Step 5).

Task brief: docs/plans/phase-5-mcp-agent/task-03-agent-loop-endpoint.md, Step 5.
Spec: advisordesk-prd.md §5.4 (stateless agent endpoint + the five SSE event shapes), §6 (agent
loop rules), §12 ("server-side persistence of admin agent conversations" — deliberately out of
scope).

RED-mode note (binding rule 3): at the test-author stage, NEITHER `app.agent.loop` (Step 1-4 of
this same task) NOR `app.routes.agent_routes`/the `agent_llm=` factory seam (Step 5-6) exist
yet. `TextDelta`/`ToolCallStep`/`LlmDone` (imported below, top of file, to script the fake LLM)
are defined in `app.agent.loop` — so THIS file, right now, fails at COLLECTION with the same
`ModuleNotFoundError` as `tests/test_agent_loop.py`, not a clean collection. This is expected
and consistent with the brief's own step ordering (Step 3-4 implement `loop.py` BEFORE Step 5-6
touch the endpoint): once the implementer finishes Steps 2-4, this file collects cleanly, and
the REAL RED check for step 6 becomes purely behavioral, per test:
  - `test_agent_chat_without_admin_session_returns_401_auth_required_envelope` and
    `test_agent_chat_route_operation_id_is_agent_chat` never pass `agent_llm=` to `create_app`
    (see `_build_client`'s conditional-forwarding below) — with only `loop.py` done, these two
    hit the router: no `/agent/chat` route yet -> 404 where 401/an `agent_chat` operation id is
    asserted (behavioral RED, not a collection failure).
  - Every other test below passes `agent_llm=...`; `_build_client` forwards it, and today's
    (pre-Step-6) `create_app` doesn't accept that keyword yet -> `TypeError: create_app() got an
    unexpected keyword argument 'agent_llm'`, raised inside the test body (a genuine, informative
    test ERROR, not a hang or a silent skip).
See the test-author report for the ACTUAL RED run captured at this stage (both files failing at
collection).

Idioms: `_parse_sse_events`/`SseEvent` mirror `tests/test_public_chat.py`'s own (PINNED) local
helpers verbatim — no cross-test-file import, per that file's own precedent. `_build_client`/
`_build_settings` mirror `tests/test_routes_content.py`'s admin-auth pattern; `auth_helpers.
login_as` is a SHARED test seam (its own module docstring: "every later admin-route test... "),
unlike the fakes below, which are redefined locally rather than imported from
`tests/test_agent_loop.py` — the same no-cross-test-file-dependency precedent
`tests/test_mcp_write_tools.py` follows for its own `actor_id` fixture.

CONVENTIONS.md §10: every test here requests `tmp_engine`, so the whole module skips cleanly
without a DB (`TEST_DATABASE_URL` unset).
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agent.loop import LlmDone, LlmStep, TextDelta, ToolCallStep
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import ChatMessage, ChatSession, Content, User
from app.services import content as content_service

_ADMIN_EMAIL = "agent-admin@example.com"


# ---------------------------------------------------------------------------
# Fakes: scripted `AgentLLM` + recording `ChunkPipeline` (defined locally — see module
# docstring; field-for-field mirrors of `tests/test_agent_loop.py`'s own copies).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedLlmCall:
    """One recorded `FakeAgentLLM.next_step` call — a deep copy of `messages` plus every
    offered tool schema's name. See `tests/test_agent_loop.py::RecordedLlmCall` for the full
    rationale (kept local here, no cross-test-file import)."""

    messages: list[dict[str, Any]]
    tool_schema_names: tuple[str, ...]


@dataclass
class FakeAgentLLM:
    """Scripted, recording `AgentLLM` fake — see `tests/test_agent_loop.py::FakeAgentLLM` for
    the full rationale (index-based, not reactive; raises loudly if the script runs out)."""

    steps: list[LlmStep]
    calls: list[RecordedLlmCall] = field(default_factory=list)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.calls.append(
            RecordedLlmCall(
                messages=copy.deepcopy(messages),
                tool_schema_names=tuple(schema["name"] for schema in tool_schemas),
            )
        )
        if len(self.calls) > len(self.steps):
            raise AssertionError(
                f"FakeAgentLLM script exhausted after {len(self.steps)} steps but the route "
                f"asked for step #{len(self.calls)}."
            )
        return self.steps[len(self.calls) - 1]


@dataclass
class RecordingChunkPipeline:
    """Recording `ChunkPipeline` fake — see `tests/test_agent_loop.py::RecordingChunkPipeline`,
    itself a mirror of `tests/test_mcp_write_tools.py::RecordingChunkPipeline`."""

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


# ---------------------------------------------------------------------------
# SSE parsing (mirrors `tests/test_public_chat.py::SseEvent`/`_parse_sse_events` verbatim).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SseEvent:
    """One parsed `event: <name>` / `data: <json>` block."""

    name: str
    data: dict[str, Any]


def _parse_sse_events(body: str) -> list[SseEvent]:
    """Strict SSE-body parser — see `tests/test_public_chat.py::_parse_sse_events` for the full
    "why strict" rationale (task-04's admin panel parses this exact shape)."""
    events: list[SseEvent] = []
    blocks = [block for block in body.split("\n\n") if block.strip()]
    for block in blocks:
        lines = [line for line in block.split("\n") if line]
        event_lines = [line for line in lines if line.startswith("event:")]
        data_lines = [line for line in lines if line.startswith("data:")]
        assert len(event_lines) == 1, f"expected exactly one 'event:' line in block {block!r}"
        assert len(data_lines) == 1, f"expected exactly one 'data:' line in block {block!r}"
        name = event_lines[0][len("event:") :].strip()
        raw_data = data_lines[0][len("data:") :].strip()
        events.append(SseEvent(name=name, data=json.loads(raw_data)))
    return events


# ---------------------------------------------------------------------------
# HTTP / app-building helpers.
# ---------------------------------------------------------------------------


def _build_settings() -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=_ADMIN_EMAIL,
    )


def _build_client(
    tmp_engine: Engine,
    *,
    agent_llm: FakeAgentLLM | None = None,
    chunk_pipeline: RecordingChunkPipeline | None = None,
) -> TestClient:
    """Build a `TestClient` over a real DB-backed app with fake OAuth + the agent LLM/pipeline
    seams faked. Mirrors `tests/test_routes_content.py::_build_client`'s admin-auth shape.

    `agent_llm=`/`chunk_pipeline=` are forwarded to `create_app` ONLY when explicitly given
    (not merely defaulted to `None`) — deliberate, see module docstring: today, BEFORE the
    `agent_llm=` factory seam exists, passing that keyword at all raises `TypeError`. Omitting
    it entirely for the two tests that don't need a scripted LLM (the 401 guard,
    the operation-id contract check) keeps their RED mode purely behavioral (404) rather than a
    `TypeError` that has nothing to do with what they're actually testing.
    """
    kwargs: dict[str, Any] = {
        "session_factory": make_session_factory(tmp_engine),
        "settings": _build_settings(),
        "oauth_client": FakeGoogleOAuthClient(),
    }
    if agent_llm is not None:
        kwargs["agent_llm"] = agent_llm
    if chunk_pipeline is not None:
        kwargs["chunk_pipeline"] = chunk_pipeline
    app = create_app(**kwargs)
    return TestClient(app)


def _post_agent_chat(client: TestClient, body: dict[str, Any]) -> tuple[int, str, str]:
    """POST `/api/v1/agent/chat` via the streaming interface; return (status, content_type, body).

    Uses `client.stream(...)` (not a plain `.post()`), mirroring
    `tests/test_public_chat.py::_post_chat`, so the streaming code path is actually exercised —
    and works identically for a non-streamed (e.g. 401 JSON) response too.
    """
    with client.stream("POST", "/api/v1/agent/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


# ---------------------------------------------------------------------------
# 1. Admin gate (brief Step-5 bullet 1; PRD §9).
# ---------------------------------------------------------------------------


def test_agent_chat_without_admin_session_returns_401_auth_required_envelope(
    tmp_engine: Engine,
) -> None:
    """PRD §9/§5.4: `/agent/chat` is admin-gated — no session cookie -> 401 with the §9
    envelope."""
    client = _build_client(tmp_engine)

    status, _content_type, body = _post_agent_chat(
        client, {"messages": [{"role": "user", "content": "What can you do?"}]}
    )

    assert status == 401, body
    payload = json.loads(body)
    assert payload["error"]["code"] == "auth_required"
    assert isinstance(payload["error"]["message"], str) and payload["error"]["message"]


# ---------------------------------------------------------------------------
# 2. SSE event sequence matches the loop (brief Step-5 bullet 2; PRD §5.4).
# ---------------------------------------------------------------------------


def test_agent_chat_admin_streams_events_in_execution_order_matching_the_loop(
    tmp_engine: Engine,
) -> None:
    """PRD §5.4: an authenticated exchange streams the loop's own event sequence over SSE,
    with the exact §5.4 wire shapes: `token{text}`, `tool_call{tool,arguments}`,
    `tool_result{tool,result_summary}`, `done{tool_calls:[...]}`."""
    llm = FakeAgentLLM(
        steps=[
            TextDelta("Drafting now. "),
            ToolCallStep("create_draft", {"title": "Roth IRA Basics", "body_md": "body"}),
            TextDelta("Done."),
            LlmDone(),
        ]
    )
    client = _build_client(tmp_engine, agent_llm=llm)
    login_as(client, _ADMIN_EMAIL)

    status, content_type, body = _post_agent_chat(
        client, {"messages": [{"role": "user", "content": "Draft an article on Roth IRAs."}]}
    )

    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type
    events = _parse_sse_events(body)
    names = [event.name for event in events]
    assert names == ["token", "tool_call", "tool_result", "token", "done"]

    assert events[0].data == {"text": "Drafting now. "}
    assert events[1].data["tool"] == "create_draft"
    assert events[1].data["arguments"] == {"title": "Roth IRA Basics", "body_md": "body"}
    assert events[2].data["tool"] == "create_draft"
    result_summary = events[2].data["result_summary"]
    assert isinstance(result_summary, str) and result_summary
    assert events[3].data == {"text": "Done."}

    done_data = events[4].data
    assert isinstance(done_data["tool_calls"], list)
    assert len(done_data["tool_calls"]) == 1
    assert done_data["tool_calls"][0]["tool"] == "create_draft"


# ---------------------------------------------------------------------------
# 3. History resent reaches the LLM verbatim (brief Step-5 bullet 4; PRD §5.4).
# ---------------------------------------------------------------------------


def test_agent_chat_resent_history_reaches_the_llm_verbatim(tmp_engine: Engine) -> None:
    """PRD §5.4: the admin frontend holds conversation history in component state and resends
    it each request — the loop must pass that history through to the model UNCHANGED (as a
    trailing, exact-order, exact-content suffix — a leading system-prompt message may precede
    it, per the loop's own system-prompt pin)."""
    llm = FakeAgentLLM(steps=[TextDelta("Sure — here's a summary."), LlmDone()])
    client = _build_client(tmp_engine, agent_llm=llm)
    login_as(client, _ADMIN_EMAIL)
    history = [
        {"role": "user", "content": "What tools can you use?"},
        {"role": "assistant", "content": "I can create, edit, and publish CMS content."},
        {"role": "user", "content": "Summarize that."},
    ]

    status, _content_type, body = _post_agent_chat(client, {"messages": history})

    assert status == 200, body
    assert len(llm.calls) >= 1
    first_call_messages = llm.calls[0].messages
    assert first_call_messages[-len(history) :] == history


# ---------------------------------------------------------------------------
# 4. Statelessness (brief Step-5 bullet 3; PRD §5.4/§12).
# ---------------------------------------------------------------------------


def test_agent_chat_is_stateless_chat_session_and_message_counts_unchanged(
    tmp_engine: Engine,
) -> None:
    """PRD §5.4/§12: the server persists NOTHING for agent chats — even an exchange that uses a
    CMS write tool must leave `chat_sessions`/`chat_messages` row counts unchanged."""
    llm = FakeAgentLLM(
        steps=[ToolCallStep("create_draft", {"title": "Stateless Check Article"}), LlmDone()]
    )
    client = _build_client(tmp_engine, agent_llm=llm)
    login_as(client, _ADMIN_EMAIL)
    session_factory = make_session_factory(tmp_engine)

    with session_factory() as probe:
        sessions_before = len(probe.execute(select(ChatSession)).scalars().all())
        messages_before = len(probe.execute(select(ChatMessage)).scalars().all())

    status, _content_type, body = _post_agent_chat(
        client, {"messages": [{"role": "user", "content": "Draft an article."}]}
    )

    assert status == 200, body

    with session_factory() as probe:
        sessions_after = len(probe.execute(select(ChatSession)).scalars().all())
        messages_after = len(probe.execute(select(ChatMessage)).scalars().all())

    assert sessions_after == sessions_before
    assert messages_after == messages_before

    # Sanity: the exchange DID actually run the tool (this isn't a vacuous "nothing happened at
    # all" pass) — a `Content` row was created even though no chat row was.
    with session_factory() as probe:
        created = probe.execute(
            select(Content).where(Content.title == "Stateless Check Article")
        ).scalar_one_or_none()
    assert created is not None


# ---------------------------------------------------------------------------
# 5. Pipeline threading via `app.state.chunk_pipeline` (controller pin, t02 amendment).
# ---------------------------------------------------------------------------


def test_agent_chat_threads_the_real_chunk_pipeline_from_app_state(tmp_engine: Engine) -> None:
    """t02 amendment: the route MUST thread `app.state.chunk_pipeline` (the factory-injected
    seam) into the loop's `call_tool` calls — an explicit-instruction publish through the agent
    must run through the SAME pipeline `POST /content/{id}/publish` does, never silently a
    no-op."""
    session_factory = make_session_factory(tmp_engine)
    with session_factory() as seed_session:
        seed_user = User(email="seed-actor@example.com", name="Seed Actor")
        seed_session.add(seed_user)
        seed_session.flush()
        draft = content_service.create_draft(
            seed_session, title="Roth IRA Basics", actor_id=seed_user.id
        )
        draft_id = draft.id
        seed_session.commit()

    pipeline = RecordingChunkPipeline()
    llm = FakeAgentLLM(steps=[ToolCallStep("publish", {"content_id": str(draft_id)}), LlmDone()])
    client = _build_client(tmp_engine, agent_llm=llm, chunk_pipeline=pipeline)
    login_as(client, _ADMIN_EMAIL)

    status, _content_type, body = _post_agent_chat(
        client,
        {"messages": [{"role": "user", "content": "Please publish the Roth IRA Basics draft."}]},
    )

    assert status == 200, body
    assert pipeline.rebuild_calls == [draft_id]


# ---------------------------------------------------------------------------
# 6. `operation_id="agent_chat"` contract (Interfaces block pin).
# ---------------------------------------------------------------------------


def test_agent_chat_route_operation_id_is_agent_chat(tmp_engine: Engine) -> None:
    """Interfaces-block pin: `operation_id="agent_chat"` — both frontend codegens (task-04) key
    off this exact operation id."""
    client = _build_client(tmp_engine)

    schema = client.app.openapi()  # type: ignore[attr-defined]

    operation_ids = {
        operation.get("operationId")
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict)
    }
    assert "agent_chat" in operation_ids
