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

## Phases

| Phase | Folder | Scope | Depends on | Status |
|---|---|---|---|---|
| 1 | [`phase-1-skeleton/`](phase-1-skeleton/00-INDEX.md) | Monorepo scaffold, tooling gates, schema + Alembic, app factory + healthz, MUI frontend scaffolds + codegen, compose (incl. `--profile local-db`) | — | planned |
| 2 | [`phase-2-auth-cms-crud/`](phase-2-auth-cms-crud/00-INDEX.md) | Google OAuth + allowlist + sessions, content/tag/stats services, all §5.2 admin routes, admin shell + dashboard + editor | 1 | planned |
| 3 | [`phase-3-publish-client-content/`](phase-3-publish-client-content/00-INDEX.md) | Chunking, embeddings + transactional publish/re-embed/remove lifecycle, public content API, client content pages | 2 | planned |
| 4 | [`phase-4-rag-assistant/`](phase-4-rag-assistant/00-INDEX.md) | Retrieval (similarity convention), `/public/chat` SSE + persistence + refusal, rate limiting, seed articles + eval set, client chat UI | 3 | planned |
| 5 | [`phase-5-mcp-agent/`](phase-5-mcp-agent/00-INDEX.md) | In-process MCP server + 8 core tools, agent loop + stateless `/agent/chat`, admin agent panel | 4 | planned |
| 6 | [`phase-6-deployment/`](phase-6-deployment/00-INDEX.md) | Metrics middleware, AWS deployment (App Runner + Supabase), README + demo script | 5 | planned |
| 7 | [`phase-7-evaluation/`](phase-7-evaluation/00-INDEX.md) | `report_content_gaps` tool (#9), groundedness harness, §9.1 metrics + definition-of-done walk | 6 (tasks 01–02 only need 4–5) | planned |

Statuses here and in each INDEX are a snapshot; **git history is authoritative**.

## Standing gates (from the moment they exist)

- From phase-2 task-03: any route/DTO change regenerates `apps/api/openapi.json` **and** both
  apps' codegen in the same commit.
- From phase-5 task-01: any tool-schema change regenerates `apps/api/mcp-tools.json` in the same
  commit.
- Controller checkpoints (⚠️ in the INDEXes): live visual pass after phase-2 task-06 (admin app),
  phase-4 task-05 (client chat), phase-5 task-04 (agent panel).
