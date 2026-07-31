'use client';

import { ErrorState } from '@/components/common';

// task-04 fix round 1 (F4), docs/FRONTEND-CONVENTIONS.md §9. Next.js error-boundary convention:
// `app/error.tsx` MUST be a Client Component (it renders on the client to catch errors thrown
// by Server or Client Components below it in the tree — the "no RSC boundary" gap this whole
// fix round is about doesn't apply here, since the framework already forces the client
// boundary). Thin on purpose: friendly, static copy via the shared `ErrorState`, no retry
// button/logic, and never the raw thrown `Error` — docs/FRONTEND-CONVENTIONS.md §9 bans
// surfacing raw error bodies to the user.
export default function Error() {
  return <ErrorState message="Something went wrong loading this page. Please try again." />;
}
