import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { useRisingEdgeNotice, useSnackbar } from '@/components/common';
import { useDeleteContentMutation, useListContentQuery } from '@/lib/api/contentApi';
import {
  DEFAULT_CONTENT_LIST_PARAMS,
  buildContentListSearch,
  hasActiveFilters,
  parseContentListParams,
} from '@/lib/contentListParams';
import { CONTENT_DELETED_MESSAGE, CONTENT_REFRESH_ERROR, DELETE_ERROR_FALLBACK } from '@/lib/copy';
import { extractErrorMessage } from '@/lib/errorMessage';
import type { ContentDto, ContentStatus } from '@/types/api/content';
import type { ContentListParams } from '@/lib/contentListParams';

// task-05 Interfaces: `useContentList` owns filters/pagination/debounce state so
// ContentListScreen stays dumb (docs/FRONTEND-CONVENTIONS.md §3). phase-8 task-18 (DESIGN.md §2,
// §5 C4): the URL is now the single source of truth for status/tag/page/q — the dashboard's stat
// cards and tag links deep-link into `/content?...` and the browser back button restores the
// screen — the search FIELD alone keeps a local echo so typing feels instant while the URL write
// is debounced.
const SEARCH_DEBOUNCE_MS = 300;
const PAGE_SIZE = 20;

export interface UseContentListResult {
  items: ContentDto[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  isError: boolean;
  /** `true` once a page has been loaded into `items` at least once (final review, finding F8) —
   * lets the Component distinguish "nothing to show, replace with ErrorState" from "a
   * background refetch failed but a previously loaded page is still cached". */
  hasData: boolean;
  status: ContentStatus | '';
  setStatus: (status: ContentStatus | '') => void;
  tag: string;
  setTag: (tag: string) => void;
  /** Live field value — instant while typing; the URL write is debounced. */
  q: string;
  setQ: (q: string) => void;
  hasFilters: boolean;
  clearFilters: () => void;
  setPage: (page: number) => void;
  deleteContent: (id: string) => Promise<void>;
  isDeleting: boolean;
  /** §9-friendly message from the most recent failed `deleteContent` call, else `null`. */
  deleteError: string | null;
  /** Clears `deleteError` — called on dialog close and at the start of every retry. */
  clearDeleteError: () => void;
}

export function useContentList(): UseContentListResult {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const params = parseContentListParams(searchParams);

  const write = (next: ContentListParams) => {
    router.replace(`${pathname}${buildContentListSearch(next)}`, { scroll: false });
  };

  // Search field: an instant local echo of `params.q`, written back to the URL 300ms after the
  // last keystroke. `lastWrittenQ` distinguishes "the URL changed because WE just wrote it"
  // (already in sync, no echo needed) from "the URL changed externally" (back button — sync the
  // field to match).
  const [qInput, setQInput] = useState(params.q);
  const lastWrittenQ = useRef(params.q);
  useEffect(() => {
    if (params.q !== lastWrittenQ.current) {
      lastWrittenQ.current = params.q;
      setQInput(params.q);
    }
  }, [params.q]);
  // review I-1: the timer reads the LIVE params via `paramsRef`, not the params captured by the
  // closure that scheduled it — a status/tag change made inside the debounce window must not be
  // reverted by the pending q write. Kept in sync via its own no-deps effect (runs after every
  // render) rather than a direct mutation during render — this repo's `react-hooks/refs` lint
  // rule (`Cannot access refs during render`) disallows the latter; the ref is guaranteed
  // up to date before any later-scheduled timer's callback can fire (a `setTimeout` callback is
  // a macrotask, always ordered after the synchronous render + effect commit that preceded it).
  const paramsRef = useRef(params);
  useEffect(() => {
    paramsRef.current = params;
  });
  useEffect(() => {
    if (qInput === params.q) {
      return;
    }
    const timer = setTimeout(() => {
      lastWrittenQ.current = qInput;
      write({ ...paramsRef.current, q: qInput, page: 1 });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput, params.q]);

  const { data, isLoading, isError } = useListContentQuery({
    status: params.status || undefined,
    tag: params.tag || undefined,
    q: params.q || undefined,
    page: params.page,
    page_size: PAGE_SIZE,
  });
  const hasData = data !== undefined;

  // WR-60: a stranded page (e.g. the last row on a page was deleted, or a deep link named a page
  // past the end) clamps back to the last valid page once `total` is known.
  useEffect(() => {
    if (!data) {
      return;
    }
    const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
    if (params.page > lastPage) {
      write({ ...params, page: lastPage });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only off `data`/`params.page`.
  }, [data, params.page]);

  // Final review, finding F8/C-4: a background refetch (e.g. another screen's mutation
  // invalidating the `'Content'` tag while this list is still mounted) failing must not blank the
  // whole list back to `ErrorState` — the last successfully loaded page stays visible, with the
  // failure surfaced through the global snackbar instead. Fired once per failure episode via
  // `useRisingEdgeNotice`, same idiom as `useDashboard`'s background-refresh notice.
  const { error: notifyError, success: notifySuccess } = useSnackbar();
  const isBackgroundRefreshFailing = hasData && isError;
  useRisingEdgeNotice(isBackgroundRefreshFailing, notifyError, CONTENT_REFRESH_ERROR);

  const [triggerDelete, { isLoading: isDeleting }] = useDeleteContentMutation();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const setStatus = (next: ContentStatus | '') => write({ ...params, status: next, page: 1 });
  const setTag = (next: string) => write({ ...params, tag: next, page: 1 });
  const setQ = (next: string) => setQInput(next);
  const setPage = (next: number) => write({ ...params, page: next });
  const clearFilters = () => {
    lastWrittenQ.current = '';
    setQInput('');
    write(DEFAULT_CONTENT_LIST_PARAMS);
  };

  // fix round 1, F2: a DELETE failure used to disappear into ContentListScreen's bare
  // `catch {}` with zero feedback. `deleteError` is cleared at the start of every attempt
  // (a retry's own failure replaces the previous message; a retry's success leaves it
  // cleared) and populated from the PRD §9 envelope's `error.message` when the rejection
  // carries one. The rejection is still rethrown so the caller's own try/catch (which decides
  // whether to close the dialog) is unaffected.
  const deleteContent = async (id: string) => {
    setDeleteError(null);
    try {
      await triggerDelete(id).unwrap();
      notifySuccess(CONTENT_DELETED_MESSAGE);
    } catch (error) {
      setDeleteError(extractErrorMessage(error, DELETE_ERROR_FALLBACK));
      throw error;
    }
  };

  const clearDeleteError = () => setDeleteError(null);

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    page: params.page,
    pageSize: PAGE_SIZE,
    isLoading,
    isError,
    hasData,
    status: params.status,
    setStatus,
    tag: params.tag,
    setTag,
    q: qInput,
    setQ,
    hasFilters: hasActiveFilters(params),
    clearFilters,
    setPage,
    deleteContent,
    isDeleting,
    deleteError,
    clearDeleteError,
  };
}
