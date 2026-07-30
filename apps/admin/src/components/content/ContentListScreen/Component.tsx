'use client';

import { useState } from 'react';

import {
  Box,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  IconButton,
  LoadingIndicator,
  Select,
  StatusChip,
  TextField,
} from '@/components/common';
import { useListTagsQuery } from '@/lib/api/tagsApi';
import { CONTENT_STATUS_LABELS, ContentStatus } from '@/types/api/content';
import type { ContentDto } from '@/types/api/content';

import { useContentList } from './useContentList';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...Object.values(ContentStatus).map((status) => ({
    value: status,
    label: CONTENT_STATUS_LABELS[status],
  })),
];

function formatUpdatedAt(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function Component() {
  const {
    items,
    isLoading,
    isError,
    status,
    setStatus,
    tag,
    setTag,
    q,
    setQ,
    deleteContent,
    isDeleting,
  } = useContentList();
  const { data: tags } = useListTagsQuery();
  const [deleteTarget, setDeleteTarget] = useState<ContentDto | null>(null);

  const tagOptions = [
    { value: '', label: 'All tags' },
    ...(tags ?? []).map((item) => ({ value: item.name, label: item.name })),
  ];

  const handleConfirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    try {
      await deleteContent(deleteTarget.id);
      setDeleteTarget(null);
    } catch {
      // Deletion failed — leave the dialog open so the admin can retry or cancel. A
      // friendly-error surface (snackbar, per §9) is out of scope for this task.
    }
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
        <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
          <Box component="thead">
            <Box component="tr">
              <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
                Title
              </Box>
              <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
                Status
              </Box>
              <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
                Tags
              </Box>
              <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
                Updated
              </Box>
              <Box component="th" sx={{ p: 1 }} />
            </Box>
          </Box>
          <Box component="tbody">
            {items.map((item) => (
              <Box
                component="tr"
                key={item.id}
                sx={{ borderTop: '1px solid', borderColor: 'divider' }}
              >
                <Box component="td" sx={{ p: 1 }}>
                  {item.title}
                </Box>
                <Box component="td" sx={{ p: 1 }}>
                  <StatusChip status={item.status} />
                </Box>
                <Box component="td" sx={{ p: 1 }}>
                  {item.tags.map((itemTag) => (
                    <Box component="span" key={itemTag} sx={{ mr: 0.5 }}>
                      {itemTag}
                    </Box>
                  ))}
                </Box>
                <Box component="td" sx={{ p: 1 }}>
                  {formatUpdatedAt(item.updated_at)}
                </Box>
                <Box component="td" sx={{ p: 1 }}>
                  <IconButton
                    name="Delete"
                    label={`Delete ${item.title}`}
                    onClick={() => setDeleteTarget(item)}
                  />
                </Box>
              </Box>
            ))}
          </Box>
        </Box>
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete content"
        body={`“${deleteTarget?.title ?? ''}” will be permanently deleted — there is no restore.`}
        confirmLabel="Delete"
        onConfirm={handleConfirmDelete}
        onClose={() => setDeleteTarget(null)}
        isPending={isDeleting}
      />
    </Box>
  );
}
