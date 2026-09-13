import { IconButton, Stack } from '@/components/common';
import { FEEDBACK_DOWN_LABEL, FEEDBACK_UP_LABEL } from '@/lib/copy';

import type { FeedbackButtonsProps } from './interface';

// phase-9 task-17 (DESIGN §A/D2). Dumb leaf: it renders the current rating and raises a choice —
// no state, no fetching, no conditional on `role` (the parent decides whether to render it at
// all). `pressed`/`aria-pressed` (docs/FRONTEND-CONVENTIONS.md §9) is what tells an assistive-tech
// user which thumb, if either, is currently chosen.
export default function Component({ value, disabled, onSelect }: FeedbackButtonsProps) {
  return (
    <Stack direction="row" spacing={0.5}>
      <IconButton
        name="ThumbUpAltOutlined"
        label={FEEDBACK_UP_LABEL}
        size="small"
        pressed={value === 1}
        color={value === 1 ? 'primary' : 'default'}
        onClick={() => onSelect(1)}
        disabled={disabled}
      />
      <IconButton
        name="ThumbDownAltOutlined"
        label={FEEDBACK_DOWN_LABEL}
        size="small"
        pressed={value === -1}
        color={value === -1 ? 'primary' : 'default'}
        onClick={() => onSelect(-1)}
        disabled={disabled}
      />
    </Stack>
  );
}
