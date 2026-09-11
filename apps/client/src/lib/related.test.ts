import { describe, expect, it } from 'vitest';

import type { PublicContentSummary } from '@/types';

import { relatedArticles } from './related';

const make = (slug: string, tags: string[], date: string): PublicContentSummary => ({
  slug,
  title: slug,
  tags,
  published_at: date,
});

const all = [
  make('current', ['retirement', 'tax'], '2026-05-01T00:00:00Z'),
  make('two-shared-old', ['retirement', 'tax'], '2025-01-01T00:00:00Z'),
  make('one-shared-new', ['retirement'], '2026-04-01T00:00:00Z'),
  make('one-shared-old', ['tax'], '2025-06-01T00:00:00Z'),
  make('none-newest', ['insurance'], '2026-06-01T00:00:00Z'),
  make('none-older', ['college'], '2026-03-01T00:00:00Z'),
];

describe('relatedArticles', () => {
  it('excludes the current article and orders by shared tags, then recency', () => {
    expect(relatedArticles(all, all[0]!).map((item) => item.slug)).toEqual([
      'two-shared-old',
      'one-shared-new',
      'one-shared-old',
    ]);
  });

  it('fills with the most recent unrelated articles when fewer than max share a tag', () => {
    const current = make('solo', ['insurance'], '2026-01-01T00:00:00Z');
    expect(relatedArticles(all, current).map((item) => item.slug)).toEqual([
      'none-newest',
      'current',
      'one-shared-new',
    ]);
  });

  it('respects max and returns [] when there is nothing else', () => {
    expect(relatedArticles(all, all[0]!, 1).map((item) => item.slug)).toEqual(['two-shared-old']);
    expect(relatedArticles([all[0]!], all[0]!)).toEqual([]);
  });
});
