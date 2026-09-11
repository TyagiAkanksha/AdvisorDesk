import { Box, Paper, Typography } from '@/components/common';
import { MarkdownPreview } from '@/components/content/MarkdownPreview';
import { stripLeadingHeading } from '@/lib/markdown';
import { PREVIEW_EMPTY_MESSAGE, PREVIEW_LABEL } from '@/lib/copy';

import type { EditorPreviewProps } from './interface';

// phase-8 task-20 (DESIGN.md §5 C5, §3 A2): the live preview mirrors the public article page —
// `stripLeadingHeading` drops the body's own leading `# Title` (the screen already renders the
// title as its h1) and `headingOffset={1}` demotes the remaining headings so a `##` in the
// source renders as an `<h3>`, keeping the document outline correct under the screen's own h1.
// 88 = 64px AppBar + 24px main padding at `md`+ (the offset the sticky preview must clear).
export default function Component({ title, body }: EditorPreviewProps) {
  const stripped = stripLeadingHeading(body, title);
  // p8 final, F17: a blank new-mode form (or an edit whose entire body is just its own title
  // heading) has nothing to render — an explicit empty message instead of a blank preview panel.
  const isEmpty = stripped.trim() === '';

  return (
    <Paper variant="outlined" sx={{ p: 3, position: { md: 'sticky' }, top: { md: 88 } }}>
      <Box component="section" aria-label={PREVIEW_LABEL}>
        {isEmpty ? (
          <Typography variant="body2" color="text.secondary">
            {PREVIEW_EMPTY_MESSAGE}
          </Typography>
        ) : (
          <MarkdownPreview markdown={stripped} variant="article" headingOffset={1} />
        )}
      </Box>
    </Paper>
  );
}
