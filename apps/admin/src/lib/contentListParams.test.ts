import { describe, expect, it } from 'vitest';

import {
  DEFAULT_CONTENT_LIST_PARAMS,
  buildContentListSearch,
  hasActiveFilters,
  isCanonicalContentListSearch,
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

  it('never writes a whitespace-only tag or q into the search string (hygiene t06 M1)', () => {
    expect(buildContentListSearch({ status: '', tag: '   ', q: '   ', page: 1 })).toBe('');
    expect(buildContentListSearch({ status: '', tag: ' retirement ', q: ' roth ', page: 1 })).toBe(
      '?tag=retirement&q=roth',
    );
  });

  it('recognises a canonical search string (hygiene t06 M2)', () => {
    expect(isCanonicalContentListSearch(new URLSearchParams(''))).toBe(true);
    expect(isCanonicalContentListSearch(new URLSearchParams('status=draft&tag=a&q=b&page=2'))).toBe(
      true,
    );
    expect(isCanonicalContentListSearch(new URLSearchParams('status=bogus'))).toBe(false);
    expect(isCanonicalContentListSearch(new URLSearchParams('page=0'))).toBe(false);
    expect(isCanonicalContentListSearch(new URLSearchParams('page=abc'))).toBe(false);
    expect(isCanonicalContentListSearch(new URLSearchParams('page=1'))).toBe(false);
    expect(isCanonicalContentListSearch(new URLSearchParams('tag=%20%20'))).toBe(false);
    expect(isCanonicalContentListSearch(new URLSearchParams('q=roth&status=draft'))).toBe(false);
    expect(isCanonicalContentListSearch(new URLSearchParams('sort=title'))).toBe(false);
  });
});
