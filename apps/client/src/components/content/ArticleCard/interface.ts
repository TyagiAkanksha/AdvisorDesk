import type { PublicContentSummary } from '@/types';

export interface ArticleCardProps {
  item: PublicContentSummary;
  /** Heading level for the card title — 'h3' when the card sits under a section h2 (Related articles). */
  titleAs?: 'h2' | 'h3';
}
