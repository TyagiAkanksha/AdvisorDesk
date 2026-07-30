import { skipToken } from '@reduxjs/toolkit/query/react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import {
  useArchiveContentMutation,
  useCreateContentMutation,
  useDeleteContentMutation,
  useGetContentQuery,
  usePublishContentMutation,
  useUpdateContentMutation,
} from '@/lib/api/contentApi';
import { extractErrorMessage } from '@/lib/errorMessage';
import { ContentStatus } from '@/types/api/content';
import type { ContentUpdateDto } from '@/types/api/content';

const SAVE_ERROR_FALLBACK = "Couldn't save this item. Please try again.";
const TRANSITION_ERROR_FALLBACK = "Couldn't update this item's status. Please try again.";
const DELETE_ERROR_FALLBACK = "Couldn't delete this item. Please try again.";

// task-06 Interfaces: ALL editor state (fields, dirty tracking, transition dispatch, snackbar
// state) lives here so ContentEditorScreen stays a dumb renderer (docs/FRONTEND-CONVENTIONS.md
// §3). `contentId` omitted => NEW mode (blank form); a string id => EDIT mode.
export interface UseContentEditorArgs {
  contentId?: string;
}

export interface UseContentEditorResult {
  mode: 'new' | 'edit';
  isLoading: boolean;
  isError: boolean;
  title: string;
  setTitle: (value: string) => void;
  body: string;
  setBody: (value: string) => void;
  tags: string[];
  setTags: (value: string[]) => void;
  /** Display-only — never rendered as an editable control (PRD §4 slug immutability). */
  slug: string | null;
  status: ContentStatus | null;
  submitLabel: 'Create' | 'Save';
  canSubmit: boolean;
  isSaving: boolean;
  onSubmit: () => void;
  canPublish: boolean;
  canArchive: boolean;
  isTransitioning: boolean;
  onPublish: () => void;
  onArchive: () => void;
  isDeleting: boolean;
  deleteDialogOpen: boolean;
  deleteError: string | null;
  openDeleteDialog: () => void;
  closeDeleteDialog: () => void;
  confirmDelete: () => void;
  previewOpen: boolean;
  togglePreview: () => void;
  snackbarMessage: string | null;
  closeSnackbar: () => void;
}

function tagsEqual(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

// Mirrors app.services.tags._normalize_tag_name (PRD §4.1: lowercase, hyphenated) so a tag
// typed here matches what the server would store — any run of non-`[a-z0-9]` characters
// collapses to one hyphen, leading/trailing hyphens are stripped.
export function normalizeTag(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function useContentEditor({ contentId }: UseContentEditorArgs): UseContentEditorResult {
  const router = useRouter();
  const mode: 'new' | 'edit' = contentId ? 'edit' : 'new';

  const { data: content, isLoading, isError } = useGetContentQuery(contentId ?? skipToken);

  const [createContent, { isLoading: isCreating }] = useCreateContentMutation();
  const [updateContent, { isLoading: isUpdating }] = useUpdateContentMutation();
  const [publishContent, { isLoading: isPublishing }] = usePublishContentMutation();
  const [archiveContent, { isLoading: isArchiving }] = useArchiveContentMutation();
  const [deleteContentMutation, { isLoading: isDeleting }] = useDeleteContentMutation();

  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Reseed the editable fields only when a *different* record has finished loading (by id) —
  // a same-id refetch (e.g. after Publish/Archive, which only change status/published_at)
  // must never clobber an in-progress, unsaved edit. "Adjusting state during render" (not an
  // effect, react.dev's own recommended pattern for this): React discards this render and
  // immediately re-renders with the new state before anything is painted, and the guard
  // condition then goes false, so this stabilizes in one extra pass with no visible flicker.
  const [seededContentId, setSeededContentId] = useState<string | undefined>(undefined);
  if (content && content.id !== seededContentId) {
    setSeededContentId(content.id);
    setTitle(content.title);
    setBody(content.body_md);
    setTags(content.tags);
  }

  const setTagsNormalized = (next: string[]) => {
    setTags(next.map(normalizeTag).filter((value) => value.length > 0));
  };

  const isDirty =
    mode === 'edit' && content
      ? title !== content.title || body !== content.body_md || !tagsEqual(tags, content.tags)
      : false;
  const canSubmit = mode === 'new' ? title.trim().length > 0 : isDirty;

  const onSubmit = () => {
    if (mode === 'new') {
      void createContent({ title, body_md: body, tags })
        .unwrap()
        .then((created) => {
          router.push(`/content/${created.id}`);
        })
        .catch((error: unknown) => {
          setSnackbarMessage(extractErrorMessage(error, SAVE_ERROR_FALLBACK));
        });
      return;
    }
    if (!contentId || !content || !isDirty) {
      return;
    }
    const patch: ContentUpdateDto = {};
    if (title !== content.title) {
      patch.title = title;
    }
    if (body !== content.body_md) {
      patch.body_md = body;
    }
    if (!tagsEqual(tags, content.tags)) {
      patch.tags = tags;
    }
    void updateContent({ id: contentId, patch })
      .unwrap()
      .catch((error: unknown) => {
        setSnackbarMessage(extractErrorMessage(error, SAVE_ERROR_FALLBACK));
      });
  };

  const canPublish =
    mode === 'edit' &&
    (content?.status === ContentStatus.Draft || content?.status === ContentStatus.Archived);
  const canArchive = mode === 'edit' && content?.status === ContentStatus.Published;

  const onPublish = () => {
    if (!contentId) {
      return;
    }
    void publishContent(contentId)
      .unwrap()
      .catch((error: unknown) => {
        setSnackbarMessage(extractErrorMessage(error, TRANSITION_ERROR_FALLBACK));
      });
  };

  const onArchive = () => {
    if (!contentId) {
      return;
    }
    void archiveContent(contentId)
      .unwrap()
      .catch((error: unknown) => {
        setSnackbarMessage(extractErrorMessage(error, TRANSITION_ERROR_FALLBACK));
      });
  };

  const openDeleteDialog = () => {
    setDeleteError(null);
    setDeleteDialogOpen(true);
  };
  const closeDeleteDialog = () => {
    setDeleteDialogOpen(false);
    setDeleteError(null);
  };
  const confirmDelete = () => {
    if (!contentId) {
      return;
    }
    setDeleteError(null);
    void deleteContentMutation(contentId)
      .unwrap()
      .then(() => {
        setDeleteDialogOpen(false);
        router.push('/content');
      })
      .catch((error: unknown) => {
        setDeleteError(extractErrorMessage(error, DELETE_ERROR_FALLBACK));
      });
  };

  return {
    mode,
    isLoading,
    isError,
    title,
    setTitle,
    body,
    setBody,
    tags,
    setTags: setTagsNormalized,
    slug: content?.slug ?? null,
    status: content?.status ?? null,
    submitLabel: mode === 'new' ? 'Create' : 'Save',
    canSubmit,
    isSaving: isCreating || isUpdating,
    onSubmit,
    canPublish,
    canArchive,
    isTransitioning: isPublishing || isArchiving,
    onPublish,
    onArchive,
    isDeleting,
    deleteDialogOpen,
    deleteError,
    openDeleteDialog,
    closeDeleteDialog,
    confirmDelete,
    previewOpen,
    togglePreview: () => setPreviewOpen((prev) => !prev),
    snackbarMessage,
    closeSnackbar: () => setSnackbarMessage(null),
  };
}
