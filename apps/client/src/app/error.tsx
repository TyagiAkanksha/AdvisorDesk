'use client';

import { ErrorState } from '@/components/common';
import { PAGE_ERROR_MESSAGE, RETRY_LABEL } from '@/lib/copy';

// Next.js error-boundary convention: MUST be a Client Component. Friendly copy via `ErrorState`,
// never the raw thrown `Error` (docs/FRONTEND-CONVENTIONS.md §9). phase-8 task-07: `reset` lets
// the reader retry the segment instead of reloading the tab.
export default function Error({ reset }: { reset: () => void }) {
  return (
    <ErrorState message={PAGE_ERROR_MESSAGE} action={{ label: RETRY_LABEL, onClick: reset }} />
  );
}
