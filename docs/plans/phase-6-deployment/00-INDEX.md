# phase-6-deployment — Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Implement with superpowers:test-driven-development;
> claim completion only via superpowers:verification-before-completion.

**Spec:** `advisordesk-prd.md` §10 Phase 6 — authoritative. Primary sections: §9 (deployment,
security NFRs, streaming latency, metrics), §9.1 (metrics to capture), §11 rows 1/5 (models,
container deploy). On any conflict the PRD wins.
**Conventions:** `CONVENTIONS.md` §11.

**Goal:** AdvisorDesk runs on AWS — API on App Runner, both frontends as containers, Supabase as
the database — with rate limiting verified in the deployed environment, first-token latency
metrics logging p50/p95, and a README + demo script a stranger can follow end-to-end (§10).
Owner-ratified scope additions (2026-08-08): the MCP endpoint ships ENABLED in production behind
bearer-token auth (task-04, superseding the original `MCP_HTTP_ENABLED=false` pin — the owner
chose streamable-HTTP exposure at the site's MCP slug for Claude connectors), and the two
phase-2 auth-hardening findings (logout revocation, OAuth state CSRF) are fixed pre-deploy
(task-05).

**Architecture:** ECR-pushed images from the phase-1 Dockerfiles; env-driven config (no wildcard
CORS, Secure cookies); metrics as an ASGI middleware wrapping the existing endpoints (log-based —
no new HTTP surface). Production topology (owner D4, 2026-08-08): custom domain
`tyagiakanksha.com` (registrar + DNS on Cloudflare) — `advisordesk.tyagiakanksha.com` → client,
`admin.advisordesk.tyagiakanksha.com` → admin, `api.advisordesk.tyagiakanksha.com` → API + MCP
(`/api/v1/mcp`); all one registrable domain, so the SameSite=Lax admin cookie works.

**Tech Stack:** AWS App Runner (default; ECS Fargate documented alternative) · ECR · Supabase
Postgres (deployed DB, §9 default) · structured logging.

## Global Constraints

Phase-1..5 Global Constraints apply verbatim. Additionally:

- Deployment scripts/notes live in `infra/deploy/` (§3.1); no secrets in the repo, ever — env is
  configured in AWS, documented by name only.
- The §5 API surface is frozen in this phase: NO task adds or alters REST routes (the OpenAPI
  baseline diff stays empty). Metrics are log-based; MCP bearer tokens are minted by a SCRIPT,
  not a route; auth hardening changes behavior behind the existing routes only.

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 1 | Metrics middleware (first-token p50/p95) | `task-01-metrics-middleware.md` | phase-4/task-02 |
| 2 | AWS deployment | `task-02-aws-deployment.md` | 1, 4, 5 |
| 3 | README + demo script | `task-03-readme-demo-script.md` | 2 |
| 4 | MCP bearer-token auth | `task-04-mcp-bearer-auth.md` | phase-5 complete |
| 5 | Auth hardening (logout revocation + OAuth state) | `task-05-auth-hardening.md` | 4 (migration chain) |

Order: **1 → 4 → 5 → 2 → 3**. Rationale: task-02 deploys the image, so every code task (1, 4, 5)
must be merged into it first — the deployed verification exercises task-01's latency logs,
task-04's bearer-gated MCP endpoint, and task-05's hardened auth; the README (3) documents what
2 stood up. Task-05 chains its Alembic revision after task-04's, fixing the migration order.

## Status

planned — snapshot only; git history is authoritative.
