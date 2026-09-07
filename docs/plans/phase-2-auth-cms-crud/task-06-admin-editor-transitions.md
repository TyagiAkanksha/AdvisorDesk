---
id: task-06
phase: phase-2-auth-cms-crud
depends_on: [task-03, task-04]
status: built
spec: advisordesk-prd.md §2.2, §4, §5.2
---

# task-06 — Content editor and status transitions

## Goal

A content manager can create a draft, edit title/markdown body/tags, and move an item through
`draft → published → archived` from the UI (§2.2). The editor works unchanged when phase 3 makes
publish do real embedding — the seam is entirely server-side.

## Context (read ONLY these)

- `docs/FRONTEND-CONVENTIONS.md` §3–§6, §9 (error surfacing).
- `advisordesk-prd.md` §2.2 (stories), §4 (slug immutability — display only, never editable),
  §5.2 (PATCH semantics + transition endpoints).
- `apps/admin/src/lib/api/contentApi.ts` (task-05) — extend, don't fork.

## Files

- Create: `apps/admin/src/components/content/ContentEditorScreen/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
  + colocated `useContentEditor.ts`
- Create: `apps/admin/src/components/content/MarkdownPreview/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: `apps/admin/src/components/common/AppSnackbar/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: thin pages `src/app/(app)/content/new/page.tsx`, `src/app/(app)/content/[id]/page.tsx`
- Modify: `apps/admin/src/lib/api/contentApi.ts` (add endpoints)

## Interfaces

- **Consumes:** `contentApi`/`tagsApi` + `common/` set (task-05); DTOs via `@/types`.
- **Produces (later tasks rely on — produce exactly):**
  - `contentApi` additions: `getContent` (provides `['Content']` by id), `createContent`,
    `updateContent`, `publishContent`, `archiveContent` mutations — each invalidates
    `['Content','Stats','Tags']`.
  - `ContentEditorScreen` + `useContentEditor` (loads by id or starts blank; dirty-state save;
    transition actions with per-status enablement: draft → publish; published → archive; archived
    → publish again; delete everywhere).
  - `MarkdownPreview` (`{markdown: string}`) — placeholder `<pre>` rendering here; **phase-3
    task-04 replaces the internals with the shared markdown renderer; the props contract must not
    change.**
  - `common/AppSnackbar` — surfaces the §9 envelope `message` for any failed mutation; reused by
    phase-5 panel.
- **Implementation note:** tag input = MUI Autocomplete `freeSolo` normalizing to
  lowercase-hyphen on entry (mirrors `tags.py` server normalization).

## Steps (TDD)

- [ ] **Step 1: Failing endpoint tests** (node): `updateContent` sends only changed fields;
  `publishContent` POSTs the transition URL; each mutation invalidates the three tags (proven via
  refetch pattern).
- [ ] **Step 2:** run → FAIL → **implement endpoint additions** → PASS.
- [ ] **Step 3: Failing component tests** (jsdom): new-content form submits
  `{title, body_md, tags}` and routes to the item page; slug rendered read-only (no input);
  transition buttons enabled/disabled per status matrix; failed save surfaces the envelope
  message via AppSnackbar; preview toggle shows MarkdownPreview with the body.
- [ ] **Step 4:** run → FAIL → **implement screens/hook/components + thin pages** → PASS.
- [ ] **Step 5: Gates → commit:**
  `feat(admin): content editor + status transitions (phase-2 task-06)`

## Verify

```bash
pnpm -C apps/admin test && pnpm -C apps/admin lint && pnpm -C apps/admin type-check
pnpm -C apps/admin dev &  # create draft → edit → publish → archive → delete, all from UI;
                          # slug never editable; errors appear as snackbar, never raw JSON
```

## Acceptance

- Full §2.2 editor story works end-to-end against the phase-2 API (publish = status flip via the
  no-op pipeline; embedding arrives in phase 3 with zero UI change).
- Slug is display-only from creation onward (§4 immutability).
- Transition availability follows the status machine; every mutation refreshes list/dashboard via
  invalidation.

> ⚠️ Phase INDEX checkpoint: after this task's gates pass, pause for the user's visual pass of the
> whole admin flow before closing phase 2.
