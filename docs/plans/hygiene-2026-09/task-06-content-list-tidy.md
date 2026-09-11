---
id: hy-t06
phase: hygiene-2026-09
depends_on: []
status: todo
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: opus
---

# Task 06 — Content list tidy: whitespace `q`, URL canonicalisation, delete-confirmation hook, import order

## Goal

Close the four deferred Minors from the phase-8 task-18 Opus review, verbatim from the ledger:
**M1** "whitespace-only q cosmetics", **M2** "unknown status not canonicalised out of the URL",
**M6** "`Component.tsx` 154 lines — extract a delete-confirmation hook", **M7** "import grouping".
No visible redesign: the table, filters, empty states and the delete flow all behave exactly as
today apart from what M1/M2 explicitly correct.

## Context (read ONLY these)

- `apps/admin/src/components/content/ContentListScreen/{Component.tsx, useContentList.ts,
  useContentList.test.tsx, Component.test.tsx, pagination.test.tsx, deleteError.test.tsx,
  newContentLink.test.tsx, resilientRefetch.test.tsx, components/**}`.
- `apps/admin/src/lib/contentListParams.ts` + `apps/admin/src/lib/contentListParams.test.ts`.
- `apps/admin/src/testing/nextNavigation.ts` (stateful `next/navigation` seam: `navigation.reset`,
  `navigation.replace` spy, `navigation.search`) and `nextNavigation.test.tsx` for the idiom.
- `docs/FRONTEND-CONVENTIONS.md` §3 (folder-per-component, hooks colocated and flat, UI dumb),
  §7 (TDD; mock ONLY fetch + `next/navigation`), §9.
- `docs/plans/phase-8-ui-polish/DESIGN.md` §5 C4 + the C4 plan-time ruling (URL is the single
  source of truth; `lib/contentListParams.ts` is the only parse/build boundary).

**Current behaviour, observed at the time of writing** (line numbers are HEAD of
`chore/hygiene-ride` before this task; task 03 may have shifted `Component.test.tsx` slightly):

- M1: `parseContentListParams` already trims `q` (`contentListParams.ts:40`), so a whitespace-only
  term **never reaches the request** (`useContentList.ts:103` sends `q: params.q || undefined`).
  But the debounce timer writes the **raw** field value — `write({ ...paramsRef.current, q: qInput,
  page: 1 })` (`useContentList.ts:94`) — and `buildContentListSearch` only tests truthiness
  (`contentListParams.ts:55`), so typing three spaces puts **`/content?q=+++`** in the address bar
  (`URLSearchParams` encodes a space as `+`). The URL then re-parses to `q: ''`, so the echo-sync
  effect (`useContentList.ts:71-76`) sees `params.q ('') !== lastWrittenQ.current ('   ')` and calls
  `setQInput('')` — **the search box the admin is typing in is wiped 300 ms later**. The same wipe
  happens for a trailing space (`"roth "` snaps back to `"roth"` mid-typing).
- M2: `?status=bogus` parses to `status: ''` (`contentListParams.ts:23-25`), so the filter is "all"
  and the request carries no `status` — but nothing rewrites the URL, so the address bar keeps
  `?status=bogus`. Same for `page=0`/`page=abc` (parsed to 1) and a whitespace-only `tag`.
- M2 idiom reuse: the WR-60 clamp (`useContentList.ts:111-120`) is already exactly the idiom we
  need — **one effect keyed on the input it corrects, whose own `write` makes the condition false,
  no ref guard and no loop** (the t18 reviewer called it "clamp single-shot, loop-free"). The
  canonicalisation effect **reuses that shape verbatim**; only its key differs (the raw search
  string instead of `[data, params.page]`).
- M6: `Component.tsx` is 157 lines and owns `useState<ContentDto | null>` plus three handlers.
- M7: `useContentList.ts:15` (`import type { ContentListParams }`) sits after the `@/types` import
  instead of beside its own module; `Component.tsx:15-28` lists `CONTENT_TITLE` before
  `CLEAR_FILTERS_LABEL`.

**Rulings for this task (controller; do not re-open):**
- An **unknown tag** (a tag name with no matching content) is NOT canonicalised out — tag values are
  server data, the filter legitimately sends them, and the result is the "no match" empty state.
  Only an **empty/whitespace-only** tag is removed.
- Canonicalisation also normalises key ORDER to `status,tag,q,page` and drops stray keys — blessed:
  `lib/contentListParams.ts` is the single parse/build boundary, so any future param is added
  there first. Accepted and pinned: one extra `router.replace` on a non-canonical deep link,
  `{ scroll: false }`, no history entry.
- `tagOptions` (the `useListTagsQuery` + mapping in `Component.tsx:59-65`) stays in the component.
  Moving it into `useContentList` is out of scope for this task.

## Files

**Create**
- `apps/admin/src/components/content/ContentListScreen/useDeleteConfirmation.ts`
- `apps/admin/src/components/content/ContentListScreen/useDeleteConfirmation.test.tsx`

**Modify**
- `apps/admin/src/lib/contentListParams.ts` + `apps/admin/src/lib/contentListParams.test.ts`
- `apps/admin/src/components/content/ContentListScreen/useContentList.ts`
- `apps/admin/src/components/content/ContentListScreen/useContentList.test.tsx`
- `apps/admin/src/components/content/ContentListScreen/Component.tsx`

**Delete** — none.

## Interfaces

```ts
// src/lib/contentListParams.ts — buildContentListSearch trims tag/q (M1, defence in depth:
// no code path can emit a blank-looking param), plus one new pure predicate (M2).
export function buildContentListSearch(params: ContentListParams): string {
  const query = new URLSearchParams();
  const tag = params.tag.trim();
  const q = params.q.trim();
  if (params.status) {
    query.set('status', params.status);
  }
  if (tag) {
    query.set('tag', tag);
  }
  if (q) {
    query.set('q', q);
  }
  if (params.page !== DEFAULT_CONTENT_LIST_PARAMS.page) {
    query.set('page', String(params.page));
  }

  const search = query.toString();
  return search ? `?${search}` : '';
}

// hygiene t06 M2: `true` when `search` is exactly what `buildContentListSearch` would produce for
// the params it parses to — i.e. it carries no unknown `status`, no unusable `page`, no untrimmed
// `tag`/`q`, no stray key and no non-canonical key order.
export function isCanonicalContentListSearch(search: URLSearchParams): boolean {
  const raw = search.toString();
  return buildContentListSearch(parseContentListParams(search)) === (raw ? `?${raw}` : '');
}

// src/components/content/ContentListScreen/useDeleteConfirmation.ts (M6)
export interface UseDeleteConfirmationArgs {
  /** `useContentList().deleteContent` — owns the mutation, the "Deleted" notice and `deleteError`. */
  deleteContent: (id: string) => Promise<void>;
  /** `useContentList().clearDeleteError`. */
  clearDeleteError: () => void;
}

export interface UseDeleteConfirmationResult {
  /** The row awaiting confirmation, or `null` when the dialog is closed. */
  target: ContentDto | null;
  isOpen: boolean;
  open: (item: ContentDto) => void;
  close: () => void;
  /** Resolves either way: a failure is swallowed here and surfaced by `deleteError` inside the
   *  still-open dialog (unchanged from today's `Component.tsx` catch). */
  confirm: () => Promise<void>;
}

export function useDeleteConfirmation(args: UseDeleteConfirmationArgs): UseDeleteConfirmationResult;

// UseContentListResult is UNCHANGED by this task — no field added, removed or renamed.
```

## Steps

- [ ] **Step 1 (test-author, RED): `src/lib/contentListParams.test.ts`** — append two cases; do not
  touch the four existing ones. Add `isCanonicalContentListSearch` to the import list.

  ```ts
    it('never writes a whitespace-only tag or q into the search string (hygiene t06 M1)', () => {
      expect(buildContentListSearch({ status: '', tag: '   ', q: '   ', page: 1 })).toBe('');
      expect(buildContentListSearch({ status: '', tag: ' retirement ', q: ' roth ', page: 1 })).toBe(
        '?tag=retirement&q=roth',
      );
    });

    it('recognises a canonical search string (hygiene t06 M2)', () => {
      expect(isCanonicalContentListSearch(new URLSearchParams(''))).toBe(true);
      expect(isCanonicalContentListSearch(new URLSearchParams('status=draft&tag=a&q=b&page=2'))).toBe(
        true,
      );
      expect(isCanonicalContentListSearch(new URLSearchParams('status=bogus'))).toBe(false);
      expect(isCanonicalContentListSearch(new URLSearchParams('page=0'))).toBe(false);
      expect(isCanonicalContentListSearch(new URLSearchParams('page=abc'))).toBe(false);
      expect(isCanonicalContentListSearch(new URLSearchParams('page=1'))).toBe(false);
      expect(isCanonicalContentListSearch(new URLSearchParams('tag=%20%20'))).toBe(false);
      expect(isCanonicalContentListSearch(new URLSearchParams('q=roth&status=draft'))).toBe(false);
      expect(isCanonicalContentListSearch(new URLSearchParams('sort=title'))).toBe(false);
    });
  ```

- [ ] **Step 2 (test-author, RED): append six cases to `useContentList.test.tsx`.** The harness
  (`Wrapper`, `jsonResponse`, `requestUrl`, `emptyPage`, `mockList`, the `vi.mock` + `beforeEach`
  seam) already exists at the top of that file — reuse it, add nothing to it. No existing case in
  this file changes.

  ```tsx
    it('never writes a whitespace-only search term to the URL or the request (M1)', async () => {
      const fetchMock = mockList(() => emptyPage(0, 1));
      const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

      act(() => result.current.setQ('   '));

      // Real timers: wait past the hook's 300 ms debounce and prove nothing was ever written.
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 600));
      });

      expect(navigation.replace).not.toHaveBeenCalled();
      expect(navigation.search).toBe('');
      expect(result.current.q).toBe('   ');
      expect(
        fetchMock.mock.calls.every(
          ([input]) => new URL(requestUrl(input)).searchParams.get('q') === null,
        ),
      ).toBe(true);
    });

    it('trims the search term before writing it to the URL and leaves the field as typed (M1)', async () => {
      mockList(() => emptyPage(0, 1));
      const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

      act(() => result.current.setQ('  roth  '));

      await waitFor(
        () =>
          expect(navigation.replace).toHaveBeenLastCalledWith('/content?q=roth', { scroll: false }),
        { timeout: 2000 },
      );
      expect(navigation.replace).toHaveBeenCalledTimes(1);
      expect(result.current.q).toBe('  roth  ');
    });

    it('blanking a term with whitespace clears the q param instead of writing blanks (M1)', async () => {
      mockList(() => emptyPage(0, 1));
      navigation.reset('/content?q=roth');
      const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

      act(() => result.current.setQ('   '));

      await waitFor(
        () => expect(navigation.replace).toHaveBeenLastCalledWith('/content', { scroll: false }),
        { timeout: 2000 },
      );
      expect(navigation.search).toBe('');
      expect(result.current.hasFilters).toBe(false);
    });

    it('canonicalises an unknown status out of the URL on first parse (M2)', async () => {
      navigation.reset('/content?status=bogus');
      mockList(() => emptyPage(0, 1));

      const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

      await waitFor(() =>
        expect(navigation.replace).toHaveBeenCalledWith('/content', { scroll: false }),
      );
      expect(navigation.search).toBe('');
      expect(result.current.status).toBe('');
      expect(result.current.hasFilters).toBe(false);
    });

    it('canonicalising keeps the usable filters and drops only the unusable parts (M2)', async () => {
      navigation.reset('/content?q=roth&status=bogus&tag=retirement&page=0');
      mockList(() => emptyPage(0, 1));

      renderHook(() => useContentList(), { wrapper: Wrapper });

      await waitFor(() =>
        expect(navigation.replace).toHaveBeenCalledWith('/content?tag=retirement&q=roth', {
          scroll: false,
        }),
      );
    });

    it('leaves an already-canonical URL untouched (M2)', async () => {
      navigation.reset('/content?status=published&tag=retirement&q=roth&page=2');
      mockList((url) => emptyPage(100, Number(url.searchParams.get('page') ?? 1)));

      const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

      await waitFor(() => expect(result.current.hasData).toBe(true));
      expect(navigation.replace).not.toHaveBeenCalled();
    });
  ```

  If `mockList`'s callback signature or `emptyPage`'s arguments differ from what these cases
  assume, adapt the *call* to the existing harness (never the harness) and note it in the report.

- [ ] **Step 3 (test-author, RED): new `useDeleteConfirmation.test.tsx`.** Hook-level, driven
  against a REAL `useContentList` — only the network edge is mocked (§7); no stubbed collaborator.

  ```tsx
  // @vitest-environment jsdom
  import { act, renderHook, screen, waitFor } from '@testing-library/react';
  import '@testing-library/jest-dom/vitest';
  import type { ReactNode } from 'react';
  import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

  import Providers from '@/app/providers';
  import { navigation } from '@/testing/nextNavigation';
  import type { ContentDto, ContentListDto } from '@/types/api/content';

  import { useContentList } from './useContentList';
  import { useDeleteConfirmation } from './useDeleteConfirmation';

  vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

  // hygiene t06 M6: the delete-confirmation state that used to live in this screen's
  // Component.tsx (which row is pending deletion, open/close, confirm -> mutation -> snackbar)
  // moves into this colocated hook. RED today: the module does not exist.
  function Wrapper({ children }: { children: ReactNode }) {
    return <Providers>{children}</Providers>;
  }

  function useHarness() {
    const list = useContentList();
    const confirmation = useDeleteConfirmation({
      deleteContent: list.deleteContent,
      clearDeleteError: list.clearDeleteError,
    });
    return { list, confirmation };
  }

  function requestUrl(input: RequestInfo | URL): string {
    return input instanceof Request ? input.url : String(input);
  }

  function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
    return input instanceof Request ? input.method : (init?.method ?? 'GET');
  }

  function pathnameOf(input: RequestInfo | URL): string {
    return new URL(requestUrl(input)).pathname;
  }

  function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const itemA: ContentDto = {
    author_id: null,
    body_md: '# Roth IRA Conversion Basics',
    created_at: '2026-01-01T00:00:00Z',
    id: '11111111-1111-1111-1111-111111111111',
    published_at: null,
    slug: 'roth-ira-conversion-basics',
    status: 'draft',
    tags: [],
    title: 'Roth IRA Conversion Basics',
    updated_at: '2026-03-15T00:00:00Z',
    updated_by: null,
  };

  const itemB: ContentDto = {
    ...itemA,
    id: '22222222-2222-2222-2222-222222222222',
    slug: 'estate-planning-101',
    title: 'Estate Planning 101',
  };

  const listFixture: ContentListDto = { items: [itemA, itemB], page: 1, page_size: 20, total: 2 };

  const DELETE_FAILURE_MESSAGE = 'Could not delete due to a database hiccup.';
  const deleteOk = () => new Response(null, { status: 204 });
  const deleteFails = () =>
    jsonResponse({ error: { code: 'internal_error', message: DELETE_FAILURE_MESSAGE } }, 500);

  function mockFetch(deleteResponse: (attempt: number) => Response) {
    let attempts = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/content' && method === 'GET') {
          return jsonResponse(listFixture);
        }
        if (pathname.startsWith('/api/v1/content/') && method === 'DELETE') {
          attempts += 1;
          return deleteResponse(attempts);
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    return fetchMock;
  }

  describe('useDeleteConfirmation', () => {
    beforeEach(() => {
      navigation.reset('/content');
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('open(item) arms the dialog for that row and close() disarms it', async () => {
      mockFetch(deleteOk);
      const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
      await waitFor(() => expect(result.current.list.hasData).toBe(true));

      expect(result.current.confirmation.isOpen).toBe(false);
      expect(result.current.confirmation.target).toBeNull();

      act(() => result.current.confirmation.open(itemB));
      expect(result.current.confirmation.isOpen).toBe(true);
      expect(result.current.confirmation.target).toEqual(itemB);

      act(() => result.current.confirmation.close());
      expect(result.current.confirmation.isOpen).toBe(false);
      expect(result.current.confirmation.target).toBeNull();
    });

    it('confirm() deletes the armed row, disarms the dialog and reports through the snackbar', async () => {
      const fetchMock = mockFetch(deleteOk);
      const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
      await waitFor(() => expect(result.current.list.hasData).toBe(true));

      act(() => result.current.confirmation.open(itemA));
      await act(async () => {
        await result.current.confirmation.confirm();
      });

      const deleteCall = fetchMock.mock.calls.find(
        ([input, init]) => requestMethod(input, init) === 'DELETE',
      );
      expect(deleteCall).toBeDefined();
      expect(pathnameOf(deleteCall![0])).toBe(`/api/v1/content/${itemA.id}`);
      expect(result.current.confirmation.isOpen).toBe(false);
      // The skeleton also uses role="status" on this screen — query the notice by its text.
      expect(await screen.findByText('Deleted')).toBeInTheDocument();
    });

    it('a failed confirm() keeps the row armed and leaves the message on the list hook', async () => {
      mockFetch(deleteFails);
      const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
      await waitFor(() => expect(result.current.list.hasData).toBe(true));

      act(() => result.current.confirmation.open(itemA));
      await act(async () => {
        await result.current.confirmation.confirm();
      });

      expect(result.current.confirmation.isOpen).toBe(true);
      expect(result.current.confirmation.target).toEqual(itemA);
      expect(result.current.list.deleteError).toBe(DELETE_FAILURE_MESSAGE);
    });

    it('arming another row clears the previous failure message', async () => {
      mockFetch((attempt) => (attempt === 1 ? deleteFails() : deleteOk()));
      const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
      await waitFor(() => expect(result.current.list.hasData).toBe(true));

      act(() => result.current.confirmation.open(itemA));
      await act(async () => {
        await result.current.confirmation.confirm();
      });
      expect(result.current.list.deleteError).toBe(DELETE_FAILURE_MESSAGE);

      act(() => result.current.confirmation.open(itemB));

      expect(result.current.list.deleteError).toBeNull();
      expect(result.current.confirmation.target).toEqual(itemB);
    });

    it('confirm() with no armed row resolves without touching the API', async () => {
      const fetchMock = mockFetch(deleteOk);
      const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
      await waitFor(() => expect(result.current.list.hasData).toBe(true));

      await act(async () => {
        await result.current.confirmation.confirm();
      });

      expect(
        fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'DELETE'),
      ).toBe(false);
    });
  });
  ```

  Verify against the real `useContentList` result before writing: the field names `hasData`,
  `deleteContent`, `clearDeleteError`, `deleteError` must exist with these semantics (the
  snackbar "Deleted" notice and the in-dialog `deleteError` are set by `useContentList` today).
  If a name differs, use the real one and say so in the report — the hook under test is new, the
  list hook is not changed by this task.

- [ ] **Step 4 (test-author): run RED and record it.**
  `cd apps/admin && npx vitest run contentListParams ContentListScreen`
  Expected: `useDeleteConfirmation.test.tsx` fails to resolve `./useDeleteConfirmation`;
  `contentListParams` fails the two new cases (`isCanonicalContentListSearch` is not exported —
  also a type-check error); `useContentList.test.tsx` fails all six new cases (today: `?q=+++`,
  `?q=++roth++`, no canonicalising `replace`). **Every pre-existing case in all six
  `ContentListScreen/*.test.tsx` files and the four pre-existing `contentListParams` cases stay
  green** — if any goes red, stop and report (stop rule). No test name changes in this task.

- [ ] **Step 5 (implementer, GREEN): `src/lib/contentListParams.ts`.** Apply the two Interfaces
  blocks (trim in `buildContentListSearch`, add `isCanonicalContentListSearch` at the end of the
  file, below `hasActiveFilters`).

- [ ] **Step 6 (implementer, GREEN): `useContentList.ts`.**
  1. **M7** — move line 15 (`import type { ContentListParams } from '@/lib/contentListParams';`) up
     so it sits directly under the value import from that same module (the `ContentStatus` /
     `ContentUpdateDto` pair in `ContentEditorScreen/useContentEditor.ts:27-28` is the precedent:
     external packages · blank · `@/` modules in path order, each module's value import followed by
     its type import · blank · relative imports). Final order:
     `next/navigation`, `react` — blank — `@/components/common`, `@/lib/api/contentApi`,
     `@/lib/contentListParams` (value), `@/lib/contentListParams` (type), `@/lib/copy`,
     `@/lib/errorMessage`, `@/types/api/content` (type). Add
     `isCanonicalContentListSearch` to the `@/lib/contentListParams` value import (alphabetically
     after `hasActiveFilters`).
  2. **M2** — insert directly after the `write` definition (currently lines 61-63):

     ```ts
     // hygiene t06 M2: an unusable param (unknown `status`, `page=0`/`page=abc`, a whitespace-only
     // `tag`/`q`, a stray key, or a non-canonical key order) is silently ignored by
     // `parseContentListParams`, so the address bar disagreed with the filters actually applied.
     // Same single-shot idiom as the WR-60 clamp below — one effect keyed on the input it
     // corrects, whose own write makes the condition false, so no ref guard and no loop.
     const rawSearch = searchParams.toString();
     useEffect(() => {
       if (!isCanonicalContentListSearch(searchParams)) {
         write(params);
       }
       // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only off the raw URL string.
     }, [rawSearch]);
     ```

     On a deep link that is both non-canonical and stranded (`?status=bogus&page=5`) this effect
     writes first and the clamp writes second — two `replace` calls, final URL correct.
  3. **M1** — the debounce effect (currently lines 88-98) compares and writes the **trimmed**
     value, so a whitespace-only term never schedules a write and a padded term is stored clean
     (the field keeps the raw text, because `lastWrittenQ` then matches `params.q`):

     ```ts
     useEffect(() => {
       // hygiene t06 M1: the URL gets the TRIMMED term. `'   '` is the same as empty (nothing is
       // written, the field keeps what was typed); `'  roth  '` writes `?q=roth` once.
       const trimmedQ = qInput.trim();
       if (trimmedQ === params.q) {
         return;
       }
       const timer = setTimeout(() => {
         lastWrittenQ.current = trimmedQ;
         write({ ...paramsRef.current, q: trimmedQ, page: 1 });
       }, SEARCH_DEBOUNCE_MS);
       return () => clearTimeout(timer);
       // eslint-disable-next-line react-hooks/exhaustive-deps
     }, [qInput, params.q]);
     ```

     Keep whatever `eslint-disable` line the existing effect already carries (it may differ from
     the one shown); the point is the trimmed compare-and-write.

- [ ] **Step 7 (implementer, GREEN): create `useDeleteConfirmation.ts`.**

  ```ts
  import { useState } from 'react';

  import type { ContentDto } from '@/types/api/content';

  // hygiene t06 M6 (phase-8 t18 review): the delete-confirmation state machine, lifted out of
  // ContentListScreen/Component.tsx so that file is composition only
  // (docs/FRONTEND-CONVENTIONS.md §3). The mutation itself, the "Deleted" notice and
  // `deleteError` stay in `useContentList` — this hook only decides WHICH row is pending and
  // WHEN the dialog is open, and it is handed the two callbacks it drives.
  export interface UseDeleteConfirmationArgs {
    deleteContent: (id: string) => Promise<void>;
    clearDeleteError: () => void;
  }

  export interface UseDeleteConfirmationResult {
    /** The row awaiting confirmation, or `null` when the dialog is closed. */
    target: ContentDto | null;
    isOpen: boolean;
    open: (item: ContentDto) => void;
    close: () => void;
    confirm: () => Promise<void>;
  }

  export function useDeleteConfirmation({
    deleteContent,
    clearDeleteError,
  }: UseDeleteConfirmationArgs): UseDeleteConfirmationResult {
    const [target, setTarget] = useState<ContentDto | null>(null);

    const open = (item: ContentDto) => {
      clearDeleteError();
      setTarget(item);
    };

    const close = () => {
      setTarget(null);
      clearDeleteError();
    };

    const confirm = async () => {
      if (!target) {
        return;
      }
      try {
        await deleteContent(target.id);
        setTarget(null);
      } catch {
        // `deleteError` (from useContentList) surfaces the failure inside the still-open
        // ConfirmDialog — the admin can retry immediately or cancel.
      }
    };

    return { target, isOpen: target !== null, open, close, confirm };
  }
  ```

  If today's `Component.tsx` handlers do something this hook does not (compare them line by
  line before deleting them — e.g. whether `deleteContent` itself throws on failure or resolves
  with the error stored), mirror the existing behaviour exactly and note the difference.

- [ ] **Step 8 (implementer, GREEN): `Component.tsx`.** Delete the `useState` import, the
  `import type { ContentDto }` line, the `deleteTarget` state and the three handlers
  (`handleDeleteClick`, `handleConfirmDelete`, `handleCloseDialog`). Add
  `import { useDeleteConfirmation } from './useDeleteConfirmation';` after the `./useContentList`
  import, and directly under the `useListTagsQuery` line:

  ```tsx
    const {
      target: deleteTarget,
      isOpen: isDeleteDialogOpen,
      open: openDeleteDialog,
      close: closeDeleteDialog,
      confirm: confirmDelete,
    } = useDeleteConfirmation({ deleteContent, clearDeleteError });
  ```

  Wire: `<ContentTable items={items} onDeleteClick={openDeleteDialog} />`, and on `ConfirmDialog`
  `open={isDeleteDialogOpen}`, `onConfirm={confirmDelete}`, `onClose={closeDeleteDialog}`
  (`body={deleteContentDialogBody(deleteTarget?.title ?? '')}` unchanged).
  **M7** — sort the `@/lib/copy` specifiers ASCII-ascending (uppercase before lowercase, the
  existing convention): `ALL_TAGS_LABEL, CLEAR_FILTERS_LABEL, CONTENT_LOAD_ERROR, CONTENT_TITLE,
  CREATE_FIRST_ARTICLE_LABEL, DELETE_CONTENT_DIALOG_TITLE, NEW_CONTENT_LABEL,
  NO_CONTENT_DESCRIPTION, NO_CONTENT_TITLE, NO_MATCH_DESCRIPTION, NO_MATCH_TITLE,
  deleteContentDialogBody`.

- [ ] **Step 9 (implementer): run GREEN + gates.**
  `cd apps/admin && npx vitest run contentListParams ContentListScreen` → all green, then
  `pnpm -C apps/admin type-check`, `pnpm -C apps/admin lint` (zero errors AND zero warnings),
  `pnpm -C apps/admin format:check`, and the full `cd apps/admin && npx vitest run`.
  (`pnpm -C apps/admin test -- <filter>` **drops the filter** — always use `npx vitest run` for a
  focused run.)

- [ ] **Step 10 (implementer): commit.**
  `git commit -m "refactor(admin): content list — trimmed q, canonical URL, delete-confirmation hook, import order (p8 t18 M1/M2/M6/M7)"`

## Acceptance criteria

- `?status=bogus` (and `page=0`, `page=abc`, `tag=%20%20`, a stray key, a non-canonical key order)
  is rewritten out of the address bar exactly once via `router.replace(..., { scroll: false })`;
  an already-canonical URL produces **zero** `replace` calls; an unknown *tag* is preserved.
- A whitespace-only search term never appears in the URL and never in a request query; a padded
  term is written trimmed; the search field keeps exactly what was typed in both cases.
- `useDeleteConfirmation.ts` exists next to `useContentList.ts` with the exact result shape above;
  `wc -l apps/admin/src/components/content/ContentListScreen/Component.tsx` ≤ **140** and
  `grep -n "useState" apps/admin/src/components/content/ContentListScreen/Component.tsx` prints
  nothing.
- `UseContentListResult` is unchanged (no field added/removed/renamed); the WR-60 clamp block is
  unchanged.
- Every pre-existing test in `ContentListScreen/` and `lib/contentListParams.test.ts` passes
  unmodified — `git diff` shows no deletion or edit inside any pre-existing `it(...)` block.
- Full admin gate green: `pnpm -C apps/admin type-check && pnpm -C apps/admin lint &&
  pnpm -C apps/admin format:check && cd apps/admin && npx vitest run`.

## Report

- Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-06-test-author.md`: the RED command
  and the pasted failure summary lines for all three files (module-not-found for
  `useDeleteConfirmation`, the `?q=+++` / `?q=++roth++` assertion diffs, the missing canonicalising
  `replace`), plus the pasted "pre-existing tests still green" summary line.
- Implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-06-implementer.md`: the GREEN
  command + pasted summary lines for the focused run and the full run, the four gate commands with
  their output lines, and `wc -l` for `Component.tsx`.
