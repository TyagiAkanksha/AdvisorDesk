import type { ContentStatus } from '@/types/api/content';

// phase-8 task-20 (DESIGN.md §5 C5): the header's second line in edit mode — status chip, slug,
// and the record's dates. Dumb per docs/FRONTEND-CONVENTIONS.md §3: values in, nothing else.
export interface EditorMetaProps {
  slug: string;
  status: ContentStatus;
  createdAt: string;
  updatedAt: string;
  publishedAt: string | null;
}
