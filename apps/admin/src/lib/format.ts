import { PLACEHOLDER_DASH } from './copy';

// phase-8 task-14 (DESIGN.md §C4): one date formatter per app. Local time zone on purpose —
// admin screens only ever render in the browser (RequireSession gates them behind a query that
// is pending during SSR), so there is no server/client mismatch to pin UTC for.
const DATE = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' });
const DATE_TIME = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });

export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

export function formatOptionalDateTime(iso: string | null): string {
  return iso === null ? PLACEHOLDER_DASH : formatDateTime(iso);
}
