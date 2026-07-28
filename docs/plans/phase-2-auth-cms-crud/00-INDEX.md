# phase-2-auth-cms-crud — Auth + CMS CRUD — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Implement with superpowers:test-driven-development;
> claim completion only via superpowers:verification-before-completion.

**Spec:** `advisordesk-prd.md` §10 Phase 2 — authoritative. Primary sections: §2.2 (CMS stories),
§4 + §4.1 (slug rules, soft delete, actor columns), §5.1–§5.2 (routes), §9 (auth security, tests).
On any conflict the PRD wins.
**Conventions:** `CONVENTIONS.md` · `docs/FRONTEND-CONVENTIONS.md`.

**Goal:** a content manager signs in with Google (allowlisted), sees a dashboard of all content
with status/tags/updated date, and can create, edit, filter, soft-delete, and move items through
`draft → published → archived` — with publish/archive running behind a lifecycle seam that phase 3
fills with real embedding. All nine §5.2 routes exist with committed OpenAPI baseline + codegen.

**Architecture:** OAuth + signed-cookie sessions in `app/auth`; session-first services in
`app/services` (the exact functions phase-5 MCP tools wrap); thin routes with DTOs and explicit
operation_ids; admin app on RTK Query with tag invalidation.

**Tech Stack:** authlib-style manual OAuth code exchange via httpx (injectable client seam),
itsdangerous cookie signing · FastAPI DTOs · RTK Query + MUI (admin).

## Global Constraints

Every task's requirements implicitly include this section — plus phase-1's (gates, commits,
path-scoped adds, PRD defaults philosophy) verbatim.

- **Wire-surface gate (standing from task-03 on):** any route/DTO change regenerates
  `apps/api/openapi.json` AND both apps' `pnpm codegen` output in the same commit.
- Soft-deleted rows are invisible to every endpoint (PRD §5 intro): excluded from lists/counts;
  by-id/slug reads, updates, and status transitions on them return 404. Reads go through
  `active_select` (CONVENTIONS.md §3) — ad-hoc `is_deleted` filters are review-blocking.
- All admin routes require `require_admin`; 401 without a session or with a soft-deleted user row
  (§9).

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 1 | Google OAuth, sessions, allowlist, require_admin | `task-01-google-oauth-sessions.md` | phase-1 |
| 2 | Content/tag/stats services + lifecycle seam | `task-02-content-tag-services.md` | phase-1 (∥ 1) |
| 3 | Admin REST routes + DTOs + OpenAPI baseline | `task-03-admin-rest-routes.md` | 1, 2 |
| 4 | Admin shell, auth UI, RTK foundation | `task-04-admin-shell-auth-ui.md` | phase-1/task-04, 1 |
| 5 | Dashboard + content list | `task-05-admin-dashboard-list.md` | 3, 4 |
| 6 | Editor + status transitions | `task-06-admin-editor-transitions.md` | 3, 4 (∥ 5) |

Order: (1 ∥ 2) → 3 → 4 → (5 ∥ 6). Rationale: task-02 pins the service signatures that task-03's
routes AND phase-5's MCP tools wrap; task-03's committed baseline pins the DTO names tasks 5–6
consume through codegen.

## ⚠️ Controller checkpoint — after task-06

When task-06's gates pass, PAUSE. Ask the user for a live visual pass of the admin app (sign-in →
dashboard → create draft → edit → publish → archive → delete) before closing the phase. Use
superpowers:requesting-code-review for the phase diff. Do not skip.

## Status

planned — snapshot only; git history is authoritative.
