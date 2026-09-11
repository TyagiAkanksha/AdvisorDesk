// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { stubMatchMedia } from '@/testing/matchMedia';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// task-20 (DESIGN.md §5 C5): below the `md` breakpoint the form and the live preview no longer
// share a two-column row — a header Preview/Edit toggle swaps one for the other. Copied from
// Component.test.tsx: the `next/navigation` mock block, `draftFixture` (with task-20's new
// body — a bare `# Title` strips to nothing, which this suite doesn't want to assert against),
// `mockFetch`, and `renderEdit`.
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const NEW_CONTENT_ID = '99999999-9999-9999-9999-999999999999';

const draftFixture: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics\n\nBody.',
  created_at: '2026-01-01T00:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-01-02T00:00:00Z',
  updated_by: null,
};

interface MockFetchOptions {
  getContentResponse?: Response;
  createContentResponse?: Response;
  updateContentResponse?: Response;
  publishContentResponse?: Response;
  archiveContentResponse?: Response;
  tagsResponse?: Response;
}

function mockFetch(options: MockFetchOptions = {}) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'POST') {
        return (
          options.createContentResponse ??
          jsonResponse({ ...draftFixture, id: NEW_CONTENT_ID }, 201)
        );
      }
      if (pathname.endsWith('/publish') && method === 'POST') {
        return (
          options.publishContentResponse ??
          jsonResponse({
            ...draftFixture,
            status: 'published',
            published_at: '2026-04-01T00:00:00Z',
          })
        );
      }
      if (pathname.endsWith('/archive') && method === 'POST') {
        return (
          options.archiveContentResponse ?? jsonResponse({ ...draftFixture, status: 'archived' })
        );
      }
      if (pathname.startsWith('/api/v1/content/') && method === 'GET') {
        return options.getContentResponse ?? jsonResponse(draftFixture);
      }
      if (pathname.startsWith('/api/v1/content/') && method === 'PATCH') {
        return options.updateContentResponse ?? jsonResponse(draftFixture);
      }
      if (pathname === '/api/v1/tags' && method === 'GET') {
        return options.tagsResponse ?? jsonResponse([]);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderEdit(contentId: string) {
  return render(
    <Providers>
      <ContentEditorScreen contentId={contentId} />
    </Providers>,
  );
}

describe('ContentEditorScreen below the md breakpoint', () => {
  let restore: (() => void) | null = null;

  beforeEach(() => {
    restore = stubMatchMedia(true);
  });

  afterEach(() => {
    restore?.();
    restore = null;
    vi.restoreAllMocks();
  });

  it('a header Preview button swaps the form for the preview, and Edit swaps back', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    await screen.findByRole('textbox', { name: /title/i });
    expect(screen.queryByRole('region', { name: 'Preview' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Preview' }));
    expect(screen.getByRole('region', { name: 'Preview' })).toHaveTextContent('Body.');
    expect(screen.queryByRole('textbox', { name: /title/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('textbox', { name: /title/i })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Preview' })).not.toBeInTheDocument();
  });
});
