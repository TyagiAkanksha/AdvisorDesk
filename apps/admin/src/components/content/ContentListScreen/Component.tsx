'use client';

import { useState } from 'react';

import {
  Box,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  LoadingIndicator,
  Pagination,
  Select,
  TextField,
} from '@/components/common';
import { useListTagsQuery } from '@/lib/api/tagsApi';
import { CONTENT_STATUS_LABELS, ContentStatus } from '@/types/api/content';
import type { ContentDto } from '@/types/api/content';

import { ContentTable } from './components/ContentTable';
import { useContentList } from './useContentList';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...Object.values(ContentStatus).map((status) => ({
    value: status,
    label: CONTENT_STATUS_LABELS[status],
  })),
];

export default function Component() {
  const {
    items,
    total,
    page,
    pageSize,
    isLoading,
    isError,
    status,
    setStatus,
    tag,
    setTag,
    q,
    setQ,
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
      // fix round 1, F2: `deleteError` (from useContentList) now surfaces the failure inside
      // the still-open ConfirmDialog — the admin can retry immediately or cancel.
    }
  };

  const handleCloseDialog = () => {
    setDeleteTarget(null);
    clearDeleteError();
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        <Select
          label="Status"
          value={status}
          onChange={(value) => setStatus(value as ContentStatus | '')}
          options={STATUS_OPTIONS}
        />
        <Select label="Tag" value={tag} onChange={setTag} options={tagOptions} />
        <TextField label="Search" value={q} onChange={setQ} placeholder="Search by title…" />
      </Box>

      {isLoading ? <LoadingIndicator /> : null}
      {!isLoading && isError ? <ErrorState message="Couldn't load content." /> : null}
      {!isLoading && !isError && items.length === 0 ? (
        <EmptyState message="No content found." />
      ) : null}
      {!isLoading && !isError && items.length > 0 ? (
        <ContentTable items={items} onDeleteClick={handleDeleteClick} />
      ) : null}
      {/* fix round 2, C2: hoisted out of the items.length>0 branch — a stranded empty page
          (e.g. deleting the sole row on page 2, whose refetch then answers zero items) must
          not unmount the pager along with the table, or there is no way back to an earlier
          page except side effects. EmptyState still replaces only the table above. */}
      {!isLoading && !isError ? (
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
      />
    </Box>
  );
}
