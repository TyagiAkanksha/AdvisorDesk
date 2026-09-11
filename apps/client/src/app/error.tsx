'use client';

import { ErrorState, PageContainer } from '@/components/common';
import { PAGE_ERROR_MESSAGE, RETRY_LABEL } from '@/lib/copy';

// Next.js error-boundary convention: MUST be a Client Component. Friendly copy via `ErrorState`,
// never the raw thrown `Error` (docs/FRONTEND-CONVENTIONS.md §9). phase-8 task-07: `reset` lets
// the reader retry the segment instead of reloading the tab.
//
// p8 final (I-4): the segment this boundary replaces normally renders inside `PageContainer`
// (a `main` landmark) — without it, an error route had no landmark and the footer could sit
// mid-viewport instead of at the bottom.
export default function Error({ reset }: { reset: () => void }) {
  return (
    <PageContainer maxWidth="sm">
      <ErrorState message={PAGE_ERROR_MESSAGE} action={{ label: RETRY_LABEL, onClick: reset }} />
    </PageContainer>
  );
}
