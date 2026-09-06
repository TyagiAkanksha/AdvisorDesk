// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// 6R task-11, fix round 1 (review finding #1, Important): a NEW regression the WR-11 blur-capture
// fix itself introduced. `Autocomplete/Component.tsx`'s `onChange` wrapper used to clear the
// locally-tracked `inputValue` unconditionally on EVERY MUI `onChange`, including
// `reason: 'removeOption'` (chip delete via the × icon). MUI's own `useAutocomplete.js` never
// touches `inputValue` for that reason (`handleValue` is called directly there, bypassing
// `resetInputValue` entirely) — so deleting an unrelated, already-confirmed tag while a NEW tag
// sat typed-but-unconfirmed in the field silently wiped the typed text too, from both the visible
// input and (implicitly) the eventual payload. This is colocated (not added to the pinned
// `tagBlurCapture.test.tsx`) per this folder's one-behavior-per-new-file convention.
//
// RED against the pre-fix-round-1 `Autocomplete/Component.tsx` (commit 7a909c9): the first test
// below fails because the "baz" input is empty after deleting the "bar" chip.
const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function pathnameOf(input: RequestInfo | URL): string {
  return new URL(requestUrl(input)).pathname;
}

const draftFixture: ContentDto = {
  author_id: null,
  body_md: 'Body text',
  created_at: '2026-01-01T00:00:00Z',
  id: '44444444-4444-4444-4444-444444444444',
  published_at: null,
  slug: 'chip-delete-fixture',
  status: 'draft',
  tags: ['bar', 'foo'],
  title: 'Chip Delete Fixture',
  updated_at: '2026-01-01T00:00:00Z',
  updated_by: null,
};

function mockFetch() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input) => {
      const pathname = pathnameOf(input);
      if (pathname === `/api/v1/content/${draftFixture.id}`) {
        return jsonResponse(draftFixture);
      }
      if (pathname === '/api/v1/tags') {
        return jsonResponse([]);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderEdit() {
  return render(
    <Providers>
      <ContentEditorScreen contentId={draftFixture.id} />
    </Providers>,
  );
}

describe('ContentEditorScreen tag chip delete preserves in-progress typing (WR-11 fix round 1)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('deleting an existing chip does NOT discard a different tag typed-but-not-yet-Entered', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit();

    expect(await screen.findByText('bar')).toBeInTheDocument();
    expect(screen.getByText('foo')).toBeInTheDocument();

    const tagsInput = screen.getByRole('combobox', { name: /tags/i });
    await user.type(tagsInput, 'baz');
    expect(tagsInput).toHaveValue('baz');

    const barChip = screen.getByText('bar').closest('.MuiChip-root');
    expect(barChip).not.toBeNull();
    const deleteIcon = barChip!.querySelector('.MuiChip-deleteIcon');
    expect(deleteIcon).not.toBeNull();
    await user.click(deleteIcon!);

    // The unrelated, already-confirmed "bar" tag is gone...
    expect(screen.queryByText('bar')).not.toBeInTheDocument();
    // ...but the tag the user was still typing survives, untouched, in the input.
    expect(tagsInput).toHaveValue('baz');
    // ...and the other pre-existing tag is unaffected by the deletion.
    expect(screen.getByText('foo')).toBeInTheDocument();
  });

  it('deleting a chip with no pending typed text still removes only that tag', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit();

    expect(await screen.findByText('bar')).toBeInTheDocument();
    expect(screen.getByText('foo')).toBeInTheDocument();

    const tagsInput = screen.getByRole('combobox', { name: /tags/i });
    expect(tagsInput).toHaveValue('');

    const barChip = screen.getByText('bar').closest('.MuiChip-root');
    const deleteIcon = barChip!.querySelector('.MuiChip-deleteIcon');
    await user.click(deleteIcon!);

    expect(screen.queryByText('bar')).not.toBeInTheDocument();
    expect(screen.getByText('foo')).toBeInTheDocument();
    expect(tagsInput).toHaveValue('');
  });
});
