---
id: task-03
phase: phase-5-mcp-agent
depends_on: [task-02, phase-2-auth-cms-crud/task-01, phase-4-rag-assistant/task-02]
status: planned
spec: advisordesk-prd.md §6 (agent loop), §5.4, §11 row 7
---

# task-03 — Agent loop and the stateless `/agent/chat` endpoint

## Goal

A hand-rolled tool loop (§11 row 7) over the v1.5 provider executes CMS commands against the 8
MCP tools with the §6 cap-of-8 and honest partial-completion reporting, streamed as §5.4's typed
events from a stateless `POST /agent/chat`. The server persists nothing for agent chats (§12).

## Context (read ONLY these)

- `advisordesk-prd.md` §6 "Agent loop" (cap behavior verbatim; error-once self-correction; draft
  rule), §5.4 (stateless contract + the five event shapes), §11 row 7 (hand-rolled — no
  LangChain).
- `app/mcp/runtime.py` (`call_tool`, `list_tool_schemas`) — the only tool interface.
- `app/routes/sse.py` (p4-t02) — reuse; do not write a second SSE writer.

## Files

- Create: `apps/api/app/agent/loop.py`, `apps/api/app/routes/agent_routes.py`,
  `apps/api/app/models/schemas/agent.py`
- Create: `apps/api/tests/{test_agent_loop.py,test_agent_endpoint.py}`
- Modify: `apps/api/app/factory.py` (router + LLM seam), `apps/api/openapi.json` + admin codegen

## Interfaces

- **Consumes:** `call_tool`/`list_tool_schemas` (t01–t02); `require_admin` → `AdminPrincipal`
  (actor for tools); `sse_event`/`sse_response` (p4-t02).
- **Produces (later tasks rely on — produce exactly):**
  - `app.agent.loop`: `class AgentLLM(Protocol): def next_step(self, messages, tool_schemas)
    -> LlmStep` where `LlmStep = TextDelta(text) | ToolCallStep(name, arguments) | Done()` —
    seam faked in tests (factory param `agent_llm=None`).
  - Real implementation `OpenAICompatibleAgentLLM` (v1.5) — mirror `OpenAICompatibleChatLLM`
    (p4-t02) exactly: `from_settings` classmethod building an `openai` SDK client from
    `llm_base_url` + `nvidia_api_key` (same empty-key boot-safe `"unset"` fallback),
    `model=settings.chat_model` (pinned `meta/llama-3.1-8b-instruct`, probe-verified for tool
    calling 2026-08-01), tools passed as standard `tools=[...]` function schemas derived from
    `list_tool_schemas()`; provider errors logged, never enveloped (phase-3/4 rule). No
    NVIDIA-specific `extra_body`.
  - **Probe-derived pins (2026-08-01, both load-bearing — the pinned model's known weaknesses):**
    (1) the system prompt MUST include a steering line: answer capability/general questions in
    text WITHOUT calling a tool; only call tools to operate on CMS content (the model over-calls
    under `tool_choice="auto"` without it). (2) `ToolInputError` messages fed back on the
    error-once retry MUST be actionable — field name, expected type, and an example (the model
    emits array args as string repr on first shot, e.g. `tags: "['retirement']"`, and
    self-corrects ONLY when the error names the field and shows the shape; description examples
    alone do not fix it). The loop feeds the structured tool error back verbatim as the tool
    result — tests pin both behaviors.
  - `run_agent(messages: list[dict], *, llm: AgentLLM, session: Session, actor_id)
    -> Iterator[AgentEvent]` with
    `AgentEvent = Token(text) | ToolCall(tool, arguments) | ToolResult(tool, result_summary)
    | Done(tool_calls) | Error(code, message)`:
    - executes tool calls sequentially via `call_tool`; **hard cap 8** — at the cap, emit a final
      assistant message reporting exactly which operations completed and which remain, telling
      the user to re-run (§6 verbatim behavior);
    - on a tool error: feed the error back to the model once for self-correction; a second
      failure → graceful explanatory finish, never silent (§6);
    - system prompt: CMS operations agent; drafts article bodies in-model and passes them to
      `create_draft`; NEVER publishes unless the user's message explicitly instructs it (§6).
  - Route: `POST /agent/chat` `operation_id="agent_chat"`, `require_admin`, body
    `{messages:[{role:'user'|'assistant', content}]}` (last = new turn); SSE events exactly §5.4:
    `token{text}` / `tool_call{tool,arguments}` / `tool_result{tool,result_summary}` /
    `done{tool_calls:[...]}` / `error{error:{code,message}}`, interleaved in execution order.
    **The admin panel (task-04) parses exactly these.**

## Steps (TDD)

- [ ] **Step 1: Failing loop tests** (`test_agent_loop.py`, scripted `FakeAgentLLM`): two-tool
  script → events in execution order (token, tool_call, tool_result, ..., done with full
  summary); **cap pin:** script demanding 9 calls → exactly 8 executed, final text names
  completed ops and the remainder + re-run instruction; **error-once pin:** first `call_tool`
  raises → error fed to LLM, script self-corrects → success; two consecutive failures → graceful
  `Error` finish; **draft-rule pin:** "draft an article…" script calls `create_draft`, never
  `publish`.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** `loop.py`. **Step 4:** run → PASS.
- [ ] **Step 5: Failing endpoint tests** (`test_agent_endpoint.py`): 401 without admin session;
  SSE event sequence matches the loop; **statelessness pin: after a full exchange,
  `chat_sessions`/`chat_messages` row counts are unchanged** (§5.4/§12); history resent in the
  body reaches the LLM verbatim.
- [ ] **Step 6:** run → FAIL → **implement** `agent_routes.py` + wiring → PASS.
- [ ] **Step 7: Baseline:** regenerate `openapi.json` + admin codegen (same commit).
- [ ] **Step 8: Gates → commit:**
  `feat(api): agent loop + stateless /agent/chat SSE (phase-5 task-03)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_agent_loop.py tests/test_agent_endpoint.py -q
grep -rn "langchain\|llamaindex" apps/api -i   # empty (§11 row 7)
git diff --exit-code openapi.json               # regenerated in-commit
```

## Acceptance

- §6 loop rules pinned: cap-8 with honest partial report, error-once then graceful, drafts never
  auto-published.
- §5.4 pinned: stateless (zero rows written), five event types in execution order, admin-gated.
- One SSE implementation serves both chat endpoints.
