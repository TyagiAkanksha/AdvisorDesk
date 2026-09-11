import { Autocomplete, Box, Button, Stack, TextField, Tooltip } from '@/components/common';
import {
  ARCHIVE_LABEL,
  BODY_FIELD_LABEL,
  DELETE_LABEL,
  PUBLISH_ALREADY_TOOLTIP,
  PUBLISH_LABEL,
  PUBLISH_SAVE_FIRST_TOOLTIP,
  TAGS_FIELD_LABEL,
  TITLE_FIELD_LABEL,
} from '@/lib/copy';
import { ContentStatus } from '@/types/api/content';

import type { EditorFormProps } from './interface';

// phase-8 task-20 (DESIGN.md §5 C5): the real `<form>` (native Enter-submits-on-Title behavior,
// no bespoke keydown handling needed) plus the action row. Dumb per docs/FRONTEND-CONVENTIONS.md
// §3 — every value and callback comes from the hook result the screen passes down; this leaf
// makes no requests and holds no state of its own.
export default function Component({ editor, onDelete }: EditorFormProps) {
  const reason =
    editor.mode === 'new'
      ? PUBLISH_SAVE_FIRST_TOOLTIP
      : editor.status === ContentStatus.Published
        ? PUBLISH_ALREADY_TOOLTIP
        : null;
  const publishButton = (
    <Button
      variant="outlined"
      onClick={editor.onPublish}
      disabled={reason !== null || !editor.canPublish || editor.isTransitioning || editor.isSaving}
    >
      {PUBLISH_LABEL}
    </Button>
  );
  // A disabled button cannot receive pointer events, so hovering it never fires a Tooltip's own
  // listeners — MUI's documented fix is to wrap it in a `<span>` and put the listeners there.
  const publish = reason ? (
    <Tooltip title={reason} describeChild>
      <span>{publishButton}</span>
    </Tooltip>
  ) : (
    publishButton
  );

  return (
    // A plain <form> on purpose (same precedent as MarkdownPreview's raw <img>): common/Box is
    // typed against <div> attributes (default `component`), so it has no `noValidate` — a native
    // element with one inline attribute is the smaller change than widening the primitive.
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        editor.onSubmit();
      }}
    >
      <Stack spacing={2}>
        <TextField
          label={TITLE_FIELD_LABEL}
          value={editor.title}
          onChange={editor.setTitle}
          required
          error={editor.titleError !== null}
          helperText={editor.titleError ?? undefined}
          onBlur={editor.onTitleBlur}
          fullWidth
        />
        <TextField
          label={BODY_FIELD_LABEL}
          value={editor.body}
          onChange={editor.setBody}
          multiline
          minRows={16}
          monospace
          fullWidth
        />
        <Autocomplete
          label={TAGS_FIELD_LABEL}
          value={editor.tags}
          onChange={editor.setTags}
          options={editor.tagOptions}
        />
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <Button type="submit" variant="contained" disabled={!editor.canSubmit || editor.isSaving}>
            {editor.submitLabel}
          </Button>
          {publish}
          {editor.canArchive ? (
            <Button
              variant="outlined"
              onClick={editor.onArchive}
              disabled={editor.isTransitioning || editor.isSaving}
            >
              {ARCHIVE_LABEL}
            </Button>
          ) : null}
          <Box sx={{ flexGrow: 1 }} />
          {editor.mode === 'edit' ? (
            <Button variant="outlined" color="error" onClick={onDelete}>
              {DELETE_LABEL}
            </Button>
          ) : null}
        </Stack>
      </Stack>
    </form>
  );
}
