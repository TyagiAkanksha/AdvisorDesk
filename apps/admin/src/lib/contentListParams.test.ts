import { describe, expect, it } from 'vitest';

import {
  DEFAULT_CONTENT_LIST_PARAMS,
  buildContentListSearch,
  hasActiveFilters,
  parseContentListParams,
} from './contentListParams';

describe('contentListParams', () => {
  it('parses known values and falls back per field', () => {
    expect(
      parseContentListParams(new URLSearchParams('status=draft&tag= retirement &q=roth&page=3')),
    ).toEqual({
      status: 'draft',
      tag: 'retirement',
      q: 'roth',
      page: 3,
    });
    expect(parseContentListParams(new URLSearchParams('status=bogus&page=0'))).toEqual(
      DEFAULT_CONTENT_LIST_PARAMS,
    );
    expect(parseContentListParams(new URLSearchParams('page=abc'))).toEqual(
      DEFAULT_CONTENT_LIST_PARAMS,
    );
    expect(parseContentListParams(new URLSearchParams('page=2.5'))).toEqual(
      DEFAULT_CONTENT_LIST_PARAMS,
    );
    expect(parseContentListParams(new URLSearchParams(''))).toEqual(DEFAULT_CONTENT_LIST_PARAMS);
  });

  it('builds the search string with defaults omitted, in a fixed key order', () => {
    expect(buildContentListSearch(DEFAULT_CONTENT_LIST_PARAMS)).toBe('');
    expect(buildContentListSearch({ status: 'published', tag: '', q: '', page: 1 })).toBe(
      '?status=published',
    );
    expect(buildContentListSearch({ status: '', tag: 'a&b', q: 'roth ira', page: 2 })).toBe(
      '?tag=a%26b&q=roth+ira&page=2',
    );
  });

  it('round-trips', () => {
    const params = { status: 'archived' as const, tag: 'tax-planning', q: 'x', page: 4 };
    expect(parseContentListParams(new URLSearchParams(buildContentListSearch(params)))).toEqual(
      params,
    );
  });

  it('hasActiveFilters ignores the page', () => {
    expect(hasActiveFilters({ ...DEFAULT_CONTENT_LIST_PARAMS, page: 3 })).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_CONTENT_LIST_PARAMS, q: 'x' })).toBe(true);
  });
});
