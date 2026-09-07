# phase-5-mcp-agent — MCP + agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Implement with superpowers:test-driven-development;
> claim completion only via superpowers:verification-before-completion.

**Spec:** `advisordesk-prd.md` §10 Phase 5 — authoritative. Primary sections: §6 (tool table +
agent-loop rules), §5.4 (stateless agent endpoint + events), §3 (in-process MCP, exposure rule,
shared services), §2.2 (agent-panel story). On any conflict the PRD wins.
**Conventions:** `CONVENTIONS.md` · `docs/FRONTEND-CONVENTIONS.md`.

**Goal:** the editorial workflow becomes agentic: 8 core MCP tools wrap the same service functions
as the REST routes, a hand-rolled tool loop executes natural-language commands with a hard
8-call cap and honest partial-completion reporting, `/agent/chat` streams tokens and tool events
statelessly, and the admin panel renders each tool call live (§2.2).

**Architecture:** MCP server instantiated inside the FastAPI process (official Python SDK); an
in-process invocation seam so the agent loop calls tools without HTTP; HTTP exposure OFF by
default behind admin auth when enabled (§3); loop + endpoint reuse phase-4's SSE utilities; panel
is an RTK-connected drawer that invalidates content tags on completion.

**Tech Stack:** official `mcp` Python SDK · NVIDIA OpenAI-compatible API (v1.5, `LLM_BASE_URL`)
function-calling on **`Settings.chat_model` = `meta/llama-3.1-8b-instruct`** (probe-verified
2026-08-01: correct tool selection + multi-turn tool-result follow-up + streamed tool-call
deltas; two known weaknesses with proven mitigations — array args as string repr on first shot,
fixed by the §6 error-once retry with an actionable field error; over-eager tool calls on
conversational questions, fixed by a system-prompt steering line — both pinned in task-03) ·
phase-4 SSE utils (`sse_event`/`sse_response`) + the client's `parseSseStream` pattern · MUI
Drawer + RTK Query.

## Global Constraints

Phase-1/2/3/4 Global Constraints apply verbatim (gates, commits, wire-surface + mcp-tools
baselines same-commit, soft-delete visibility, no real LLM-provider calls in tests — the
`AgentLLM` seam takes fakes, exactly as `ChatLLM`/`Embedder` did).

- **§3 security rule:** CMS write tools must never be reachable unauthenticated —
  `MCP_HTTP_ENABLED=false` by default; when true, the MCP route sits behind the same admin
  session auth; pinned by test.
- **§6 draft rule:** agent-created drafts are ALWAYS status `draft` — publishing happens only on
  explicit user instruction, enforced in the loop's system prompt AND by the tools' design.
- Every tool validates inputs with Pydantic and returns structured JSON (§6 header).

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 0 | Lifecycle hardening (pre-task) | `task-00-lifecycle-hardening.md` | phase-3/task-02 |
| 1 | MCP server foundation + read tools | `task-01-mcp-server-read-tools.md` | phase-2/task-02, phase-3/task-02 |
| 2 | MCP write tools (six) | `task-02-mcp-write-tools.md` | 0, 1 |
| 3 | Agent loop + `/agent/chat` | `task-03-agent-loop-endpoint.md` | 2, phase-2/task-01, phase-4/task-02 |
| 4 | Admin agent panel | `task-04-admin-agent-panel.md` | 3, phase-2/task-04 |

Order: 0 → 1 → 2 → 3 → 4 (linear). Rationale: task-00 hardens the publish/archive services
BEFORE the MCP write tools wrap them (owner decision 2026-07-25 — the agent's `publish` tool
must not reset `published_at` or re-bill embeddings, and illegal transitions must fail
server-side, not rely on UI button gating); task-01 pins the tool-registration pattern and the
in-process `call_tool` seam; task-03 consumes the complete tool set; task-04 renders task-03's
event stream.

## ⚠️ Controller checkpoint — after task-04

When task-04's gates pass, PAUSE for the user's live pass of the §2.2 agent commands ("Draft an
article on Roth IRA conversion basics and tag it retirement", "How many published pieces do we
have on tax planning?", "Find everything tagged estate-planning and publish the drafts") watching
the live tool events. Use superpowers:requesting-code-review for the phase diff. Do not skip.

## Status

built — snapshot only; git history is authoritative.
