"""New (RED-at-authoring-time, expected-GREEN-on-current-code) HTTP-level error-path tests for
`POST /agent/chat` — the direct analog of `tests/test_public_chat.py`'s (pinned)
`test_llm_failure_mid_stream_emits_error_event_and_still_persists_user_message`.

Task brief: docs/plans/phase-6-remediation/task-08-held-txn-agent-tests-metrics.md, WR-10.

`app/routes/agent_routes.py`'s two failure surfaces have no HTTP-level coverage before this file:

  (a) `run_agent` (`app.agent.loop`) itself turning a real failure into a GRACEFUL `Error`
      AgentEvent (PRD §6: "on a tool error, surface the error to the model once for
      self-correction, then fail gracefully" — a SECOND consecutive tool failure) — which
      `_to_sse_event`'s catch-all fallback branch (`agent_routes.py` ~66, the final `return
      sse_event("error", ...)` for anything that isn't `Token`/`ToolCall`/`ToolResult`/`Done`)
      renders onto the wire.
  (b) an exception `run_agent` does NOT itself catch (a bug, or a real `AgentLLMFailedError` from
      the provider seam) escaping the generator entirely and being caught by
      `_generate_agent_stream`'s own outer `except Exception` (`agent_routes.py` ~103-115),
      which manually builds the fallback `error` event the same way
      `public_routes._generate_chat_stream` does on its own failure path.

Both are exercised here as real `POST /agent/chat` requests over `TestClient`, mirroring
`tests/test_public_chat.py`'s SSE-body-driven-by-a-real-request style, not a call into
`_generate_agent_stream`/`run_agent` directly.

Per the brief: `agent_routes.py`'s handler is expected to already work correctly for both cases
(this closes a coverage gap, not a known bug) — each test below states, in its own docstring,
that it is expected GREEN on current code; a genuine bug surfaced by either would be a real
finding for the implementer, not a reason to change the test's assertions.

Fakes/helpers below are near-verbatim, LOCAL copies of `tests/test_agent_endpoint.py`'s own
(no cross-test-file imports, per that file's own module docstring / CONVENTIONS.md §10) —
`auth_helpers.login_as`/`FakeGoogleOAuthClient` are the one explicitly SHARED test seam
(`auth_helpers.py`'s own module docstring: "every later admin-route test... "), reused directly.

CONVENTIONS.md §10: every test here requests `tmp_engine`, so the whole module skips cleanly
without a DB (`TEST_DATABASE_URL` unset).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.agent.loop import LlmStep, ToolCallStep
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app

_ADMIN_EMAIL = "agent-error-admin@example.com"


# ---------------------------------------------------------------------------
# Fakes: a scripted, tool-call-only `AgentLLM` and one that raises directly out of `next_step`
# (mirrors `tests/test_agent_endpoint.py::FakeAgentLLM`'s shape, trimmed to what these two tests
# need — no call recording, since neither test asserts on what the LLM was called with).
# ---------------------------------------------------------------------------


@dataclass
class _ScriptedAgentLLM:
    """Scripted `AgentLLM` fake: returns `steps[n]` on the nth call; raises loudly if the script
    runs out (mirrors `tests/test_agent_endpoint.py::FakeAgentLLM`'s own "raise, don't hang"
    precedent).
    """

    steps: list[LlmStep]
    calls: int = 0

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        if self.calls >= len(self.steps):
            raise AssertionError(
                f"_ScriptedAgentLLM script exhausted after {len(self.steps)} steps but the "
                f"route asked for step #{self.calls + 1}."
            )
        step = self.steps[self.calls]
        self.calls += 1
        return step


@dataclass
class _ExplodingAgentLLM:
    """An `AgentLLM` fake whose `next_step` always raises a plain (non-`AppError`) exception —
    simulates a bug, or a real provider failure (`AgentLLMFailedError`), that `run_agent` does
    NOT catch itself (its own `try/except` only wraps the `call_tool` invocation, never
    `llm.next_step`) — the exact scenario `agent_routes._generate_agent_stream`'s OUTER
    `except Exception` exists for.
    """

    calls: list[None] = field(default_factory=list)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        self.calls.append(None)
        raise RuntimeError("simulated agent LLM crash mid-exchange (_ExplodingAgentLLM fake)")


# ---------------------------------------------------------------------------
# SSE parsing (verbatim shape of `tests/test_public_chat.py`/`tests/test_agent_endpoint.py`'s own
# local `SseEvent`/`_parse_sse_events`).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SseEvent:
    name: str
    data: dict[str, Any]


def _parse_sse_events(body: str) -> list[_SseEvent]:
    events: list[_SseEvent] = []
    blocks = [block for block in body.split("\n\n") if block.strip()]
    for block in blocks:
        lines = [line for line in block.split("\n") if line]
        event_lines = [line for line in lines if line.startswith("event:")]
        data_lines = [line for line in lines if line.startswith("data:")]
        assert len(event_lines) == 1, f"expected exactly one 'event:' line in block {block!r}"
        assert len(data_lines) == 1, f"expected exactly one 'data:' line in block {block!r}"
        name = event_lines[0][len("event:") :].strip()
        raw_data = data_lines[0][len("data:") :].strip()
        events.append(_SseEvent(name=name, data=json.loads(raw_data)))
    return events


# ---------------------------------------------------------------------------
# HTTP / app-building helpers (mirrors `tests/test_agent_endpoint.py`'s own shape).
# ---------------------------------------------------------------------------


def _build_settings() -> Settings:
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=_ADMIN_EMAIL,
    )


def _build_client(tmp_engine: Engine, *, agent_llm: object) -> TestClient:
    app = create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
        agent_llm=agent_llm,
    )
    return TestClient(app)


def _post_agent_chat(client: TestClient, body: dict[str, Any]) -> tuple[int, str, str]:
    with client.stream("POST", "/api/v1/agent/chat", json=body) as response:
        text = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), text


# ---------------------------------------------------------------------------
# (a) A graceful `Error` AgentEvent (second consecutive tool failure) reaches the wire via
#     `_to_sse_event`'s fallback branch.
# ---------------------------------------------------------------------------


def test_second_consecutive_tool_failure_error_event_reaches_wire_via_fallback(
    tmp_engine: Engine,
) -> None:
    """PRD §6: a SECOND consecutive tool-call failure ends the exchange with a graceful `Error`
    AgentEvent (`app.agent.loop.run_agent`) — `_to_sse_event`'s catch-all fallback branch
    (`agent_routes.py`'s `_to_sse_event`, the final `return sse_event("error", ...)` for anything
    that isn't `Token`/`ToolCall`/`ToolResult`/`Done`) is what actually puts it on the wire.

    Two consecutive calls to a tool name that doesn't exist (`ToolNotFoundError`, an `AppError`)
    is the simplest deterministic way to trigger this: the first failure is recorded and the
    exchange continues (PRD §6 self-correction step); the second — since one has already
    happened — ends the exchange with `Error(code=exc.code, message=str(exc))`.

    Expected GREEN on current code (coverage-closing, per the task brief: `agent_routes.py`'s
    handler already works for this path) — a fresh failure here would be a genuine finding for
    the implementer, not a reason to weaken this test.
    """
    llm = _ScriptedAgentLLM(
        steps=[
            ToolCallStep("this_tool_does_not_exist", {}),
            ToolCallStep("this_tool_does_not_exist", {}),
        ]
    )
    client = _build_client(tmp_engine, agent_llm=llm)
    login_as(client, _ADMIN_EMAIL)

    status, content_type, body = _post_agent_chat(
        client, {"messages": [{"role": "user", "content": "Do something with a bogus tool."}]}
    )

    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type
    events = _parse_sse_events(body)
    names = [event.name for event in events]

    assert names.count("tool_call") == 2, names  # every ATTEMPT fires `tool_call` (loop docstring)
    assert "tool_result" not in names, names  # neither attempt ever succeeded
    assert "done" not in names, names  # the exchange ended in failure, not success
    assert names.count("error") == 1, names
    assert names[-1] == "error", names

    error_payload = events[-1].data["error"]
    assert isinstance(error_payload, dict)
    # `ToolNotFoundError.code`, propagated verbatim.
    assert error_payload["code"] == "tool_not_found"
    assert isinstance(error_payload["message"], str) and error_payload["message"]


# ---------------------------------------------------------------------------
# (b) An exception escaping `run_agent` itself hits the route's outer `except` and still yields
#     a clean `error` event.
# ---------------------------------------------------------------------------


def test_exception_escaping_run_agent_hits_outer_except_and_yields_clean_error_event(
    tmp_engine: Engine,
) -> None:
    """A plain exception raised directly out of `AgentLLM.next_step` (a bug, or a real
    `AgentLLMFailedError` from the provider seam) is NOT caught by `run_agent`'s own
    `try/except` (`agent_routes.py` docstring: that `try` wraps only the `call_tool`
    invocation) — it escapes the generator entirely and is caught by
    `_generate_agent_stream`'s OUTER `except Exception` (`agent_routes.py` ~103-115), which
    yields the manually-built fallback `error` event instead of letting a bare 500/dead
    connection reach the client.

    Expected GREEN on current code (coverage-closing, per the task brief) — a fresh failure here
    would be a genuine finding for the implementer, not a reason to weaken this test.
    """
    llm = _ExplodingAgentLLM()
    client = _build_client(tmp_engine, agent_llm=llm)
    login_as(client, _ADMIN_EMAIL)

    status, content_type, body = _post_agent_chat(
        client, {"messages": [{"role": "user", "content": "This will crash the fake LLM."}]}
    )

    assert status == 200, body
    assert content_type.startswith("text/event-stream"), content_type
    events = _parse_sse_events(body)
    names = [event.name for event in events]

    # The crash happens on the very first `llm.next_step` call, before any AgentEvent at all —
    # the only SSE block on the wire is the outer-except's own fallback `error` event.
    assert names == ["error"], names
    assert len(llm.calls) == 1

    error_payload = events[0].data["error"]
    assert isinstance(error_payload, dict)
    assert error_payload["code"] == "agent_stream_failed"  # the generic non-AppError fallback code
    assert isinstance(error_payload["message"], str) and error_payload["message"]
