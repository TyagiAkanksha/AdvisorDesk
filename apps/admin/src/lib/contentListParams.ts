import { ContentStatus } from '@/types/api/content';

// phase-8 task-18 (DESIGN.md §2, §5 C4): the content list's filter/pagination state lives in the
// URL (`?status=&tag=&q=&page=`) — this module is the single, pure parse/build boundary so
// dashboard stat cards and the dashboard's tag table can deep-link straight into a filtered list
// and the browser back button restores it for free (`useContentList` is the only consumer).
export interface ContentListParams {
  status: ContentStatus | '';
  tag: string;
  q: string;
  page: number;
}

export const DEFAULT_CONTENT_LIST_PARAMS: ContentListParams = {
  status: '',
  tag: '',
  q: '',
  page: 1,
};

const VALID_STATUSES: ReadonlySet<string> = new Set(Object.values(ContentStatus));

function parseStatus(value: string | null): ContentStatus | '' {
  return value !== null && VALID_STATUSES.has(value) ? (value as ContentStatus) : '';
}

// Only a plain positive integer string ("1", "23", ...) is a valid page — anything else
// (missing, zero/negative, non-integer, non-numeric) falls back to page 1.
function parsePage(value: string | null): number {
  if (value === null || !/^[1-9]\d*$/.test(value)) {
    return 1;
  }
  return Number(value);
}

export function parseContentListParams(search: URLSearchParams): ContentListParams {
  return {
    status: parseStatus(search.get('status')),
    tag: (search.get('tag') ?? '').trim(),
    q: (search.get('q') ?? '').trim(),
    page: parsePage(search.get('page')),
  };
}

// Defaults are omitted entirely (never written as e.g. `page=1`) so a cleared filter set
// round-trips to the bare `/content` pathname, not `/content?status=&tag=&q=&page=1`.
// hygiene t06 M1: `tag`/`q` are trimmed here too, defence in depth — no code path (including a
// future one) can emit a blank-looking param into the URL.
export function buildContentListSearch(params: ContentListParams): string {
  const query = new URLSearchParams();
  const tag = params.tag.trim();
  const q = params.q.trim();
  if (params.status) {
    query.set('status', params.status);
  }
  if (tag) {
    query.set('tag', tag);
  }
  if (q) {
    query.set('q', q);
  }
  if (params.page !== DEFAULT_CONTENT_LIST_PARAMS.page) {
    query.set('page', String(params.page));
  }

  const search = query.toString();
  return search ? `?${search}` : '';
}

export function hasActiveFilters(params: ContentListParams): boolean {
  return Boolean(params.status || params.tag || params.q);
}

// hygiene t06 M2: `true` when `search` is exactly what `buildContentListSearch` would produce for
// the params it parses to — i.e. it carries no unknown `status`, no unusable `page`, no untrimmed
// `tag`/`q`, no stray key and no non-canonical key order. The comparison is against the
// RE-SERIALISED form on both sides (`URLSearchParams.toString()`), so e.g. a `%20`-encoded deep
// link is still canonical when it decodes to the same params. `parseContentListParams` only
// reads `status|tag|q|page` — any other key (a campaign/tracking param, or one a future feature
// adds) is deliberately dropped on load: the list's query-param set is closed, so add a new key
// here first (final-review M-3).
export function isCanonicalContentListSearch(search: URLSearchParams): boolean {
  const raw = search.toString();
  return buildContentListSearch(parseContentListParams(search)) === (raw ? `?${raw}` : '');
}
