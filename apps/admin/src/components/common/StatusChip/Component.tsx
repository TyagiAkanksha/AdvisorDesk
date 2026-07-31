import MuiChip from '@mui/material/Chip';
import type { ChipProps as MuiChipProps } from '@mui/material/Chip';

import { CONTENT_STATUS_LABELS, ContentStatus } from '@/types/api/content';

import type { StatusChipProps } from './interface';

// task-05: the ONE typed lookup content-status colors come from — no per-call color logic
// anywhere else (docs/plans/phase-2-auth-cms-crud/task-05-admin-dashboard-list.md).
const STATUS_CHIP_COLOR: Record<ContentStatus, MuiChipProps['color']> = {
  [ContentStatus.Draft]: 'default',
  [ContentStatus.Published]: 'success',
  [ContentStatus.Archived]: 'warning',
};

export default function Component({ status }: StatusChipProps) {
  return (
    <MuiChip label={CONTENT_STATUS_LABELS[status]} color={STATUS_CHIP_COLOR[status]} size="small" />
  );
}
