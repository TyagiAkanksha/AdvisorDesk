import type { components } from '../generated/schema';

// src/types/ is the only layer allowed to touch `components['schemas']`
// (docs/FRONTEND-CONVENTIONS.md §5) — everything else imports `WeakQueriesDto`/`WeakQueryGroupDto`.
export type WeakQueriesDto = components['schemas']['WeakQueriesResponse'];
export type WeakQueryGroupDto = components['schemas']['WeakQueryGroupOut'];

// Mirrors app/services/chat.py WEAK_QUERY_KINDS (precedence order). `kind` is a plain string on
// the wire; unknown values render with the raw string and the `default` colour.
export const WEAK_QUERY_KIND_LABELS: Record<string, string> = {
  negative_feedback: 'Thumbs down',
  refused: 'Refused',
  near_miss: 'Near miss',
  low_confidence: 'Low confidence',
};
export const WEAK_QUERY_KIND_COLORS: Record<string, 'error' | 'default' | 'warning' | 'info'> = {
  negative_feedback: 'error',
  refused: 'default',
  near_miss: 'warning',
  low_confidence: 'info',
};
