import { skipToken } from '@reduxjs/toolkit/query/react';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { useSnackbar } from '@/components/common';
import {
  useArchiveContentMutation,
  useCreateContentMutation,
  useDeleteContentMutation,
  useGetContentQuery,
  usePublishContentMutation,
  useUpdateContentMutation,
} from '@/lib/api/contentApi';
import { useListTagsQuery } from '@/lib/api/tagsApi';
import {
  CONTENT_ARCHIVED_MESSAGE,
  CONTENT_DELETED_MESSAGE,
  CONTENT_PUBLISHED_MESSAGE,
  CONTENT_SAVED_MESSAGE,
  DELETE_ERROR_FALLBACK,
  EDITOR_REFRESH_ERROR,
  SAVE_ERROR_FALLBACK,
  TITLE_REQUIRED_MESSAGE,
  TRANSITION_ERROR_FALLBACK,
} from '@/lib/copy';
import { extractErrorMessage } from '@/lib/errorMessage';
import { ContentStatus } from '@/types/api/content';
import type { ContentUpdateDto } from '@/types/api/content';

// task-06 Interfaces: ALL editor state (fields, dirty tracking, transition dispatch) lives here
// so ContentEditorScreen stays a dumb renderer (docs/FRONTEND-CONVENTIONS.md §3). `contentId`
// omitted => NEW mode (blank form); a string id => EDIT mode.
export interface UseContentEditorArgs {
  contentId?: string;
}

export interface UseContentEditorResult {
  mode: 'new' | 'edit';
  isLoading: boolean;
  isError: boolean;
  /** fix round 1, F3: `true` once a record has been loaded into `content` at least once — lets
   * the Component distinguish "nothing to show, replace the form with ErrorState" from "a
   * background refetch failed but we still have a cached item, keep the form". */
  hasContent: boolean;
  /** Header data from the loaded record (edit mode); null in new mode / before load. */
  savedTitle: string | null;
  slug: string | null;
  status: ContentStatus | null;
  createdAt: string | null;
  updatedAt: string | null;
  publishedAt: string | null;
  title: string;
  setTitle: (value: string) => void;
  /** TITLE_REQUIRED_MESSAGE once the field was blurred or a submit was attempted while blank;
   * null otherwise. */
  titleError: string | null;
  onTitleBlur: () => void;
  body: string;
  setBody: (value: string) => void;
  tags: string[];
  setTags: (value: string[]) => void;
  /** Existing tag names (GET /tags) for the Autocomplete; [] until loaded or on failure. */
  tagOptions: string[];
  /** New mode: any field non-empty. Edit mode: differs from the loaded record (order-insensitive
   * tags). */
  isDirty: boolean;
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
}

// fix round 1, F4: order-INsensitive — the server always returns `tags` sorted alphabetically
// (app.services.tags), while the client appends newly-typed tags at the end of the array, so a
// positional comparison went false-not-equal for same-membership tag sets in a different order
// (phantom dirty: Save never re-disabled after a refetch echoed the sorted list back). Compare
// sorted copies; the array actually SENT to the server (`tags`, untouched) still preserves the
// user's own order.
function tagsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((value, index) => value === sortedB[index]);
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
  const { success: notifySuccess, error: notifyError } = useSnackbar();
  const mode: 'new' | 'edit' = contentId ? 'edit' : 'new';

  const { data: content, isLoading, isError } = useGetContentQuery(contentId ?? skipToken);
  const { data: tagsData } = useListTagsQuery();

  const [createContent, { isLoading: isCreating }] = useCreateContentMutation();
  const [updateContent, { isLoading: isUpdating }] = useUpdateContentMutation();
  const [publishContent, { isLoading: isPublishing }] = usePublishContentMutation();
  const [archiveContent, { isLoading: isArchiving }] = useArchiveContentMutation();
  const [deleteContentMutation, { isLoading: isDeleting }] = useDeleteContentMutation();

  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [titleBlurred, setTitleBlurred] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);

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

  const tagOptions = tagsData?.map((tag) => tag.name) ?? [];

  const trimmedTitle = title.trim();
  const titleError =
    (titleBlurred || submitAttempted) && trimmedTitle.length === 0 ? TITLE_REQUIRED_MESSAGE : null;
  const onTitleBlur = () => setTitleBlurred(true);

  // fix round 1, F3: `content` (RTK Query's `data`) keeps the last successfully fetched value
  // even while a later background refetch is in flight or has failed — this is `true` once
  // we've ever had something to show for this record.
  const hasContent = mode === 'edit' && content !== undefined;

  const isDirty =
    mode === 'new'
      ? title.length > 0 || body.length > 0 || tags.length > 0
      : content
        ? trimmedTitle !== content.title ||
          body !== content.body_md ||
          !tagsEqual(tags, content.tags)
        : false;
  const canSubmit = mode === 'new' ? trimmedTitle.length > 0 : isDirty;

  // Dirty guard: warns on a real page unload/reload/close while there is unsaved work. In-app
  // navigation is NOT blocked — the App Router has no supported navigation blocker
  // (DESIGN.md §C5) — so this only ever fires for `beforeunload`.
  useEffect(() => {
    if (!isDirty) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [isDirty]);

  // fix round 1, F2: shared by onSubmit's EDIT branch and onPublish's save-then-publish path —
  // tri-state PATCH body (only the fields that actually changed), built from current field
  // state against the last-known `content`. `null` when there is nothing to diff against yet.
  const buildPatch = (): ContentUpdateDto | null => {
    if (!content) {
      return null;
    }
    const patch: ContentUpdateDto = {};
    if (trimmedTitle !== content.title) {
      patch.title = trimmedTitle;
    }
    if (body !== content.body_md) {
      patch.body_md = body;
    }
    if (!tagsEqual(tags, content.tags)) {
      patch.tags = tags;
    }
    return patch;
  };

  const onSubmit = () => {
    if (trimmedTitle.length === 0) {
      setSubmitAttempted(true);
      return;
    }
    if (mode === 'new') {
      void createContent({ title: trimmedTitle, body_md: body, tags })
        .unwrap()
        .then((created) => {
          notifySuccess(CONTENT_SAVED_MESSAGE);
          router.push(`/content/${created.id}`);
        })
        .catch((error: unknown) => {
          notifyError(extractErrorMessage(error, SAVE_ERROR_FALLBACK));
        });
      return;
    }
    if (!contentId || !isDirty) {
      return;
    }
    const patch = buildPatch();
    if (!patch) {
      return;
    }
    void updateContent({ id: contentId, patch })
      .unwrap()
      .then(() => {
        notifySuccess(CONTENT_SAVED_MESSAGE);
      })
      .catch((error: unknown) => {
        notifyError(extractErrorMessage(error, SAVE_ERROR_FALLBACK));
      });
  };

  const canPublish =
    mode === 'edit' &&
    (content?.status === ContentStatus.Draft || content?.status === ContentStatus.Archived);
  const canArchive = mode === 'edit' && content?.status === ContentStatus.Published;

  // fix round 1, F2 (probe-confirmed): Publish used to POST /publish straight away, so an
  // unsaved edit never reached the server before phase-3 embedded the STALE stored body.
  // Chosen semantics — SAVE-THEN-PUBLISH: a dirty editor PATCHes first; publish is only
  // dispatched after that PATCH succeeds; a PATCH failure surfaces via the snackbar and never
  // reaches publishContent at all. Archive is intentionally untouched (it doesn't embed
  // anything, so there is nothing stale to save first). task-19: the save-then-publish path
  // reports ONLY "Published" — the intermediate PATCH stays silent so the admin isn't told
  // "Saved" and then immediately "Published" for one click.
  const onPublish = () => {
    if (!contentId) {
      return;
    }
    const dispatchPublish = () => {
      void publishContent(contentId)
        .unwrap()
        .then(() => {
          notifySuccess(CONTENT_PUBLISHED_MESSAGE);
        })
        .catch((error: unknown) => {
          notifyError(extractErrorMessage(error, TRANSITION_ERROR_FALLBACK));
        });
    };
    if (!isDirty) {
      dispatchPublish();
      return;
    }
    const patch = buildPatch();
    if (!patch) {
      return;
    }
    void updateContent({ id: contentId, patch })
      .unwrap()
      .then(dispatchPublish)
      .catch((error: unknown) => {
        notifyError(extractErrorMessage(error, SAVE_ERROR_FALLBACK));
      });
  };

  const onArchive = () => {
    if (!contentId) {
      return;
    }
    void archiveContent(contentId)
      .unwrap()
      .then(() => {
        notifySuccess(CONTENT_ARCHIVED_MESSAGE);
      })
      .catch((error: unknown) => {
        notifyError(extractErrorMessage(error, TRANSITION_ERROR_FALLBACK));
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
        notifySuccess(CONTENT_DELETED_MESSAGE);
        router.push('/content');
      })
      .catch((error: unknown) => {
        setDeleteError(extractErrorMessage(error, DELETE_ERROR_FALLBACK));
      });
  };

  // fix round 1, F3: a background refetch (e.g. the tag-invalidation-driven `getContent` refetch
  // after a successful Save/Publish/Archive elsewhere) failing while a previously loaded item is
  // still cached must not tear down the form — surfaced through the global snackbar instead.
  // task-19: reported once per failure episode via the rising edge of `hasContent && isError`
  // (same idiom as useDashboard/useContentList's background-refresh notices) — the
  // SnackbarProvider owns the notice's own dismiss/auto-hide lifecycle, so no dismissal state is
  // needed here.
  const isBackgroundRefreshFailing = mode === 'edit' && hasContent && isError;
  const wasBackgroundRefreshFailing = useRef(false);
  useEffect(() => {
    if (isBackgroundRefreshFailing && !wasBackgroundRefreshFailing.current) {
      notifyError(EDITOR_REFRESH_ERROR);
    }
    wasBackgroundRefreshFailing.current = isBackgroundRefreshFailing;
  }, [isBackgroundRefreshFailing, notifyError]);

  return {
    mode,
    isLoading,
    isError,
    hasContent,
    savedTitle: content?.title ?? null,
    slug: content?.slug ?? null,
    status: content?.status ?? null,
    createdAt: content?.created_at ?? null,
    updatedAt: content?.updated_at ?? null,
    publishedAt: content?.published_at ?? null,
    title,
    setTitle,
    titleError,
    onTitleBlur,
    body,
    setBody,
    tags,
    setTags: setTagsNormalized,
    tagOptions,
    isDirty,
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
  };
}
