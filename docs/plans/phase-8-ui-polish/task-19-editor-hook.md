---
id: p8-t19
phase: phase-8-ui-polish
depends_on: [p8-t18]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 19 — Editor hook: title validation, dirty guard, global snackbar, tag suggestions, header data (C5, hook half)

## Goal

`useContentEditor` gains everything task 20's screen needs and loses its private snackbar:
required-title validation (error after blur or a blank submit; the saved title is trimmed), an
`isDirty` flag that also drives a `beforeunload` guard, success/error feedback through
`useSnackbar()` ("Saved" / "Published" / "Archived" / "Deleted"), tag suggestions from
`GET /tags`, and the loaded record's header fields (saved title, slug, status, created/updated/
published). The screen changes only enough to compile (its `AppSnackbar` block goes), and the
now-unused `AppSnackbar` primitive is deleted.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §5 C5 (Form, Feedback, Dirty guard bullets;
  plan-time ruling: the header title is the SAVED title from the record, not the live field).
- `docs/FRONTEND-CONVENTIONS.md` §3 (VM hook owns state/validation), §7, §9.
- `apps/admin/src/components/content/ContentEditorScreen/{useContentEditor.ts, Component.tsx,
  Component.test.tsx, publishGuard.test.tsx, resilientRefetch.test.tsx, tagBlurCapture.test.tsx,
  tagOrderDirty.test.tsx, chipDeletePreservesTyping.test.tsx}` — read the hook fully; the six
  test files are NOT modified (their `vi.mock('next/navigation', …)` idiom is copied into the
  new hook test); their pins that touch feedback are listed under "Pins that must stay green".
- `apps/admin/src/components/common/SnackbarProvider/{interface.ts, Component.tsx}`
  (`useSnackbar(): { success, error }`), `common/AppSnackbar/*` (deleted here), `common/index.ts`.
- `apps/admin/src/lib/api/{contentApi.ts, tagsApi.ts}` (`useListTagsQuery` → `TagDto[]` with
  `name`), `apps/admin/src/lib/{copy.ts, errorMessage.ts}`, `types/api/content.ts`
  (`ContentDto` has `created_at`, `updated_at`, `published_at`, `slug`, `status`).

## Files

**Create**
- `src/components/content/ContentEditorScreen/useContentEditor.test.tsx`
- `src/components/content/ContentEditorScreen/feedback.test.tsx`

**Modify**
- `src/components/content/ContentEditorScreen/useContentEditor.ts`
- `src/components/content/ContentEditorScreen/Component.tsx` (only: drop the `AppSnackbar`
  element + import; everything else waits for task 20)
- `src/components/common/index.ts` (drop the `AppSnackbar` exports)
- `src/lib/copy.ts`

**Delete**
- `src/components/common/AppSnackbar/` (whole folder incl. `Component.test.tsx`,
  `clickaway.test.tsx`) — tasks 17 and 18 retired the other call sites; grep must show zero
  imports before deleting.

## Interfaces

```ts
// src/lib/copy.ts additions (the four hook-local fallbacks move here too)
export const TITLE_REQUIRED_MESSAGE = 'Title is required';
export const CONTENT_SAVED_MESSAGE = 'Saved';
export const CONTENT_PUBLISHED_MESSAGE = 'Published';
export const CONTENT_ARCHIVED_MESSAGE = 'Archived';
// CONTENT_DELETED_MESSAGE ('Deleted') and DELETE_ERROR_FALLBACK already exist (task 18)
export const SAVE_ERROR_FALLBACK = "Couldn't save this item. Please try again.";
export const TRANSITION_ERROR_FALLBACK = "Couldn't update this item's status. Please try again.";
export const EDITOR_REFRESH_ERROR = "Couldn't refresh this item — showing the last loaded version.";
export const EDITOR_LOAD_ERROR = "Couldn't load this item.";

// useContentEditor.ts — full result shape after this task
export interface UseContentEditorResult {
  mode: 'new' | 'edit';
  isLoading: boolean;
  isError: boolean;
  hasContent: boolean;
  /** Header data from the loaded record (edit mode); null in new mode / before load. */
  savedTitle: string | null;
  slug: string | null;
  status: ContentStatus | null;
  createdAt: string | null;
  updatedAt: string | null;
  publishedAt: string | null;
  title: string;
  setTitle: (value: string) => void;
  /** TITLE_REQUIRED_MESSAGE once the field was blurred or a submit was attempted while blank; null otherwise. */
  titleError: string | null;
  onTitleBlur: () => void;
  body: string;
  setBody: (value: string) => void;
  tags: string[];
  setTags: (value: string[]) => void;
  /** Existing tag names (GET /tags) for the Autocomplete; [] until loaded or on failure. */
  tagOptions: string[];
  /** New mode: any field non-empty. Edit mode: differs from the loaded record (order-insensitive tags). */
  isDirty: boolean;
  submitLabel: 'Create' | 'Save';
  canSubmit: boolean;              // unchanged rule: new → title.trim() non-empty; edit → isDirty
  isSaving: boolean;
  onSubmit: () => void;            // blank (trimmed) title → titleError set, NO request; payload/patch title is trimmed
  canPublish: boolean;
  canArchive: boolean;
  isTransitioning: boolean;
  onPublish: () => void;
  onArchive: () => void;
  isDeleting: boolean;
  deleteDialogOpen: boolean;
  deleteError: string | null;
  openDeleteDialog: () => void;
  closeDeleteDialog: () => void;
  confirmDelete: () => void;
  previewOpen: boolean;
  togglePreview: () => void;
}
// REMOVED: snackbarMessage, closeSnackbar.
// Feedback (useSnackbar()): create ok → success(CONTENT_SAVED_MESSAGE) then router.push; PATCH ok →
// success(CONTENT_SAVED_MESSAGE); publish ok → success(CONTENT_PUBLISHED_MESSAGE) (save-then-publish
// emits ONLY "Published"); archive ok → success(CONTENT_ARCHIVED_MESSAGE); delete ok →
// success(CONTENT_DELETED_MESSAGE) then router.push('/content'); save/transition failures →
// error(extractErrorMessage(err, …FALLBACK)); delete failure stays in the dialog (deleteError, as today).
// Background refetch failure (mode edit && hasContent && isError) → error(EDITOR_REFRESH_ERROR) once per
// episode: an effect on that boolean firing on its false → true edge.
// Dirty guard (exact):
//   useEffect(() => {
//     if (!isDirty) return;
//     const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
//     window.addEventListener('beforeunload', guard);
//     return () => window.removeEventListener('beforeunload', guard);
//   }, [isDirty]);
//   // In-app navigation is NOT blocked: the App Router has no supported blocker (DESIGN.md §C5) —
//   // say so in a comment above the effect.
```

**Pins that must stay green (no edits to those files):** `Component.test.tsx` "a failed save
(PATCH → 500) surfaces the envelope message as an alert" (the global snackbar's error notice
is `role="alert"`); `publishGuard.test.tsx` "a PATCH failure blocks publish … shown as an
alert"; `resilientRefetch.test.tsx` both cases — the second one's failure → dismiss → success
→ failure sequence holds under the rising-edge rule because the successful refetch in between
resets the edge; `tagOrderDirty`, `tagBlurCapture`, `chipDeletePreservesTyping` (untouched
behaviour).

## Steps (TDD)

- [ ] **RED — test-author.**

**`useContentEditor.test.tsx`** (hook-level, `Providers` wrapper, fetch at the edge)

```tsx
// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { useContentEditor } from './useContentEditor';

const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

function Wrapper({ children }: { children: ReactNode }) {
  return <Providers>{children}</Providers>;
}

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

async function requestBody(input: RequestInfo | URL, init?: RequestInit): Promise<unknown> {
  if (input instanceof Request) return input.clone().json();
  return JSON.parse(String(init?.body));
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const draftFixture: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics\n\nBody.',
  created_at: '2026-01-01T12:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-03-15T12:00:00Z',
  updated_by: null,
};

type Handler = (url: URL, method: string, input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>;

function mockFetch(handler: Handler) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => handler(new URL(requestUrl(input)), requestMethod(input, init), input, init),
  );
  global.fetch = fetchMock;
  return fetchMock;
}

const editHandler: Handler = (url, method) => {
  if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'GET') return jsonResponse(draftFixture);
  if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'PATCH') return jsonResponse(draftFixture);
  if (url.pathname === '/api/v1/tags') return jsonResponse([{ id: 't1', name: 'retirement', count: 2 }, { id: 't2', name: 'tax-planning', count: 1 }]);
  return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
};

describe('useContentEditor', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    pushMock.mockClear();
  });

  it('new mode: titleError appears after blurring a blank title and clears once typed', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    expect(result.current.titleError).toBeNull();
    act(() => result.current.onTitleBlur());
    expect(result.current.titleError).toBe('Title is required');

    act(() => result.current.setTitle('A title'));
    expect(result.current.titleError).toBeNull();
  });

  it('new mode: onSubmit with a blank title sets titleError and sends no request', () => {
    const fetchMock = mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    act(() => result.current.setTitle('   '));
    act(() => result.current.onSubmit());

    expect(result.current.titleError).toBe('Title is required');
    expect(fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'POST')).toBe(false);
  });

  it('new mode: isDirty is false on a blank form and true once any field has content', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    expect(result.current.isDirty).toBe(false);
    act(() => result.current.setBody('draft text'));
    expect(result.current.isDirty).toBe(true);
    act(() => result.current.setBody(''));
    expect(result.current.isDirty).toBe(false);
  });

  it('installs a beforeunload guard only while dirty', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    const clean = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    act(() => result.current.setTitle('Unsaved'));
    const dirty = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);

    act(() => result.current.setTitle(''));
    const cleanAgain = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(cleanAgain);
    expect(cleanAgain.defaultPrevented).toBe(false);
  });

  it('edit mode: exposes the record\'s header fields; savedTitle stays the saved value while the field changes', async () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({ contentId: draftFixture.id }), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.hasContent).toBe(true));
    expect(result.current.savedTitle).toBe(draftFixture.title);
    expect(result.current.slug).toBe(draftFixture.slug);
    expect(result.current.status).toBe('draft');
    expect(result.current.createdAt).toBe(draftFixture.created_at);
    expect(result.current.updatedAt).toBe(draftFixture.updated_at);
    expect(result.current.publishedAt).toBeNull();

    act(() => result.current.setTitle('Renamed'));
    expect(result.current.savedTitle).toBe(draftFixture.title);
    expect(result.current.isDirty).toBe(true);
  });

  it('edit mode: the saved title is trimmed in the PATCH body', async () => {
    const fetchMock = mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({ contentId: draftFixture.id }), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.hasContent).toBe(true));

    act(() => result.current.setTitle('  Trimmed title  '));
    act(() => result.current.onSubmit());

    await waitFor(async () => {
      const patch = fetchMock.mock.calls.find(([input, init]) => requestMethod(input, init) === 'PATCH');
      expect(patch).toBeDefined();
      expect(await requestBody(patch![0], patch![1])).toEqual({ title: 'Trimmed title' });
    });
  });

  it('tagOptions come from GET /tags', async () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.tagOptions).toEqual(['retirement', 'tax-planning']));
  });

  it('no longer exposes a private snackbar', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    expect('snackbarMessage' in result.current).toBe(false);
    expect('closeSnackbar' in result.current).toBe(false);
  });
});
```

**`feedback.test.tsx`** (screen-level, one-behaviour file; copy the `draftFixture`,
`jsonResponse`, `requestUrl`, `requestMethod`, `pushMock`/`vi.mock` block from the file above
and the `renderEdit`/`renderNew` helpers from `Component.test.tsx`)

```tsx
describe('ContentEditorScreen mutation feedback (global snackbar)', () => {
  it('a successful Save shows a "Saved" notice', async () => {
    mockFetch(editHandler);
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByRole('status')).toHaveTextContent('Saved');
  });

  it('a successful Publish shows a "Published" notice (and not a "Saved" one)', async () => {
    mockFetch((url, method) => {
      if (url.pathname === `/api/v1/content/${draftFixture.id}/publish` && method === 'POST') {
        return jsonResponse({ ...draftFixture, status: 'published', published_at: '2026-03-16T12:00:00Z' });
      }
      return editHandler(url, method, url);
    });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    await user.click(await screen.findByRole('button', { name: /publish/i }));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('Published');
    expect(status).not.toHaveTextContent('Saved');
  });

  it('a successful Create shows "Saved" and routes to the new item', async () => {
    mockFetch((url, method) => {
      if (url.pathname === '/api/v1/content' && method === 'POST') {
        return jsonResponse({ ...draftFixture, id: '22222222-2222-2222-2222-222222222222' }, 201);
      }
      return editHandler(url, method, url);
    });
    const user = userEvent.setup();

    renderNew();
    await user.type(screen.getByRole('textbox', { name: /title/i }), 'New Piece');
    await user.click(screen.getByRole('button', { name: /create/i }));

    expect(await screen.findByRole('status')).toHaveTextContent('Saved');
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/content/22222222-2222-2222-2222-222222222222'));
  });

  it('a confirmed Delete shows "Deleted" and routes to the list', async () => {
    mockFetch((url, method) => {
      if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      return editHandler(url, method, url);
    });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    await user.click(await screen.findByRole('button', { name: /delete/i }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /delete/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/content'));
    expect(await screen.findByRole('status')).toHaveTextContent('Deleted');
  });
});
```

(`editHandler`'s 4-arg signature lets the screen tests reuse it with a 3-arg call — the
test-author may simplify the `Handler` type to `(url, method) => Response` in both files if
the extra args are unused; keep the two files consistent.)

- [ ] **Run RED:** `pnpm -C apps/admin test -- ContentEditorScreen` → the hook test fails on
  every new field (`titleError`, `onTitleBlur`, `isDirty`, `savedTitle`, …, `tagOptions`) and
  the "no private snackbar" case; `feedback.test.tsx` fails (no `role="status"` notice today —
  `AppSnackbar` only renders errors here); `pnpm -C apps/admin type-check` reports the new
  fields. The six existing files stay green.

- [ ] **GREEN — implementer:** copy → hook → minimal screen edit → delete `AppSnackbar` +
  barrel exports (`grep -rn AppSnackbar apps/admin/src` must be empty first).

- [ ] **Run GREEN:** `pnpm -C apps/admin test` (all eight editor files + the rest);
  `pnpm -C apps/admin type-check`.

- [ ] **Gates:** `pnpm gates:admin` → clean. No screenshots (hook task; the screen is task 20).

- [ ] **Commit:**
  `git add apps/admin/src/components/content/ContentEditorScreen apps/admin/src/components/common/index.ts apps/admin/src/lib/copy.ts`
  `git rm -r apps/admin/src/components/common/AppSnackbar`
  `git commit -m "feat(admin): editor hook — title validation, dirty guard, global snackbar, tag options (p8 t19)"`

## Verify

```bash
pnpm -C apps/admin test -- ContentEditorScreen
grep -rn "AppSnackbar" apps/admin/src   # must print nothing
pnpm gates:admin
```

## Acceptance

- `titleError`/`onTitleBlur`/`isDirty`/`tagOptions`/header fields exported and tested; blank
  submit sends nothing; title trimmed on save; `beforeunload` guard only while dirty.
- Every mutation reports through `useSnackbar()` with the exact copy; the six pre-existing
  editor test files pass unmodified.
- `AppSnackbar` deleted from the codebase.
