import { afterEach, describe, expect, it, vi } from 'vitest';

import { getPublishedContentOrEmpty } from './publicApi';

// p8 t24 (DESIGN.md §B3 carry-in): the related-articles list must never take an article page down
// — a failed/erroring fetch degrades to an empty list rather than throwing out of the page.
describe('getPublishedContentOrEmpty', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the list when the fetch succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify([{ slug: 'a' }]), { status: 200 })),
    );
    await expect(getPublishedContentOrEmpty()).resolves.toEqual([{ slug: 'a' }]);
  });

  it('returns [] when the fetch fails or rejects — a broken list never takes an article page down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 500 })));
    await expect(getPublishedContentOrEmpty()).resolves.toEqual([]);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    await expect(getPublishedContentOrEmpty()).resolves.toEqual([]);
  });
});
