'use client';

import { useState } from 'react';

import {
  Box,
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
} from '@/components/common';
import { useListTagsQuery } from '@/lib/api/tagsApi';
import {
  CONTENT_LOAD_ERROR,
  CONTENT_TITLE,
  CLEAR_FILTERS_LABEL,
  CREATE_FIRST_ARTICLE_LABEL,
  NEW_CONTENT_LABEL,
  NO_CONTENT_DESCRIPTION,
  NO_CONTENT_TITLE,
  NO_MATCH_DESCRIPTION,
  NO_MATCH_TITLE,
} from '@/lib/copy';
import type { ContentDto } from '@/types/api/content';

import { ContentFilters } from './components/ContentFilters';
import { ContentTable } from './components/ContentTable';
import { ContentTableSkeleton } from './components/ContentTableSkeleton';
import { useContentList } from './useContentList';

export default function Component() {
  const {
    items,
    total,
    page,
    pageSize,
    isLoading,
    isError,
    hasData,
    status,
    setStatus,
    tag,
    setTag,
    q,
    setQ,
    hasFilters,
    clearFilters,
    setPage,
    deleteContent,
    isDeleting,
    deleteError,
    clearDeleteError,
  } = useContentList();
  const { data: tags } = useListTagsQuery();
  const [deleteTarget, setDeleteTarget] = useState<ContentDto | null>(null);

  const tagOptions = [
    { value: '', label: 'All tags' },
    ...(tags ?? []).map((item) => ({ value: item.name, label: item.name })),
  ];

  const handleDeleteClick = (item: ContentDto) => {
    clearDeleteError();
    setDeleteTarget(item);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    try {
      await deleteContent(deleteTarget.id);
      setDeleteTarget(null);
    } catch {
      // `deleteError` (from useContentList) surfaces the failure inside the still-open
      // ConfirmDialog — the admin can retry immediately or cancel.
    }
  };

  const handleCloseDialog = () => {
    setDeleteTarget(null);
    clearDeleteError();
  };

  return (
    <Box>
      <PageHeader
        title={CONTENT_TITLE}
        actions={
          <Button href="/content/new" variant="contained">
            {NEW_CONTENT_LABEL}
          </Button>
        }
      />
      <ContentFilters
        status={status}
        tag={tag}
        q={q}
        tagOptions={tagOptions}
        hasFilters={hasFilters}
        onStatusChange={setStatus}
        onTagChange={setTag}
        onQChange={setQ}
        onClear={clearFilters}
      />

      {isLoading && !hasData ? <ContentTableSkeleton /> : null}
      {!hasData && isError ? <ErrorState message={CONTENT_LOAD_ERROR} /> : null}
      {hasData && items.length === 0 && !hasFilters ? (
        <EmptyState
          title={NO_CONTENT_TITLE}
          description={NO_CONTENT_DESCRIPTION}
          action={
            <Button href="/content/new" variant="contained">
              {CREATE_FIRST_ARTICLE_LABEL}
            </Button>
          }
        />
      ) : null}
      {hasData && items.length === 0 && hasFilters ? (
        <EmptyState
          icon="Search"
          title={NO_MATCH_TITLE}
          description={NO_MATCH_DESCRIPTION}
          action={
            <Button variant="outlined" onClick={clearFilters}>
              {CLEAR_FILTERS_LABEL}
            </Button>
          }
        />
      ) : null}
      {hasData && items.length > 0 ? (
        <ContentTable items={items} onDeleteClick={handleDeleteClick} />
      ) : null}
      {hasData ? (
        <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete content"
        body={`“${deleteTarget?.title ?? ''}” will be permanently deleted — there is no restore.`}
        confirmLabel="Delete"
        onConfirm={handleConfirmDelete}
        onClose={handleCloseDialog}
        isPending={isDeleting}
        errorMessage={deleteError ?? undefined}
        destructive
      />
    </Box>
  );
}
