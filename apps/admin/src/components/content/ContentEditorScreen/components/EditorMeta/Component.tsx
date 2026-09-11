import { Divider, Stack, StatusChip, Typography } from '@/components/common';
import { formatDate } from '@/lib/format';
import { META_CREATED_PREFIX, META_PUBLISHED_PREFIX, META_UPDATED_PREFIX } from '@/lib/copy';

import type { EditorMetaProps } from './interface';

// phase-8 task-20 (DESIGN.md §5 C5): the PageHeader's meta line in edit mode — status chip,
// slug, and dates, each its own element so an exact-text query (e.g. "the slug is visible")
// keeps working against a single node.
export default function Component({
  slug,
  status,
  createdAt,
  updatedAt,
  publishedAt,
}: EditorMetaProps) {
  return (
    <Stack
      direction="row"
      spacing={{ xs: 1, md: 1 }}
      // p8 final, F9: the vertical dividers between fields (Status | slug | Created | Updated |
      // Published) read fine on one line at desktop width, but once the row wraps on a phone
      // they land mid-line and look like stray marks — hide them below `md` and let `rowGap`
      // keep the wrapped lines readably spaced instead.
      divider={
        <Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', md: 'block' } }} />
      }
      sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 1 }}
    >
      <StatusChip status={status} />
      <Typography variant="body2" color="text.secondary" component="span">
        {slug}
      </Typography>
      <Typography variant="body2" color="text.secondary" component="span">
        {`${META_CREATED_PREFIX} ${formatDate(createdAt)}`}
      </Typography>
      <Typography variant="body2" color="text.secondary" component="span">
        {`${META_UPDATED_PREFIX} ${formatDate(updatedAt)}`}
      </Typography>
      {publishedAt ? (
        <Typography variant="body2" color="text.secondary" component="span">
          {`${META_PUBLISHED_PREFIX} ${formatDate(publishedAt)}`}
        </Typography>
      ) : null}
    </Stack>
  );
}
