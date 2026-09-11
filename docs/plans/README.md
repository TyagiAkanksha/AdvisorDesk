# AdvisorDesk — Implementation Plans Registry

This directory holds the full implementation plan for the AdvisorDesk PRD
([`../../advisordesk-prd.md`](../../advisordesk-prd.md), v1.4 — authoritative on any conflict).

One shape only: **a folder per PRD §10 phase**, each containing a `00-INDEX.md` spine (goal, global
constraints, task table, ordering rationale) and one `task-NN-<slug>.md` file per task. Subtasks
are the checkboxed steps **inside** each task file — deliberately not separate files, so one
implementer (or subagent) gets a whole task in a single read.

**Conventions cited by every task:** [`../../CONVENTIONS.md`](../../CONVENTIONS.md) (Python) ·
[`../FRONTEND-CONVENTIONS.md`](../FRONTEND-CONVENTIONS.md) (both Next.js apps).

## Required plugins/skills

Implementation runs on the **superpowers** plugin (v6.1.1 installed here; on another machine:
`/plugin marketplace add obra/superpowers-marketplace` → `/plugin install
superpowers@superpowers-marketplace`). The skills the plan requires:

| Skill | When |
|---|---|
| `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` | Executing a phase folder task-by-task |
| `superpowers:test-driven-development` | Implementing every task — steps are RED/GREEN-shaped and assume it |
| `superpowers:verification-before-completion` | Before claiming any task complete — run the gates, paste real output |
| `superpowers:requesting-code-review` | At each phase's controller checkpoint |

**Format note:** task files follow `superpowers:writing-plans` (Goal header, Interfaces,
bite-sized checkbox TDD steps, exact commands with expected output), adapted at program scale:
they pin exact paths, signatures, DTO fields, `operation_id`s, named test behaviors, and commands —
not full literal implementations of future code. The PRD plus each task's Interfaces block carry
the authority; on any conflict the PRD wins.

## Execution model (per task, from phase 2 on)

Three separate agents per task — one responsibility each (`CLAUDE.md` working rules):

1. **Test-author agent** — executes the task's RED steps: writes the failing tests named in the
   brief, runs them, records the failure evidence.
2. **Implementer agent** — executes the GREEN steps: makes the authored tests pass. May add
   tests; may NOT weaken, modify, or delete the authored tests without controller approval.
   Runs the type-checker after every significant change.
3. **Reviewer agent** — never the implementer; verifies spec compliance and quality (functionality,
   tests, maintainability, coupling, design) against the brief with file:line evidence. **A review
   is never a rubber stamp**: Critical/Important findings get a fix round and a re-review; Minors
   are ledgered for the whole-branch final review.

Model policy: Sonnet for initial iterations; escalate only when a task demonstrably needs it
(final whole-branch reviews run on the most capable model). Fresh agent per task; artifacts move
as files (brief → report → review package), not chat context. (Phase-1 task files predate the
test-author/implementer split; their RED/GREEN steps were executed by a single implementer with a
separate reviewer.)

## Phases

| Phase | Folder | Scope | Depends on | Status |
|---|---|---|---|---|
| 1 | [`phase-1-skeleton/`](phase-1-skeleton/00-INDEX.md) | Monorepo scaffold, tooling gates, schema + Alembic, app factory + healthz, MUI frontend scaffolds + codegen, compose (incl. `--profile local-db`) | — | merged |
| 2 | [`phase-2-auth-cms-crud/`](phase-2-auth-cms-crud/00-INDEX.md) | Google OAuth + allowlist + sessions, content/tag/stats services, all §5.2 admin routes, admin shell + dashboard + editor | 1 | merged |
| 3 | [`phase-3-publish-client-content/`](phase-3-publish-client-content/00-INDEX.md) | Chunking, embeddings + transactional publish/re-embed/remove lifecycle, public content API, client content pages | 2 | merged |
| 4 | [`phase-4-rag-assistant/`](phase-4-rag-assistant/00-INDEX.md) | Retrieval (similarity convention), `/public/chat` SSE + persistence + refusal, rate limiting, seed articles + eval set, client chat UI | 3 | merged |
| 5 | [`phase-5-mcp-agent/`](phase-5-mcp-agent/00-INDEX.md) | In-process MCP server + 8 core tools, agent loop + stateless `/agent/chat`, admin agent panel | 4 | merged |
| 6 | [`phase-6-deployment/`](phase-6-deployment/00-INDEX.md) | Metrics middleware, AWS deployment (single-host EC2 + Caddy + Supabase; App Runner plan superseded at execution — see 00-INDEX amendment), README + demo script | 5 | merged |
| 7 | [`phase-7-evaluation/`](phase-7-evaluation/00-INDEX.md) | `report_content_gaps` tool (#9), groundedness harness, §9.1 metrics + definition-of-done walk | 6 (tasks 01–02 only need 4–5) | merged |
| mcp-oauth | [`mcp-oauth/`](mcp-oauth/00-INDEX.md) | OAuth 2.1 authorization server co-hosted with the MCP resource server (RFC 9728/8414 discovery, DCR, PKCE, Google-bridged consent, refresh rotation, revoke, admin "Connected apps" page) so claude.ai's Connect button works — spec [`mcp-oauth/DESIGN.md`](mcp-oauth/DESIGN.md) | 7 | merged |
| 8 | [`phase-8-ui-polish/`](phase-8-ui-polish/00-INDEX.md) | UI polish for both apps in three sub-phases, each its own PR: **A** shared foundation (theme type scale + fonts, twin Markdown renderer, primitives, route files), **B** client shell/home/article/chat, **C** admin shell/sign-in/dashboard/table/editor/connected-apps/agent panel + sign-in error redirect — spec [`phase-8-ui-polish/DESIGN.md`](phase-8-ui-polish/DESIGN.md) | mcp-oauth | A+B+C merged + deployed (PRs #28, #29, #31); prod 9a1e74b |

Statuses here and in each INDEX are a snapshot; **git history is authoritative**. As of this
writing, phases 1–7 and `mcp-oauth` are merged to `main` and deployed; phase 8's sub-phase A
task files are written on branch `feat/ui-polish-a` (sub-phases B and C get their task files
after A ships).

## Standing gates (from the moment they exist)

- From phase-2 task-03: any route/DTO change regenerates `apps/api/openapi.json` **and** both
  apps' codegen in the same commit.
- From phase-5 task-01: any tool-schema change regenerates `apps/api/mcp-tools.json` in the same
  commit.
- Controller checkpoints (⚠️ in the INDEXes): live visual pass after phase-2 task-06 (admin app),
  phase-4 task-05 (client chat), phase-5 task-04 (agent panel).
