import { useEffect, useState } from 'react';

import { useDeleteContentMutation, useListContentQuery } from '@/lib/api/contentApi';
import { extractErrorMessage } from '@/lib/errorMessage';
import type { ContentDto, ContentStatus } from '@/types/api/content';

// task-05 Interfaces: `useContentList` owns filters/pagination/debounce state so
// ContentListScreen stays dumb (docs/FRONTEND-CONVENTIONS.md §3). 300ms is the debounce
// window for the search field — long enough to skip a request per keystroke, short enough to
// feel responsive (test-author report's resolved ambiguity #6: no fixed value was pinned by a
// test, so this constant is the implementer's documented choice).
const SEARCH_DEBOUNCE_MS = 300;
const PAGE_SIZE = 20;
// fix round 1, F2: friendly fallback when a DELETE failure carries no §9 envelope message
// (e.g. a network error rather than a server-produced error response).
const DELETE_ERROR_FALLBACK = "Couldn't delete this item. Please try again.";

export interface UseContentListResult {
  items: ContentDto[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  isError: boolean;
  status: ContentStatus | '';
  setStatus: (status: ContentStatus | '') => void;
  tag: string;
  setTag: (tag: string) => void;
  q: string;
  setQ: (q: string) => void;
  setPage: (page: number) => void;
  deleteContent: (id: string) => Promise<void>;
  isDeleting: boolean;
  /** §9-friendly message from the most recent failed `deleteContent` call, else `null`. */
  deleteError: string | null;
  /** Clears `deleteError` — called on dialog close and at the start of every retry. */
  clearDeleteError: () => void;
}

export function useContentList(): UseContentListResult {
  const [status, setStatus] = useState<ContentStatus | ''>('');
  const [tag, setTag] = useState('');
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [page, setPage] = useState(1);

  // Debounce `q` -> `debouncedQ`; every other filter re-queries immediately.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [q]);

  const { data, isLoading, isError } = useListContentQuery({
    status: status || undefined,
    tag: tag || undefined,
    q: debouncedQ || undefined,
    page,
    page_size: PAGE_SIZE,
  });

  const [triggerDelete, { isLoading: isDeleting }] = useDeleteContentMutation();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const setStatusAndResetPage = (next: ContentStatus | '') => {
    setStatus(next);
    setPage(1);
  };
  const setTagAndResetPage = (next: string) => {
    setTag(next);
    setPage(1);
  };
  const setQAndResetPage = (next: string) => {
    setQ(next);
    setPage(1);
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
    } catch (error) {
      setDeleteError(extractErrorMessage(error, DELETE_ERROR_FALLBACK));
      throw error;
    }
  };

  const clearDeleteError = () => setDeleteError(null);

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    page,
    pageSize: PAGE_SIZE,
    isLoading,
    isError,
    status,
    setStatus: setStatusAndResetPage,
    tag,
    setTag: setTagAndResetPage,
    q,
    setQ: setQAndResetPage,
    setPage,
    deleteContent,
    isDeleting,
    deleteError,
    clearDeleteError,
  };
}
