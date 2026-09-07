---
id: task-05
phase: phase-2-auth-cms-crud
depends_on: [task-03, task-04]
status: built
spec: advisordesk-prd.md §2.2, §5.2
---

# task-05 — Dashboard and content list screens

## Goal

The §2.2 dashboard story is real: status/tag counts from `GET /stats`, and a content list with
title/status/tags/updated columns, status-tag-search filters, pagination, and delete-with-confirm
("permanent — no restore"). Establishes the per-domain RTK endpoint + tag-invalidation pattern the
editor (task-06) and agent panel (phase-5) reuse.

## Context (read ONLY these)

- `docs/FRONTEND-CONVENTIONS.md` §3–§6; `advisordesk-prd.md` §2.2 (stories), §5.2 (params).
- `apps/admin/src/lib/api/baseApi.ts` + generated schema (task-03/04) — inject, don't create new
  APIs.

## Files

- Create: `apps/admin/src/lib/api/{contentApi.ts,tagsApi.ts,statsApi.ts}`,
  `src/types/api/content.ts`
- Create: `apps/admin/src/components/dashboard/DashboardScreen/{Component.tsx,index.ts,Component.test.tsx}`
- Create: `apps/admin/src/components/content/ContentListScreen/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
  + colocated `useContentList.ts`
- Create: `apps/admin/src/components/common/{StatusChip,ConfirmDialog,EmptyState,ErrorState}/…`
  (folder-per-component each)
- Create: `apps/admin/src/app/(app)/page.tsx` (dashboard), `src/app/(app)/content/page.tsx` — thin

## Interfaces

- **Consumes:** `baseApi` tags `['Content','Tags','Stats']`; DTOs `ContentListResponse`,
  `TagWithCount`, `StatsResponse` via `@/types`.
- **Produces (later tasks rely on — produce exactly):**
  - `contentApi`: `listContent` query (`{status?,tag?,q?,page?,page_size?}`, provides
    `['Content']`), `deleteContent` mutation (invalidates `['Content','Stats','Tags']`).
  - `tagsApi.listTags` (provides `['Tags']`), `statsApi.getStats` (provides `['Stats']`).
  - `@/types/api/content.ts`: `ContentDto`, `ContentListDto`, `ContentStatus` as-const union
    (`'draft'|'published'|'archived'`).
  - `common/StatusChip` (`status: ContentStatus` → colored MUI Chip via one lookup, no per-call
    color logic), `common/ConfirmDialog` (`{open,title,body,confirmLabel,onConfirm,onClose,
    isPending}`), `EmptyState`, `ErrorState` — reused by task-06 and phase-5.
  - `useContentList` VM hook: filters/pagination state + debounced `q` (in-file Args/Result).

## Steps (TDD)

- [ ] **Step 1: Failing endpoint tests** (node env, mocked `global.fetch`): `listContent`
  serializes params correctly; `deleteContent` dispatch between two `initiate()` calls refetches
  the list (tag invalidation proven).
- [ ] **Step 2:** run → FAIL → **implement the three injected APIs + types** → PASS.
- [ ] **Step 3: Failing component tests** (jsdom): DashboardScreen renders a card per status with
  counts; ContentListScreen renders rows, empty state, error state; delete flow opens
  ConfirmDialog with "permanent" copy and fires the mutation on confirm; filter changes call the
  query with new params.
- [ ] **Step 4:** run → FAIL → **implement screens + common components + thin pages** → PASS.
- [ ] **Step 5: Gates → commit:**
  `feat(admin): dashboard + content list with filters and delete (phase-2 task-05)`

## Verify

```bash
pnpm -C apps/admin test && pnpm -C apps/admin lint && pnpm -C apps/admin type-check
pnpm -C apps/admin dev &  # with seeded API: dashboard counts render; list filters/paginates;
                          # delete asks for confirmation and the row disappears
```

## Acceptance

- Dashboard + list match §2.2 (status, tags, updated date visible; filter/search by title, tag,
  status).
- Delete requires confirmation, copy states permanence (no restore, §2.2/§12), and invalidation
  refreshes list + stats without a reload.
- StatusChip colors come from a single typed lookup; screens use `common/` + theme only.
