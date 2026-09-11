import type { SelectOption } from '@/components/common';
import type { ContentStatus } from '@/types/api/content';

// phase-8 task-18 (DESIGN.md §2, §5 C4): dumb per docs/FRONTEND-CONVENTIONS.md §3 — filter
// values and tag options in, one change callback per field plus a clear callback out.
export interface ContentFiltersProps {
  status: ContentStatus | '';
  tag: string;
  q: string;
  /** Already includes `{ value: '', label: 'All tags' }` first. */
  tagOptions: SelectOption[];
  hasFilters: boolean;
  onStatusChange: (status: ContentStatus | '') => void;
  onTagChange: (tag: string) => void;
  onQChange: (q: string) => void;
  onClear: () => void;
}
