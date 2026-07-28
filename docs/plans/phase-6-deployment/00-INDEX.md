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

**Architecture:** ECR-pushed images from the phase-1 Dockerfiles; env-driven config (no wildcard
CORS, Secure cookies); metrics as an ASGI middleware wrapping the existing endpoints (log-based —
no new HTTP surface).

**Tech Stack:** AWS App Runner (default; ECS Fargate documented alternative) · ECR · Supabase
Postgres (deployed DB, §9 default) · structured logging.

## Global Constraints

Phase-1..5 Global Constraints apply verbatim. Additionally:

- Deployment scripts/notes live in `infra/deploy/` (§3.1); no secrets in the repo, ever — env is
  configured in AWS, documented by name only.
- The §5 API surface is frozen in this phase: metrics/log changes must not add or alter routes
  (baseline diff stays empty).

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 1 | Metrics middleware (first-token p50/p95) | `task-01-metrics-middleware.md` | phase-4/task-02 |
| 2 | AWS deployment | `task-02-aws-deployment.md` | phases 1–5 complete |
| 3 | README + demo script | `task-03-readme-demo-script.md` | 2 |

Order: 1 → 2 → 3 (1 can land any time after phase-4 task-02). Rationale: the deployed
verification in task-02 wants task-01's latency logs available; the README documents what task-02
stood up.

## Status

planned — snapshot only; git history is authoritative.
