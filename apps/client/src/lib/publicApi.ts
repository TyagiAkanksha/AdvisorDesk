import { cache } from 'react';

import type { PublicContentDetailDto, PublicContentSummaryDto } from '@/types';

// Single source of truth for the apps/api base URL these server-side fetch helpers target.
// Deliberately `API_URL`, NOT `NEXT_PUBLIC_API_URL`: this module only ever runs on the server
// (React Server Components — docs/FRONTEND-CONVENTIONS.md §6, "content pages are RSC fetching
// the public API server-side"), so the value never needs to reach the browser bundle. Mirrors
// apps/admin/src/lib/apiBase.ts's fail-loudly-in-production shape (see that file's own
// comment): a missing env var in a production build is a deploy-config bug, not a runtime edge
// case to degrade gracefully around. Dev/test keep the documented local API origin as a
// fallback so an unset var never blocks `pnpm dev`/`pnpm test` (root `.env.example`'s `API_URL`
// entry documents this default; FRONTEND-CONVENTIONS.md §1 pinned ports).
const DEV_FALLBACK_API_URL = 'http://localhost:8000';

function resolveApiBaseUrl(): string {
  const value = process.env.API_URL;
  if (value) {
    return value;
  }
  if (process.env.NODE_ENV === 'production') {
    throw new Error('API_URL must be set in production');
  }
  return DEV_FALLBACK_API_URL;
}

// PRD §5.3: published-and-non-deleted content, newest-published first, tags included. Bare
// list, no pagination envelope (matches `GET /public/content`'s response shape).
//
// p8 t24: wrapped in React's `cache()` — a request-scoped memo, same pattern as
// `getContentBySlug` below — so the article page's `Promise.all([getContentBySlug(slug),
// getPublishedContentOrEmpty()])` and any other same-request caller dedupe to one fetch.
export const getPublishedContent = cache(async (): Promise<PublicContentSummaryDto[]> => {
  const response = await fetch(`${resolveApiBaseUrl()}/api/v1/public/content`, {
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch published content: ${response.status}`);
  }
  return (await response.json()) as PublicContentSummaryDto[];
});

/**
 * p8 t24 (DESIGN.md §B3 carry-in): the related-articles list must never take an article page
 * down — a failed or throwing fetch degrades to an empty list (no related section) rather than
 * surfacing an error page for content that otherwise loaded fine.
 */
export async function getPublishedContentOrEmpty(): Promise<PublicContentSummaryDto[]> {
  try {
    return await getPublishedContent();
  } catch {
    return [];
  }
}

// PRD §5.3: a deleted item's slug 404s and is never reassigned — the thin `[slug]` page turns a
// `null` return into Next's `notFound()` (404 page), never an error state.
//
// phase-8 task-10: wrapped in React's `cache()` — a request-scoped memo — so `generateMetadata`
// and the page component (both call `getContentBySlug(slug)` for the same request) dedupe to one
// fetch instead of two.
export const getContentBySlug = cache(
  async (slug: string): Promise<PublicContentDetailDto | null> => {
    const response = await fetch(
      `${resolveApiBaseUrl()}/api/v1/public/content/${encodeURIComponent(slug)}`,
      { cache: 'no-store' },
    );
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`Failed to fetch content "${slug}": ${response.status}`);
    }
    return (await response.json()) as PublicContentDetailDto;
  },
);
