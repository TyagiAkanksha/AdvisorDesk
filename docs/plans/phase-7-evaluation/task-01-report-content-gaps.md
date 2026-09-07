---
id: task-01
phase: phase-7-evaluation
depends_on: [phase-4-rag-assistant/task-02, phase-5-mcp-agent/task-01]
status: built
spec: advisordesk-prd.md §6 (report_content_gaps), §9.1
---

# task-01 — `report_content_gaps`: the ninth MCP tool

## Goal

Content managers (and the agent) can ask "what are clients asking that we haven't covered?" —
the §6 gap query over recorded `retrieval_found=false` outcomes, exposed as MCP tool #9. Completes
the §9.1 "9 MCP tools" metric.

## Context (read ONLY these)

- `advisordesk-prd.md` §6 `report_content_gaps` row — the query definition is normative: "user
  messages whose following assistant message (same session, next by `created_at`) has
  `retrieval_found = false`", last `days` days, newest first, `{count, gaps:[{question,
  asked_at, session_id}]}`.
- `app/services/chat.py` (p4-t02 — the columns being read); `app/mcp/tools_read.py` (pattern).

## Files

- Create: `apps/api/app/mcp/tools_gaps.py`
- Create: `apps/api/tests/test_content_gaps.py`
- Modify: `apps/api/app/services/chat.py` (add the query), `apps/api/app/mcp/server.py`
  (register), `apps/api/mcp-tools.json` (regenerate → 9 tools)

## Interfaces

- **Consumes:** `chat_messages` rows with `retrieval_found` (p4-t02); `call_tool` seam.
- **Produces (later tasks rely on — produce exactly):**
  - `app.services.chat::content_gaps(session, *, days: int = 30, limit: int = 20)
    -> list[GapRow]` — `GapRow{question: str, asked_at: datetime, session_id: uuid.UUID}`;
    pairing = the assistant message in the same session with the smallest `created_at` greater
    than the user message's (§6 verbatim); newest first; window = `now - days`.
  - MCP tool `report_content_gaps(days: int = 30, limit: int = 20)` →
    `{count: int, gaps: [{question, asked_at, session_id}]}` — auto-available to the agent loop
    (schemas come from the registry).

## Steps (TDD)

- [ ] **Step 1: Failing query tests** (`test_content_gaps.py`, seeded `chat_messages` fixtures —
  §9 requires testing against seeded `retrieval_found` rows):
  - a user msg followed by a `retrieval_found=false` assistant msg → included; followed by
    `true` → excluded;
  - pairing pin: two user messages in one session pair with their OWN next assistant message
    (interleaving doesn't cross-pair);
  - a user message with no following assistant message → excluded;
  - `days` window excludes old rows; newest first; `limit` respected;
  - user messages (role `user`, `retrieval_found` NULL) never appear as gaps themselves.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** `content_gaps`. **Step 4:** run → PASS.
- [ ] **Step 5: Failing tool tests**: happy path via `call_tool` returns `{count, gaps}` with
  ISO `asked_at`; failure path: `days=-1` → `ToolInputError` (§9 happy+failure per tool).
- [ ] **Step 6:** run → FAIL → **implement** `tools_gaps.py` + register → PASS.
- [ ] **Step 7: Baseline:** regenerate `mcp-tools.json` (9 tools) — same commit.
- [ ] **Step 8: Gates → commit:** `feat(api): report_content_gaps tool (phase-7 task-01)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_content_gaps.py -q   # all passed
python -c "import json;print(len(json.load(open('mcp-tools.json'))))"  # 9
```

## Acceptance

- The §6 pairing/window/order semantics are pinned by tests, including the interleaving case.
- Tool #9 registered and schema-baselined; agent loop can call it with no further wiring.
