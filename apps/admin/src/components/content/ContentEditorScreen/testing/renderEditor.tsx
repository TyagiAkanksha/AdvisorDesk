import { render } from '@testing-library/react';
import type { RenderResult } from '@testing-library/react';
import type { Mock } from 'vitest';
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

export function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

export function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

export function pathnameOf(input: RequestInfo | URL): string {
  return new URL(requestUrl(input)).pathname;
}

/** `fetchBaseQuery` hands the mock a native `Request`; a plain `init.body` is the fallback. */
export async function requestBody(input: RequestInfo | URL, init?: RequestInit): Promise<unknown> {
  if (input instanceof Request) {
    return input.clone().json();
  }
  if (init?.body === undefined) {
    return undefined;
  }
  return JSON.parse(String(init.body));
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export const NEW_CONTENT_ID = '99999999-9999-9999-9999-999999999999';

export const draftFixture: ContentDto = {
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

export const publishedFixture: ContentDto = {
  ...draftFixture,
  id: '22222222-2222-2222-2222-222222222222',
  slug: 'estate-planning-101',
  status: 'published',
  published_at: '2025-12-05T00:00:00Z',
  title: 'Estate Planning 101',
};

export const archivedFixture: ContentDto = {
  ...draftFixture,
  id: '33333333-3333-3333-3333-333333333333',
  slug: 'social-security-timing',
  status: 'archived',
  title: 'Social Security Timing',
};

export interface MockFetchOptions {
  getContentResponse?: Response;
  createContentResponse?: Response;
  updateContentResponse?: Response;
  publishContentResponse?: Response;
  archiveContentResponse?: Response;
  tagsResponse?: Response;
}

/** Option-per-endpoint idiom — Component.test.tsx:114-155, moved verbatim. */
export function mockEditorFetch(
  options: MockFetchOptions = {},
): Mock<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>> {
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

export type EditorFetchHandler = (url: URL, method: string) => Response | Promise<Response>;

/** Handler idiom — useContentEditor.test.tsx:66-72, moved verbatim. */
export function mockEditorFetchWith(
  handler: EditorFetchHandler,
): Mock<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>> {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => handler(new URL(requestUrl(input)), requestMethod(input, init)),
  );
  global.fetch = fetchMock;
  return fetchMock;
}

/** useContentEditor.test.tsx:74-85, moved verbatim (GET/PATCH the draft, two tags). */
export const editHandler: EditorFetchHandler = (url, method) => {
  if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'GET')
    return jsonResponse(draftFixture);
  if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'PATCH')
    return jsonResponse(draftFixture);
  if (url.pathname === '/api/v1/tags')
    return jsonResponse([
      { id: 't1', name: 'retirement', count: 2 },
      { id: 't2', name: 'tax-planning', count: 1 },
    ]);
  return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
};

export function renderNew(): RenderResult {
  return render(
    <Providers>
      <ContentEditorScreen />
    </Providers>,
  );
}

export function renderEdit(contentId: string): RenderResult {
  return render(
    <Providers>
      <ContentEditorScreen contentId={contentId} />
    </Providers>,
  );
}
