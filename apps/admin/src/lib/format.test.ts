import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, formatOptionalDateTime } from './format';

describe('lib/format', () => {
  it('formatDate renders a medium en-US date', () => {
    expect(formatDate('2026-03-15T12:00:00Z')).toBe('Mar 15, 2026');
  });

  it('formatDateTime appends a short time', () => {
    // `\s` (not a literal space) — ICU ≥ 72 emits U+202F before AM/PM.
    expect(formatDateTime('2026-03-15T12:00:00Z')).toMatch(/^Mar 15, 2026, \d{1,2}:\d{2}\s[AP]M$/);
  });

  it('formatOptionalDateTime renders the dash placeholder for null', () => {
    expect(formatOptionalDateTime(null)).toBe('—');
    expect(formatOptionalDateTime('2026-03-15T12:00:00Z')).toMatch(/^Mar 15, 2026, /);
  });
});
