import type { Citation } from '../useChatStream';

// task-05 Interfaces: "numbered `[n]` chips linking to `/content/{slug}`... order = server order
// (first use)". `citations` arrives already deduped-and-ordered by the server
// (`app.rag.synthesis.dedupe_citations`) — this component renders it verbatim, no re-sorting.
export interface CitationListProps {
  citations: Citation[];
}
