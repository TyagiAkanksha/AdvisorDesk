'use client';

import {
  Box,
  Button,
  ConfirmDialog,
  ErrorState,
  Grid,
  PageHeader,
  useBreakpointDown,
} from '@/components/common';
import {
  DELETE_CONTENT_DIALOG_TITLE,
  DELETE_LABEL,
  EDITOR_LOAD_ERROR,
  EDIT_LABEL,
  NEW_CONTENT_LABEL,
  PREVIEW_LABEL,
  deleteContentDialogBody,
} from '@/lib/copy';

import { EditorForm } from './components/EditorForm';
import { EditorMeta } from './components/EditorMeta';
import { EditorPreview } from './components/EditorPreview';
import { EditorSkeleton } from './components/EditorSkeleton';
import type { ContentEditorScreenProps } from './interface';
import { useContentEditor } from './useContentEditor';

// task-06 / PRD §2.2, §4, §5.2; phase-8 task-20 (DESIGN.md §5 C5): header meta, split live
// preview, action row, destructive delete. All state/business logic lives in `useContentEditor`
// (docs/FRONTEND-CONVENTIONS.md §3) — this component only renders props and raises events; the
// leaves under `components/` carry the markup.
export default function Component({ contentId }: ContentEditorScreenProps) {
  const editor = useContentEditor({ contentId });
  const isNarrow = useBreakpointDown('md');

  if (editor.mode === 'edit' && editor.isLoading) {
    return <EditorSkeleton />;
  }
  // fix round 1, F3: only ErrorState when there is genuinely nothing cached — a background
  // refetch failure while content IS cached must not discard in-progress typing (surfaced via
  // the snackbar instead).
  if (editor.mode === 'edit' && editor.isError && !editor.hasContent) {
    return <ErrorState message={EDITOR_LOAD_ERROR} />;
  }

  const showForm = !isNarrow || !editor.previewOpen;
  const showPreview = !isNarrow || editor.previewOpen;
  const headerTitle = editor.mode === 'edit' ? (editor.savedTitle ?? '') : NEW_CONTENT_LABEL;

  return (
    <Box>
      <PageHeader
        title={headerTitle}
        meta={
          editor.mode === 'edit' &&
          editor.status &&
          editor.createdAt &&
          editor.updatedAt &&
          editor.slug ? (
            <EditorMeta
              slug={editor.slug}
              status={editor.status}
              createdAt={editor.createdAt}
              updatedAt={editor.updatedAt}
              publishedAt={editor.publishedAt}
            />
          ) : undefined
        }
        actions={
          isNarrow ? (
            <Button variant="outlined" onClick={editor.togglePreview}>
              {editor.previewOpen ? EDIT_LABEL : PREVIEW_LABEL}
            </Button>
          ) : undefined
        }
      />
      <Grid container spacing={3}>
        {showForm ? (
          <Grid size={{ xs: 12, md: 7 }}>
            <EditorForm editor={editor} onDelete={editor.openDeleteDialog} />
          </Grid>
        ) : null}
        {showPreview ? (
          <Grid size={{ xs: 12, md: 5 }}>
            <EditorPreview title={editor.title} body={editor.body} />
          </Grid>
        ) : null}
      </Grid>
      <ConfirmDialog
        open={editor.deleteDialogOpen}
        title={DELETE_CONTENT_DIALOG_TITLE}
        body={deleteContentDialogBody(editor.savedTitle ?? editor.title)}
        confirmLabel={DELETE_LABEL}
        onConfirm={editor.confirmDelete}
        onClose={editor.closeDeleteDialog}
        isPending={editor.isDeleting}
        errorMessage={editor.deleteError ?? undefined}
        destructive
      />
    </Box>
  );
}
