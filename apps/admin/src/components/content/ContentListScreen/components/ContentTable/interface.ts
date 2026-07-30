import type { ContentDto } from '@/types/api/content';

// fix round 1, F1 (M1): extracted out of ContentListScreen/Component.tsx (which was 157 lines
// and growing) — dumb per docs/FRONTEND-CONVENTIONS.md §3: rows in, one click callback out.
export interface ContentTableProps {
  items: ContentDto[];
  onDeleteClick: (item: ContentDto) => void;
}
