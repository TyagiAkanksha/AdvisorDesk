import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// phase-8 task-01: docs/FRONTEND-CONVENTIONS.md §2 says the two theme.ts files are deliberately
// duplicated and must keep identical values. Until now that was a comment; this makes it a gate.
const OWN_COPY = new URL('./theme.ts', import.meta.url);
const TWIN_COPY = new URL('../../../client/src/theme/theme.ts', import.meta.url);
const TWIN_TEST_COPY = '../../../client/src/theme/theme.test.ts';

describe('theme.ts twin guard', () => {
  it('is byte-identical to the other app’s theme.ts', () => {
    expect(readFileSync(OWN_COPY, 'utf8')).toBe(readFileSync(TWIN_COPY, 'utf8'));
  });

  // p8 t24: `theme.test.ts` (the pins ABOVE) must itself stay byte-identical across apps, same
  // rationale as `theme.ts` — until now that was only enforced for the values, not the test file.
  it('keeps theme.test.ts byte-identical to the other app’s too', () => {
    expect(readFileSync(new URL('./theme.test.ts', import.meta.url), 'utf8')).toBe(
      readFileSync(new URL(TWIN_TEST_COPY, import.meta.url), 'utf8'),
    );
  });
});
