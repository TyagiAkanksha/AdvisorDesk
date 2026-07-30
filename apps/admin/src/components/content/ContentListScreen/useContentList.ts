import { useEffect, useState } from 'react';

import { useDeleteContentMutation, useListContentQuery } from '@/lib/api/contentApi';
import type { ContentDto, ContentStatus } from '@/types/api/content';

// task-05 Interfaces: `useContentList` owns filters/pagination/debounce state so
// ContentListScreen stays dumb (docs/FRONTEND-CONVENTIONS.md §3). 300ms is the debounce
// window for the search field — long enough to skip a request per keystroke, short enough to
// feel responsive (test-author report's resolved ambiguity #6: no fixed value was pinned by a
// test, so this constant is the implementer's documented choice).
const SEARCH_DEBOUNCE_MS = 300;
const PAGE_SIZE = 20;

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

  const deleteContent = async (id: string) => {
    await triggerDelete(id).unwrap();
  };

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
  };
}
