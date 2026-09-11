---
id: hy-t07
phase: hygiene-2026-09
depends_on: []
status: todo
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: opus
---

# Task 07 — Editor hook tidy: `withFeedback`, `useTitleValidation`, shared editor test harness

## Goal

Close the deferred Minors from the phase-8 task-19 (Sonnet) and task-20 (Opus) reviews, verbatim
from the ledger: t19 M1 "five near-identical then/catch feedback blocks → a `withFeedback` helper";
t19 M2 "hook now 379 lines — consider extracting title-validation state + the feedback helper";
t19 M3 "new-mode `isDirty` uses untrimmed length while canSubmit trims"; t20 M4 "~90 lines of
harness duplicated into responsivePreview.test (brief-mandated) → shared testing helper".
**Behaviour does not change** — this is a refactor with a test-side extraction in front of it.

## Context (read ONLY these)

- `apps/admin/src/components/content/ContentEditorScreen/{useContentEditor.ts, Component.tsx,
  Component.test.tsx, useContentEditor.test.tsx, feedback.test.tsx, responsivePreview.test.tsx,
  publishGuard.test.tsx, resilientRefetch.test.tsx, tagBlurCapture.test.tsx, tagOrderDirty.test.tsx,
  chipDeletePreservesTyping.test.tsx, components/**, index.ts}`.
- `apps/admin/src/components/common/useRisingEdgeNotice/` and `apps/admin/src/lib/copy.ts`
  (`TITLE_REQUIRED_MESSAGE`, `CONTENT_SAVED_MESSAGE`, `CONTENT_PUBLISHED_MESSAGE`,
  `CONTENT_ARCHIVED_MESSAGE`, `CONTENT_DELETED_MESSAGE`, `SAVE_ERROR_FALLBACK`,
  `TRANSITION_ERROR_FALLBACK`, `DELETE_ERROR_FALLBACK`, `EDITOR_REFRESH_ERROR`).
- `apps/admin/eslint.config.mjs` and `docs/plans/hygiene-2026-09/task-09-testing-import-lint-guard.md`.
- `docs/FRONTEND-CONVENTIONS.md` §3 (VM hooks flat + colocated, **Args/Result interfaces declared
  in-file**), §7, §9; `docs/plans/phase-8-ui-polish/DESIGN.md` §5 C5 + its plan-time ruling.

**State observed at the time of writing (HEAD of `chore/hygiene-ride`):**

- `useContentEditor.ts` is **375** lines (the review said 379).
- **t19 M3 is already fixed**: `useContentEditor.ts:165-176` reads
  `trimmedTitle.length > 0 || body.length > 0 || tags.length > 0` with a `p8 final, F7` comment,
  and `useContentEditor.test.tsx:131-138` pins `isDirty` staying false for a whitespace-only title.
  What is still missing is a pin that the **`beforeunload` guard** is not armed in that state —
  that is this task's one new case for M3 (see the RED/GREEN map).
- The five feedback blocks are `useContentEditor.ts:217-225` (create), `235-242` (save),
  `262-271` (publish), `280-285` (the save-then-publish PATCH — **deliberately silent on success**),
  `292-299` (archive). `confirmDelete` (`310-325`) is NOT one of them: its failure goes to the
  dialog (`deleteError`), never to the snackbar.
- Harness duplication: `Component.test.tsx:20-171` and `responsivePreview.test.tsx:18-117` are the
  same block (`vi.mock` + request helpers + `draftFixture` + option-per-endpoint `mockFetch` +
  `renderNew`/`renderEdit`). `useContentEditor.test.tsx:18-93` and `feedback.test.tsx:22-93` share a
  second idiom (handler-based `mockFetch` + `editHandler`) whose `draftFixture` differs only in two
  timestamps, neither of which is asserted against as a literal.
  `publishGuard`/`resilientRefetch`/`tagOrderDirty`/`tagBlurCapture`/`chipDeletePreservesTyping`
  have **bespoke** fixtures and call-counting handlers that ARE the point of each test — they are
  **out of scope and must not be touched**.

**Rulings for this task (controller; do not re-open):**
- `EditorForm` takes the hook result object as its single prop (`components/EditorForm/interface.ts`
  imports `UseContentEditorResult`) — DESIGN.md §5 C5 plan-time ruling, **not reopened** (INDEX
  "Dropped from the ride list").
- `UseContentEditorResult` **stays declared in `useContentEditor.ts`** (§3: a VM hook declares its
  Args/Result interfaces in-file) and stays byte-identical field-for-field, in this order:
  `mode, isLoading, isError, hasContent, savedTitle, slug, status, createdAt, updatedAt,
  publishedAt, title, setTitle, titleError, onTitleBlur, body, setBody, tags, setTags, tagOptions,
  isDirty, submitLabel, canSubmit, isSaving, onSubmit, canPublish, canArchive, isTransitioning,
  onPublish, onArchive, isDeleting, deleteDialogOpen, deleteError, openDeleteDialog,
  closeDeleteDialog, confirmDelete, previewOpen, togglePreview`.
- `withFeedback` lives **inside `useContentEditor.ts`** as a hook-local closure over
  `notifySuccess`/`notifyError`. A colocated `feedback.ts` was rejected: `feedback.test.tsx` in
  this folder is a screen-level suite, and a sibling `feedback.ts` would falsely read as its
  subject.
- **Line-count ceiling: ≤ 325, not ≤ 300.** The 48-line `UseContentEditorResult` must stay
  in-file (§3) and ~70 lines are provenance comments the review culture requires. The two
  extractions the finding names are roughly line-neutral, so this task ALSO extracts the delete
  dialog (`useDeleteDialog.ts`) and the two tag helpers (`editorTags.ts`) — accepted by the
  controller as in-scope for "hook size" (t19 M2). Expected landing ≈ 318 lines.
- The shared harness lives at `ContentEditorScreen/testing/renderEditor.tsx`. Task 09's lint guard
  exempts any `src/**/testing/**` folder, so this file *may* import `@/testing/*` — it simply
  does not need to (`stubMatchMedia` stays in `responsivePreview.test.tsx`).

## Files

**Create**
- `apps/admin/src/components/content/ContentEditorScreen/testing/renderEditor.tsx` (test-only)
- `apps/admin/src/components/content/ContentEditorScreen/useTitleValidation.ts`
- `apps/admin/src/components/content/ContentEditorScreen/useTitleValidation.test.tsx`
- `apps/admin/src/components/content/ContentEditorScreen/useDeleteDialog.ts`
- `apps/admin/src/components/content/ContentEditorScreen/editorTags.ts`

**Modify**
- `apps/admin/src/components/content/ContentEditorScreen/useContentEditor.ts`
- `apps/admin/src/components/content/ContentEditorScreen/{Component.test.tsx,
  responsivePreview.test.tsx, feedback.test.tsx, useContentEditor.test.tsx}` (harness migration +
  the new cases only)

**Delete** — none. **Must not be touched:** `Component.tsx`, `components/**`, `publishGuard.test.tsx`,
`resilientRefetch.test.tsx`, `tagBlurCapture.test.tsx`, `tagOrderDirty.test.tsx`,
`chipDeletePreservesTyping.test.tsx`.

## Interfaces

```ts
// testing/renderEditor.tsx — TEST-ONLY, colocated with the screen it renders.
// The `vi.mock('next/navigation', …)` block stays in each test file — `vi.mock` is hoisted per
// test file and its factory cannot live here.
export function requestUrl(input: RequestInfo | URL): string;
export function requestMethod(input: RequestInfo | URL, init?: RequestInit): string;
export function pathnameOf(input: RequestInfo | URL): string;
/** `fetchBaseQuery` hands the mock a native `Request`; a plain `init.body` is the fallback. */
export async function requestBody(input: RequestInfo | URL, init?: RequestInit): Promise<unknown>;
export function jsonResponse(body: unknown, status?: number): Response;
export const NEW_CONTENT_ID = '99999999-9999-9999-9999-999999999999';
export const draftFixture: ContentDto;      // Component.test.tsx's values, verbatim
export const publishedFixture: ContentDto;  // id 2222…, slug estate-planning-101, status published
export const archivedFixture: ContentDto;   // id 3333…, slug social-security-timing
export interface MockFetchOptions { getContentResponse?: Response; createContentResponse?: Response;
  updateContentResponse?: Response; publishContentResponse?: Response;
  archiveContentResponse?: Response; tagsResponse?: Response; }
/** Option-per-endpoint idiom — Component.test.tsx:114-155, moved verbatim. */
export function mockEditorFetch(options?: MockFetchOptions): Mock;
export type EditorFetchHandler = (url: URL, method: string) => Response | Promise<Response>;
/** Handler idiom — useContentEditor.test.tsx:66-72, moved verbatim. */
export function mockEditorFetchWith(handler: EditorFetchHandler): Mock;
/** useContentEditor.test.tsx:74-85, moved verbatim (GET/PATCH the draft, two tags). */
export const editHandler: EditorFetchHandler;
export function renderNew(): RenderResult;              // <Providers><ContentEditorScreen/></Providers>
export function renderEdit(contentId: string): RenderResult;

// useTitleValidation.ts (t19 M2)
export interface UseTitleValidationResult {
  /** TITLE_REQUIRED_MESSAGE once blurred or a submit was attempted while the trimmed title is
   *  empty; null otherwise. */
  titleError: string | null;
  onTitleBlur: () => void;
  /** Called by `onSubmit` when it refuses to send a blank title. */
  markSubmitAttempted: () => void;
}
/** Takes the ALREADY-TRIMMED title so "blank" is defined once, by the caller. */
export function useTitleValidation(trimmedTitle: string): UseTitleValidationResult;

// useContentEditor.ts, hook-local (t19 M1)
const withFeedback = async <T>(
  run: () => Promise<T>,
  messages: { success?: string; errorFallback: string },
): Promise<T | undefined>;
// Resolves to the mutation's value on success (every caller's mutation resolves a ContentDto,
// never `undefined`, so `undefined` unambiguously means "it failed"); shows `success` via
// notifySuccess only when given (the save-then-publish PATCH passes none); on rejection shows
// notifyError(extractErrorMessage(error, errorFallback)) and resolves `undefined`.

// useDeleteDialog.ts — the delete state machine moved out unchanged (NOT a withFeedback caller:
// its failure stays in the dialog). Distinct from ContentListScreen/useDeleteConfirmation
// (hygiene t06), which arms a ROW and delegates the mutation to its list hook.
export interface UseDeleteDialogResult {
  isDeleting: boolean; deleteDialogOpen: boolean; deleteError: string | null;
  openDeleteDialog: () => void; closeDeleteDialog: () => void; confirmDelete: () => void;
}
export function useDeleteDialog(contentId?: string): UseDeleteDialogResult;

// editorTags.ts — `normalizeTag` and `tagsEqual` moved verbatim with their comments
// (`useContentEditor.ts:86-110`); no consumer outside this folder (grep-confirmed).
export function normalizeTag(raw: string): string;
export function tagsEqual(a: string[], b: string[]): boolean;
```

## RED/GREEN map (read before writing anything)

| Test | Status when written |
|---|---|
| Harness migration of 4 test files | green → green (no assertion changes) |
| `useTitleValidation.test.tsx` (5 cases) | **RED** — module does not exist |
| `useContentEditor.test.tsx` "whitespace-only title does not arm the beforeunload guard" | green on arrival (t19 M3 already fixed by p8 final F7) |
| `feedback.test.tsx` Archive success + Archive failure | green on arrival (characterisation net for the `withFeedback` refactor) |

For the M3 pin, the test-author MAY produce RED evidence by temporarily changing
`trimmedTitle.length > 0` back to `title.length > 0` at `useContentEditor.ts:170`, running the
file, pasting the two failures, then `git checkout -- apps/admin/src/components/content/ContentEditorScreen/useContentEditor.ts`.
That is evidence-gathering, not implementation: the report must show `git status` clean after it.

## Steps

- [ ] **Step 1 (test-author): create `testing/renderEditor.tsx`.** Move, **verbatim**, from
  `Component.test.tsx`: the request helpers (lines 46-70), `NEW_CONTENT_ID` + the three fixtures
  (72-103), `MockFetchOptions` + `mockFetch` (105-155, renamed `mockEditorFetch`), `renderNew` /
  `renderEdit` (157-171). Then add, verbatim from `useContentEditor.test.tsx`, the handler idiom
  (64-85) as `EditorFetchHandler` / `mockEditorFetchWith` / `editHandler`. Widen the request-body
  helper to the signature in Interfaces (`requestBody`), keeping both existing behaviours.
  File header:

  ```tsx
  import { render } from '@testing-library/react';
  import { vi } from 'vitest';

  import Providers from '@/app/providers';
  import type { ContentDto } from '@/types/api/content';

  import { ContentEditorScreen } from '..';

  // hygiene t07 (closes phase-8 t20 M4): ~90 lines of render/fetch harness were duplicated
  // verbatim from Component.test.tsx into responsivePreview.test.tsx, and a second idiom into
  // useContentEditor.test.tsx / feedback.test.tsx. TEST-ONLY module, colocated with the screen
  // (any `**/testing/**` folder is exempt from hygiene t09's `@/testing` lint guard). Do NOT
  // move the `vi.mock('next/navigation', …)` blocks here (`vi.mock` is hoisted per test file).
  // The five remaining suites in this folder keep their bespoke fixtures and call-counting
  // handlers — those ARE what each of them pins.
  ```

- [ ] **Step 2 (test-author): migrate the four suites — preambles only.** Every `describe`/`it`
  body stays **byte-identical**; local names are preserved with import aliases so no assertion
  line moves. Delete each file's now-duplicated block and its now-unused imports
  (`@testing-library/react`'s `render`, `Providers`, `ContentDto`, `ContentEditorScreen`) —
  `lint` runs at zero warnings, so a leftover unused import fails the gate.

  `Component.test.tsx` — keep lines 1-45 except as noted (the `// @vitest-environment jsdom`
  pragma stays line 1, the `vi.mock` block and the accessible-name contract comment stay), delete
  46-171, and use:

  ```tsx
  import { screen, waitFor, within } from '@testing-library/react';
  import '@testing-library/jest-dom/vitest';
  import userEvent from '@testing-library/user-event';
  import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

  import { PREVIEW_EMPTY_MESSAGE } from '@/lib/copy';
  import { formatDate } from '@/lib/format';

  import {
    NEW_CONTENT_ID,
    archivedFixture,
    draftFixture,
    jsonResponse,
    mockEditorFetch as mockFetch,
    pathnameOf,
    publishedFixture,
    renderEdit,
    renderNew,
    requestBody as requestJson,
    requestMethod,
  } from './testing/renderEditor';
  ```

  (Keep only the names each file actually uses — an unused specifier is a lint warning.)

  `responsivePreview.test.tsx` — delete 24-117, keep the `vi.mock` block and the suite:

  ```tsx
  import { screen } from '@testing-library/react';
  import '@testing-library/jest-dom/vitest';
  import userEvent from '@testing-library/user-event';
  import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

  import { stubMatchMedia } from '@/testing/matchMedia';

  import { draftFixture, mockEditorFetch as mockFetch, renderEdit } from './testing/renderEditor';
  ```

  `feedback.test.tsx` — delete 27-93:

  ```tsx
  import {
    draftFixture,
    editHandler,
    jsonResponse,
    mockEditorFetchWith as mockFetch,
    publishedFixture,
    renderEdit,
    renderNew,
  } from './testing/renderEditor';
  import type { EditorFetchHandler } from './testing/renderEditor';
  ```

  `useContentEditor.test.tsx` — delete 27-85 (keep `Wrapper` and `Providers`):

  ```tsx
  import {
    draftFixture,
    editHandler,
    mockEditorFetchWith as mockFetch,
    requestBody,
    requestMethod,
  } from './testing/renderEditor';
  ```

- [ ] **Step 3 (test-author): run the migration green-to-green.**
  `cd apps/admin && npx vitest run ContentEditorScreen` → the same test count and the same names as
  before the migration, all passing. Paste the before and after summary lines. `pnpm -C apps/admin
  type-check` and `pnpm -C apps/admin lint` must both be clean at this point.

- [ ] **Step 4 (test-author, RED): new `useTitleValidation.test.tsx`.**

  ```tsx
  // @vitest-environment jsdom
  import { act, renderHook } from '@testing-library/react';
  import { describe, expect, it } from 'vitest';

  import { useTitleValidation } from './useTitleValidation';

  // hygiene t07 (closes phase-8 t19 M2): the editor's title-validation state (blurred /
  // submit-attempted / message) is a self-contained state machine, extracted out of the 375-line
  // `useContentEditor.ts`. RED today: the module does not exist.
  describe('useTitleValidation', () => {
    it('stays silent until the field is blurred or a submit is attempted', () => {
      const { result } = renderHook(() => useTitleValidation(''));

      expect(result.current.titleError).toBeNull();
    });

    it('reports the required message after a blur on a blank title', () => {
      const { result } = renderHook(() => useTitleValidation(''));

      act(() => result.current.onTitleBlur());

      expect(result.current.titleError).toBe('Title is required');
    });

    it('reports the required message after a submit attempt without any blur', () => {
      const { result } = renderHook(() => useTitleValidation(''));

      act(() => result.current.markSubmitAttempted());

      expect(result.current.titleError).toBe('Title is required');
    });

    it('clears as soon as a non-blank title arrives and stays clear on re-blur', () => {
      const { result, rerender } = renderHook((title: string) => useTitleValidation(title), {
        initialProps: '',
      });
      act(() => result.current.onTitleBlur());
      expect(result.current.titleError).toBe('Title is required');

      rerender('A title');
      expect(result.current.titleError).toBeNull();

      act(() => result.current.onTitleBlur());
      expect(result.current.titleError).toBeNull();
    });

    it('re-reports when a title that was typed is emptied again', () => {
      const { result, rerender } = renderHook((title: string) => useTitleValidation(title), {
        initialProps: 'A title',
      });
      act(() => result.current.onTitleBlur());
      expect(result.current.titleError).toBeNull();

      rerender('');

      expect(result.current.titleError).toBe('Title is required');
    });
  });
  ```

  Check `TITLE_REQUIRED_MESSAGE` in `lib/copy.ts` first and use its exact value in these pins.

- [ ] **Step 5 (test-author): append the M3 guard pin to `useContentEditor.test.tsx`**, directly
  after the existing "new mode: isDirty stays false when the title is whitespace only" case:

  ```tsx
    // hygiene t07 (phase-8 t19 M3): the trimmed-title rule must also keep the unload guard
    // disarmed — a blank-looking form is not unsaved work.
    it('new mode: a whitespace-only title does not arm the beforeunload guard', () => {
      mockFetch(editHandler);
      const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

      act(() => result.current.setTitle('   '));

      const event = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(false);
    });
  ```

- [ ] **Step 6 (test-author): append the two feedback characterisation cases to
  `feedback.test.tsx`** (safety net for the `withFeedback` refactor — the only two branches of the
  five-block matrix with no pin today: archive success and a transition failure):

  ```tsx
  const publishedHandler: EditorFetchHandler = (url, method) => {
    if (url.pathname === `/api/v1/content/${publishedFixture.id}` && method === 'GET') {
      return jsonResponse(publishedFixture);
    }
    if (url.pathname === `/api/v1/content/${publishedFixture.id}/archive` && method === 'POST') {
      return jsonResponse({ ...publishedFixture, status: 'archived' });
    }
    return editHandler(url, method);
  };
  ```

  ```tsx
    it('a successful Archive shows an "Archived" notice', async () => {
      mockFetch(publishedHandler);
      const user = userEvent.setup();

      renderEdit(publishedFixture.id);
      await user.click(await screen.findByRole('button', { name: /archive/i }));

      expect(await screen.findByRole('status')).toHaveTextContent('Archived');
    });

    it('a failed Archive surfaces the envelope message as an alert and shows no success notice', async () => {
      const ARCHIVE_FAILURE_MESSAGE = 'Could not archive while a publish is in flight.';
      mockFetch((url, method) => {
        if (url.pathname === `/api/v1/content/${publishedFixture.id}/archive` && method === 'POST') {
          return jsonResponse(
            { error: { code: 'conflict', message: ARCHIVE_FAILURE_MESSAGE } },
            409,
          );
        }
        return publishedHandler(url, method);
      });
      const user = userEvent.setup();

      renderEdit(publishedFixture.id);
      await user.click(await screen.findByRole('button', { name: /archive/i }));

      expect(await screen.findByRole('alert')).toHaveTextContent(ARCHIVE_FAILURE_MESSAGE);
      expect(screen.queryByText('Archived')).not.toBeInTheDocument();
    });
  ```

  If the editor skeleton also renders `role="status"`, use `waitFor(() =>
  expect(screen.getByRole('status')).toHaveTextContent('Archived'))` instead of `findByRole`
  (ledger gotcha) and say so.

  Run: `cd apps/admin && npx vitest run ContentEditorScreen useTitleValidation` → only
  `useTitleValidation.test.tsx` is red (unresolved import); everything else green. Record both.
  Commit the test-side work: `git commit -m "test(admin): shared editor harness + title-validation/guard/archive pins (hygiene t07 RED)"`.

- [ ] **Step 7 (implementer, GREEN): create `useTitleValidation.ts`, `editorTags.ts`,
  `useDeleteDialog.ts`.**

  ```ts
  // useTitleValidation.ts
  import { useState } from 'react';

  import { TITLE_REQUIRED_MESSAGE } from '@/lib/copy';

  // hygiene t07 (phase-8 t19 M2): the title field's validation state, lifted out of
  // `useContentEditor` so that hook composes state machines instead of owning them
  // (docs/FRONTEND-CONVENTIONS.md §3). Takes the ALREADY-TRIMMED title so "blank" is defined
  // once, by the caller — `titleError`, `onSubmit`, `isDirty` and `canSubmit` all read the
  // same definition.
  export interface UseTitleValidationResult {
    titleError: string | null;
    onTitleBlur: () => void;
    markSubmitAttempted: () => void;
  }

  export function useTitleValidation(trimmedTitle: string): UseTitleValidationResult {
    const [titleBlurred, setTitleBlurred] = useState(false);
    const [submitAttempted, setSubmitAttempted] = useState(false);

    return {
      titleError:
        (titleBlurred || submitAttempted) && trimmedTitle.length === 0
          ? TITLE_REQUIRED_MESSAGE
          : null,
      onTitleBlur: () => setTitleBlurred(true),
      markSubmitAttempted: () => setSubmitAttempted(true),
    };
  }
  ```

  Before writing it, compare with today's title-validation logic in `useContentEditor.ts` (the
  `titleBlurred`/`submitAttempted`-style state and how `titleError` is derived) and keep the
  existing semantics exactly — the existing pins in `Component.test.tsx`/`useContentEditor.test.tsx`
  are the contract.

  `editorTags.ts`: move `useContentEditor.ts:86-110` (`tagsEqual` + `normalizeTag`) verbatim,
  comments included, adding `export` to `tagsEqual`.

  ```ts
  // useDeleteDialog.ts
  import { useRouter } from 'next/navigation';
  import { useState } from 'react';

  import { useSnackbar } from '@/components/common';
  import { useDeleteContentMutation } from '@/lib/api/contentApi';
  import { CONTENT_DELETED_MESSAGE, DELETE_ERROR_FALLBACK } from '@/lib/copy';
  import { extractErrorMessage } from '@/lib/errorMessage';

  // hygiene t07: the editor's delete confirmation (dialog state, in-dialog error, the DELETE,
  // the "Deleted" notice and the redirect) is one self-contained state machine, moved out of
  // `useContentEditor` UNCHANGED. It is deliberately not a `withFeedback` caller: a delete
  // failure stays inside the open dialog (`deleteError`), it never becomes a snackbar.
  export interface UseDeleteDialogResult {
    isDeleting: boolean;
    deleteDialogOpen: boolean;
    deleteError: string | null;
    openDeleteDialog: () => void;
    closeDeleteDialog: () => void;
    confirmDelete: () => void;
  }

  export function useDeleteDialog(contentId?: string): UseDeleteDialogResult {
    const router = useRouter();
    const { success: notifySuccess } = useSnackbar();
    const [deleteContentMutation, { isLoading: isDeleting }] = useDeleteContentMutation();
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    const openDeleteDialog = () => {
      setDeleteError(null);
      setDeleteDialogOpen(true);
    };

    const closeDeleteDialog = () => {
      setDeleteDialogOpen(false);
      setDeleteError(null);
    };

    const confirmDelete = () => {
      if (!contentId) {
        return;
      }
      setDeleteError(null);
      void deleteContentMutation(contentId)
        .unwrap()
        .then(() => {
          setDeleteDialogOpen(false);
          notifySuccess(CONTENT_DELETED_MESSAGE);
          router.push('/content');
        })
        .catch((error: unknown) => {
          setDeleteError(extractErrorMessage(error, DELETE_ERROR_FALLBACK));
        });
    };

    return {
      isDeleting,
      deleteDialogOpen,
      deleteError,
      openDeleteDialog,
      closeDeleteDialog,
      confirmDelete,
    };
  }
  ```

  Same rule: mirror today's `confirmDelete`/dialog code in `useContentEditor.ts` line by line
  (the snackbar API names — `useSnackbar().success` vs `notifySuccess` — and the redirect must
  match what the hook does today).

- [ ] **Step 8 (implementer, GREEN): rewrite the four mutation paths in `useContentEditor.ts`.**
  Drop the `useDeleteContentMutation` import and the delete/title state; add
  `const deleteDialog = useDeleteDialog(contentId);`,
  `const { titleError, onTitleBlur, markSubmitAttempted } = useTitleValidation(trimmedTitle);`
  and `import { normalizeTag, tagsEqual } from './editorTags';`. Return `...deleteDialog,` in place
  of the six delete fields, at the same position in the object literal. Then:

  ```ts
    // hygiene t07 (phase-8 t19 M1): one place where a mutation's outcome becomes feedback —
    // this replaced five near-identical then/catch blocks. `success` is omitted by the
    // save-then-publish PATCH: one click reports only "Published" (DESIGN.md §5 C5 ruling).
    // Every caller's mutation resolves a `ContentDto`, so `undefined` means "it failed".
    const withFeedback = async <T>(
      run: () => Promise<T>,
      messages: { success?: string; errorFallback: string },
    ): Promise<T | undefined> => {
      try {
        const value = await run();
        if (messages.success) {
          notifySuccess(messages.success);
        }
        return value;
      } catch (error) {
        notifyError(extractErrorMessage(error, messages.errorFallback));
        return undefined;
      }
    };

    const createNew = async () => {
      const created = await withFeedback(
        () => createContent({ title: trimmedTitle, body_md: body, tags }).unwrap(),
        { success: CONTENT_SAVED_MESSAGE, errorFallback: SAVE_ERROR_FALLBACK },
      );
      if (created) {
        router.push(`/content/${created.id}`);
      }
    };

    const onSubmit = () => {
      if (trimmedTitle.length === 0) {
        markSubmitAttempted();
        return;
      }
      if (mode === 'new') {
        void createNew();
        return;
      }
      if (!contentId || !isDirty) {
        return;
      }
      const patch = buildPatch();
      if (!patch) {
        return;
      }
      void withFeedback(() => updateContent({ id: contentId, patch }).unwrap(), {
        success: CONTENT_SAVED_MESSAGE,
        errorFallback: SAVE_ERROR_FALLBACK,
      });
    };

    // fix round 1, F2 (probe-confirmed) — SAVE-THEN-PUBLISH, unchanged: a dirty editor PATCHes
    // first and publish is only dispatched after that PATCH succeeds, so phase-3 never embeds a
    // stale stored body. task-19: the intermediate PATCH stays silent.
    const publishFlow = async () => {
      if (!contentId) {
        return;
      }
      if (isDirty) {
        const patch = buildPatch();
        if (!patch) {
          return;
        }
        const saved = await withFeedback(() => updateContent({ id: contentId, patch }).unwrap(), {
          errorFallback: SAVE_ERROR_FALLBACK,
        });
        if (saved === undefined) {
          return;
        }
      }
      await withFeedback(() => publishContent(contentId).unwrap(), {
        success: CONTENT_PUBLISHED_MESSAGE,
        errorFallback: TRANSITION_ERROR_FALLBACK,
      });
    };

    const onPublish = () => {
      void publishFlow();
    };

    const onArchive = () => {
      if (!contentId) {
        return;
      }
      void withFeedback(() => archiveContent(contentId).unwrap(), {
        success: CONTENT_ARCHIVED_MESSAGE,
        errorFallback: TRANSITION_ERROR_FALLBACK,
      });
    };
  ```

  Preserve every guard and ordering the existing five blocks have (e.g. the existing
  `onSubmit`'s exact preconditions, whether the create path's redirect happens before or after
  the notice); the code above is the shape, the existing pins are the contract.
  `isDirty` (lines 165-176) is **not** touched — t19 M3 already landed as p8 final F7. The
  `beforeunload` effect, the `useRisingEdgeNotice` block, `buildPatch`, `setTagsNormalized` and
  the seeding-during-render block are unchanged.

- [ ] **Step 9 (implementer): run GREEN + gates.**
  `cd apps/admin && npx vitest run ContentEditorScreen useTitleValidation` → all green, then the
  full `cd apps/admin && npx vitest run`, `pnpm -C apps/admin type-check`,
  `pnpm -C apps/admin lint` (zero errors AND zero warnings), `pnpm -C apps/admin format:check`.
  (`pnpm -C apps/admin test -- <filter>` **drops the filter** — use `npx vitest run`.)

- [ ] **Step 10 (implementer): commit.**
  `git commit -m "refactor(admin): editor hook — withFeedback, title-validation + delete hooks, shared test harness (p8 t19 M1/M2/M3, t20 M4)"`

## Acceptance criteria

- `wc -l apps/admin/src/components/content/ContentEditorScreen/useContentEditor.ts` ≤ **325**
  (375 today; see the ruling above for why ≤ 300 is not reachable).
- `UseContentEditorResult` is byte-identical field-for-field to the list in Context, still declared
  in `useContentEditor.ts`; `components/EditorForm/interface.ts` is untouched and
  `pnpm -C apps/admin type-check` is clean.
- No `.then(...).catch(...)` feedback chain remains in `useContentEditor.ts`.
- The pinned feedback matrix still holds, including **save-then-publish emitting only "Published"**
  (`feedback.test.tsx` "a successful Publish shows a 'Published' notice (and not a 'Saved' one)")
  and a PATCH failure blocking publish (`publishGuard.test.tsx`).
- `git diff` shows **no change inside any `describe`/`it` body** of `Component.test.tsx`,
  `responsivePreview.test.tsx`, `useContentEditor.test.tsx` or `feedback.test.tsx` — only preambles
  plus the appended new cases; the same test names run before and after, with three more.
- `git diff --stat` does not list `Component.tsx`, `components/**`, `publishGuard.test.tsx`,
  `resilientRefetch.test.tsx`, `tagBlurCapture.test.tsx`, `tagOrderDirty.test.tsx` or
  `chipDeletePreservesTyping.test.tsx`.
- `testing/renderEditor.tsx` contains no `vi.mock` call.
- Full admin gate green: `pnpm -C apps/admin type-check && pnpm -C apps/admin lint &&
  pnpm -C apps/admin format:check && cd apps/admin && npx vitest run`.

## Report

- Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-07-test-author.md`: the
  before/after summary lines for the harness migration (identical test counts and names), the RED
  command + pasted failure lines for `useTitleValidation.test.tsx`, and an explicit statement that
  the M3 guard pin and the two Archive cases were green on arrival (with the optional reverted-trim
  RED evidence and a `git status` clean line if that route was taken).
- Implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-07-implementer.md`: the GREEN
  command + pasted summary lines for the focused and full runs, the four gate command outputs, and
  `wc -l` for `useContentEditor.ts` before and after.
