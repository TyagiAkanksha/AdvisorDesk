import { describe, expect, it } from 'vitest';

import type { PublicContentSummary } from '@/types';

import { filterByTag, uniqueTags } from './filterByTag';

const items: PublicContentSummary[] = [
  {
    slug: 'a',
    title: 'A',
    tags: ['retirement', 'tax-planning'],
    published_at: '2026-03-01T00:00:00Z',
  },
  { slug: 'b', title: 'B', tags: ['insurance'], published_at: '2026-02-01T00:00:00Z' },
  { slug: 'c', title: 'C', tags: ['retirement'], published_at: '2026-01-01T00:00:00Z' },
];

describe('uniqueTags', () => {
  it('returns each tag once, sorted A→Z', () => {
    expect(uniqueTags(items)).toEqual(['insurance', 'retirement', 'tax-planning']);
  });

  it('returns an empty array for no items', () => {
    expect(uniqueTags([])).toEqual([]);
  });
});

describe('filterByTag', () => {
  it('returns the items unchanged (same order) for a null tag', () => {
    expect(filterByTag(items, null)).toEqual(items);
  });

  it('keeps only items carrying the tag, preserving order', () => {
    expect(filterByTag(items, 'retirement').map((item) => item.slug)).toEqual(['a', 'c']);
  });

  it('matches tags exactly (no prefix or case folding) and returns [] for an unknown tag', () => {
    expect(filterByTag(items, 'retire')).toEqual([]);
    expect(filterByTag(items, 'Retirement')).toEqual([]);
    expect(filterByTag(items, 'nope')).toEqual([]);
  });
});
