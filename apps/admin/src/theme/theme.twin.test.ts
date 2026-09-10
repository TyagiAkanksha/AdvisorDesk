import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// phase-8 task-01: docs/FRONTEND-CONVENTIONS.md §2 says the two theme.ts files are deliberately
// duplicated and must keep identical values. Until now that was a comment; this makes it a gate.
const OWN_COPY = new URL('./theme.ts', import.meta.url);
const TWIN_COPY = new URL('../../../client/src/theme/theme.ts', import.meta.url);

describe('theme.ts twin guard', () => {
  it('is byte-identical to the other app’s theme.ts', () => {
    expect(readFileSync(OWN_COPY, 'utf8')).toBe(readFileSync(TWIN_COPY, 'utf8'));
  });
});
