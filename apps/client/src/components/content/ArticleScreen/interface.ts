import type { PublicContentDetail, PublicContentSummary } from '@/types';

export interface ArticleScreenProps {
  article: PublicContentDetail;
  related: PublicContentSummary[]; // already computed by the page; may be []
}
