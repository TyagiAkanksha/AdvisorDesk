// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// 6R task-11, WR-11 (DATA LOSS, verifier-confirmed via MUI 9.2 `useAutocomplete` source): this
// field is `multiple + freeSolo` with `autoSelect` at its library default (`false`) and
// `clearOnBlur` at ITS library default of `!freeSolo` — which, because this field passes
// `freeSolo`, evaluates to `false` too (`useAutocomplete.js` line 87). `handleBlur` only ever
// commits the typed text (the `autoSelect` branch) or clears it (the `clearOnBlur` branch); with
// both `false`, NEITHER branch runs on blur, so text typed but never confirmed with Enter is
// simply never folded into `value` — the array `onChange` reports, and therefore the array
// `useContentEditor.tags` (and the create/update payload) actually holds — while the same text
// stays visibly sitting in the input (worse than a visible loss). Fix (implementer, not this
// file): wire `onBlur` on `common/Autocomplete` to commit the live `inputValue` into `value`.
//
// This is a NEW, colocated one-behavior file — the existing pinned `Component.test.tsx` in this
// folder is untouched (same convention already used by
// `ContentListScreen/{pagination,deleteError,newContentLink,resilientRefetch}.test.tsx`).
//
// RED today: a network-edge assertion (FRONTEND-CONVENTIONS.md §7) on the captured POST body's
// `tags` array — 'retirement' is absent from it (dropped, not merely un-normalized) because the
// tag was only typed and blurred, never Entered. Mock ONLY the network edge (fetch) and the
// next/navigation framework seam, mirroring the pinned `Component.test.tsx` in this same folder.
const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

function pathnameOf(input: RequestInfo | URL): string {
  return new URL(requestUrl(input)).pathname;
}

async function requestJson(input: RequestInfo | URL): Promise<unknown> {
  if (input instanceof Request) {
    return input.clone().json();
  }
  return undefined;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const NEW_CONTENT_ID = '88888888-8888-8888-8888-888888888888';

const createdFixture: ContentDto = {
  author_id: null,
  body_md: 'Body text',
  created_at: '2026-01-01T00:00:00Z',
  id: NEW_CONTENT_ID,
  published_at: null,
  slug: 'untitled',
  status: 'draft',
  tags: ['retirement'],
  title: 'Untitled',
  updated_at: '2026-01-01T00:00:00Z',
  updated_by: null,
};

function mockFetch() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'POST') {
        return jsonResponse(createdFixture, 201);
      }
      if (pathname === '/api/v1/tags' && method === 'GET') {
        return jsonResponse([]);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderNew() {
  return render(
    <Providers>
      <ContentEditorScreen />
    </Providers>,
  );
}

describe('ContentEditorScreen tag blur capture (WR-11)', () => {
  beforeEach(() => {
    pushMock.mockClear();
    replaceMock.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a tag typed into Tags and blurred WITHOUT pressing Enter is still included in the create payload', async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();

    renderNew();

    await user.type(screen.getByRole('textbox', { name: /title/i }), 'Untitled');
    const tagsInput = screen.getByRole('combobox', { name: /tags/i });
    await user.type(tagsInput, 'retirement');
    // Blur WITHOUT Enter: move focus to another field instead of confirming the tag.
    await user.click(screen.getByRole('textbox', { name: /body/i }));

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'POST',
      );
      expect(call).toBeDefined();
    });
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'POST',
    )!;
    const body = (await requestJson(createCall[0])) as { tags: string[] };
    expect(body.tags).toContain('retirement');
  });
});
