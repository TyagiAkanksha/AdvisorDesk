import type { components } from '../generated/schema';

// src/types/ is the only layer allowed to touch `components['schemas']`
// (docs/FRONTEND-CONVENTIONS.md §5) — everything else imports these named types.
export type ContentDto = components['schemas']['ContentResponse'];
export type ContentListDto = components['schemas']['ContentListResponse'];

// `as const` object + `keyof typeof` value-union (docs/FRONTEND-CONVENTIONS.md §5) — never a
// TS `enum`, never a bare `string`. Values mirror `ContentResponse.status`'s wire values
// exactly (task-05 Interfaces: `'draft'|'published'|'archived'`).
export const ContentStatus = {
  Draft: 'draft',
  Published: 'published',
  Archived: 'archived',
} as const;
export type ContentStatus = (typeof ContentStatus)[keyof typeof ContentStatus];

// One canonical human-readable label per status, kept beside the enum it labels rather than
// duplicated in each consumer — `common/StatusChip` and `dashboard/DashboardScreen` both read
// it (task-05).
export const CONTENT_STATUS_LABELS: Record<ContentStatus, string> = {
  [ContentStatus.Draft]: 'Draft',
  [ContentStatus.Published]: 'Published',
  [ContentStatus.Archived]: 'Archived',
};
