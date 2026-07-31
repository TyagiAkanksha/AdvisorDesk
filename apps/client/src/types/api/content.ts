import type { components } from '../generated/schema';

// src/types/ is the only layer allowed to touch `components['schemas']`
// (docs/FRONTEND-CONVENTIONS.md §5) — everything else imports these named types.
//
// Two names per shape, deliberately (task-04 Interfaces): `*Dto` is the literal wire shape
// `src/lib/publicApi.ts`'s server-side fetch helpers return; the plain alias is what
// `content/` components consume via `@/types` (pinned by the authored component tests —
// `PublicContentSummary`/`PublicContentDetail`, no `Dto` suffix). Both resolve to the same
// type today; keeping them as separate aliases rather than one name used in two places leaves
// room for a view-model divergence later without a rename across every component.
export type PublicContentSummaryDto = components['schemas']['PublicContentSummary'];
export type PublicContentDetailDto = components['schemas']['PublicContentDetail'];
export type PublicContentSummary = PublicContentSummaryDto;
export type PublicContentDetail = PublicContentDetailDto;
