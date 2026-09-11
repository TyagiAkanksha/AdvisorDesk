'use client';

import {
  Autocomplete,
  Box,
  Button,
  ConfirmDialog,
  ErrorState,
  LoadingIndicator,
  StatusChip,
  TextField,
} from '@/components/common';

import { MarkdownPreview } from '../MarkdownPreview';
import type { ContentEditorScreenProps } from './interface';
import { useContentEditor } from './useContentEditor';

// task-06 / PRD §2.2, §4, §5.2: create/edit a content item and drive its draft -> published ->
// archived transitions. All state and business logic lives in `useContentEditor`
// (docs/FRONTEND-CONVENTIONS.md §3) — this component only renders props and raises events.
export default function Component({ contentId }: ContentEditorScreenProps) {
  const editor = useContentEditor({ contentId });

  if (editor.mode === 'edit' && editor.isLoading) {
    return <LoadingIndicator />;
  }
  // fix round 1, F3: only replace the form with ErrorState when there is genuinely nothing to
  // show (no cached content at all). A background refetch failure while content IS cached
  // (e.g. after another mutation's tag invalidation) must not unmount the form and discard
  // in-progress typing — `useContentEditor` surfaces that case through the snackbar instead.
  if (editor.mode === 'edit' && editor.isError && !editor.hasContent) {
    return <ErrorState message="Couldn't load this item." />;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 720 }}>
      {editor.mode === 'edit' ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.secondary' }}>
          <Box component="span">Slug:</Box>
          <Box component="span">{editor.slug}</Box>
          {editor.status ? <StatusChip status={editor.status} /> : null}
        </Box>
      ) : null}

      <TextField label="Title" value={editor.title} onChange={editor.setTitle} fullWidth />
      <TextField
        label="Body (Markdown)"
        value={editor.body}
        onChange={editor.setBody}
        multiline
        minRows={10}
        fullWidth
      />
      <Autocomplete label="Tags" value={editor.tags} onChange={editor.setTags} />

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Button
          onClick={editor.onSubmit}
          disabled={!editor.canSubmit || editor.isSaving}
          variant="contained"
        >
          {editor.submitLabel}
        </Button>
        <Button onClick={editor.togglePreview} variant="outlined">
          Preview
        </Button>
        {editor.mode === 'edit' ? (
          <>
            {/* fix round 2, N3: `isSaving` (not just `isTransitioning`) also disables Publish —
                onPublish's own save-then-publish PATCH runs under `isSaving`, before
                `isTransitioning` ever goes true, so without this a double-click fired
                PATCH -> PATCH -> PUBLISH -> PUBLISH (two stale-body embeds). Archive gets the
                same guard for consistency, even though it never PATCHes. */}
            <Button
              onClick={editor.onPublish}
              disabled={!editor.canPublish || editor.isTransitioning || editor.isSaving}
              variant="outlined"
            >
              Publish
            </Button>
            <Button
              onClick={editor.onArchive}
              disabled={!editor.canArchive || editor.isTransitioning || editor.isSaving}
              variant="outlined"
            >
              Archive
            </Button>
            <Button onClick={editor.openDeleteDialog} color="secondary" variant="outlined">
              Delete
            </Button>
          </>
        ) : null}
      </Box>

      {editor.previewOpen ? (
        <Box
          component="section"
          aria-label="Markdown preview"
          sx={{ border: '1px solid', borderColor: 'divider', p: 2 }}
        >
          <MarkdownPreview markdown={editor.body} />
        </Box>
      ) : null}

      <ConfirmDialog
        open={editor.deleteDialogOpen}
        title="Delete content"
        body={`“${editor.title}” will be permanently deleted — there is no restore.`}
        confirmLabel="Delete"
        onConfirm={editor.confirmDelete}
        onClose={editor.closeDeleteDialog}
        isPending={editor.isDeleting}
        errorMessage={editor.deleteError ?? undefined}
      />
    </Box>
  );
}
