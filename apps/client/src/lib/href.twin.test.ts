import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// hygiene t02: `lib/href.ts` (and its test) are deliberately duplicated across the two apps —
// same rule as theme.ts (docs/FRONTEND-CONVENTIONS.md §2) — and this makes it a gate.
const OWN = new URL('./href.ts', import.meta.url);
const TWIN = new URL('../../../admin/src/lib/href.ts', import.meta.url);
const OWN_TEST = new URL('./href.test.ts', import.meta.url);
const TWIN_TEST = new URL('../../../admin/src/lib/href.test.ts', import.meta.url);

describe('href.ts twin guard', () => {
  it('is byte-identical to the other app’s href.ts', () => {
    expect(readFileSync(OWN, 'utf8')).toBe(readFileSync(TWIN, 'utf8'));
  });

  it('keeps href.test.ts byte-identical to the other app’s too', () => {
    expect(readFileSync(OWN_TEST, 'utf8')).toBe(readFileSync(TWIN_TEST, 'utf8'));
  });
});
