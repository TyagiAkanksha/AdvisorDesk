import type { PublicContentSummary } from '@/types';

export interface ContentListScreenProps {
  /** Items to render — already filtered by the page. */
  items: PublicContentSummary[];
  /** Every tag in the full (unfiltered) list. Empty when there is no content at all. */
  tags: string[];
  selectedTag: string | null;
}
