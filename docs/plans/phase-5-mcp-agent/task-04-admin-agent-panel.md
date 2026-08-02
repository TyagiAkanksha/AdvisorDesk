---
id: task-04
phase: phase-5-mcp-agent
depends_on: [task-03, phase-2-auth-cms-crud/task-04]
status: planned
spec: advisordesk-prd.md §2.2, §5.4
---

# task-04 — Admin agent panel

## Goal

The §2.2 agent panel is live: a chat sidebar in the admin shell where a content manager issues
natural-language commands and watches each tool call render live as it happens, with conversation
history held client-side and content lists refreshing automatically after agent writes.

## Context (read ONLY these)

- `docs/FRONTEND-CONVENTIONS.md` §3–§7; `advisordesk-prd.md` §2.2 (panel story + example
  commands), §5.4 (stateless: resend full history; the five events).
- `apps/client/src/components/chat/useChatStream.ts` + its `parseSseStream` (p4-t05) — lift the
  parser pattern; admin's variant handles the extra tool events.

## Files

- Create: `apps/admin/src/components/agent/AgentPanel/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: `apps/admin/src/components/agent/useAgentStream.ts` (colocated VM hook)
- Create: `apps/admin/src/components/agent/{ToolCallCard,AgentMessage}/…` (folder-per-component)
- Modify: `apps/admin/src/components/shell/AppShell/Component.tsx` (panel toggle button + Drawer
  mount), `apps/admin/src/lib/api/contentApi.ts` (no new endpoints — invalidation helper only)

## Interfaces

- **Consumes:** `agent_chat` SSE events (task-03); `AppShell` (p2-t04); RTK tags
  `['Content','Stats','Tags']`. *(Amended by owner ratification, phase-5 checkpoint 2026-08-02:
  the original brief named `AppSnackbar` (p2-t06) for error display; the built panel renders
  errors INLINE inside the panel instead — a persistent notice at the point of failure suits a
  chat surface better than a transient edge toast. Ratified as-built.)*
- **Produces (later tasks rely on — produce exactly):**
  - `useAgentStream` (in-file Args/Result): state `{turns: AgentTurn[], streaming, error}` and
    `send(text)`; `AgentTurn = {role:'user'|'assistant', text, events: ToolEvent[]}`;
    `ToolEvent = {kind:'call'|'result', tool, detail}`. Holds the FULL conversation in component
    state and POSTs it whole each `send` (§5.4 statelessness — client owns history); on `done`,
    dispatches invalidation of `['Content','Stats','Tags']` so open screens refetch; on `error`
    event, surfaces the envelope message.
  - `ToolCallCard` (`{event: ToolEvent}`): renders `tool_call` as "→ create_draft {title:…}" and
    `tool_result` as "✓ create_draft — <result_summary>", interleaved in stream order.
  - `AgentPanel`: persistent right MUI Drawer toggled from the AppShell (state survives
    navigation within the app — component state lives above the route outlet).

## Steps (TDD)

- [ ] **Step 1: Failing hook tests** (jsdom, scripted SSE fixtures with interleaved tool
  events): events land interleaved in order on the current turn; full history resent on the
  second `send` (**§5.4 pin — assert the POST body**); `done` triggers the tag invalidation
  dispatch; `error` event sets error state.
- [ ] **Step 2:** `pnpm -C apps/admin test` → FAIL. **Step 3: implement** `useAgentStream`
  (reusing the lifted parser). **Step 4:** run → PASS.
- [ ] **Step 5: Failing component tests**: panel opens from the shell toggle; a scripted
  exchange renders user bubble → streaming text → two ToolCallCards in order → final text;
  cap-report message (from the §6 cap) renders as a normal assistant message; input disabled
  while streaming.
- [ ] **Step 6:** run → FAIL → **implement** components + shell wiring → PASS.
- [ ] **Step 7: Gates → commit:** `feat(admin): live agent panel (phase-5 task-04)`

## Verify

```bash
pnpm -C apps/admin test && pnpm -C apps/admin lint && pnpm -C apps/admin type-check
pnpm -C apps/admin dev &  # open panel; "Draft an article on Roth IRA conversion basics and tag
                          # it retirement" → live tool_call/tool_result cards; content list
                          # refreshes with the new draft without reload
```

## Acceptance

- §2.2 example commands work live with per-call visibility; §5.4 statelessness held client-side
  (history resent whole; proven by test).
- Agent writes appear in dashboard/list via invalidation without manual refresh.
- Panel is a persistent drawer; errors and cap reports render honestly.

> ⚠️ Phase INDEX checkpoint: after this task's gates pass, pause for the user's live pass before
> closing phase 5.
