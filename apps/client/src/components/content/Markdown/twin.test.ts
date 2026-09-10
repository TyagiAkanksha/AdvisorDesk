import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// phase-8 task-03: the renderer is duplicated into both apps on purpose (independent deploys).
// `nodePropStripping.test.tsx` only proves each copy strips `node`; this proves the copies ARE
// the same file.
const OWN_COPY = new URL('./Component.tsx', import.meta.url);
const TWIN_COPY = new URL(
  '../../../../../admin/src/components/content/MarkdownPreview/Component.tsx',
  import.meta.url,
);

describe('Markdown renderer twin guard', () => {
  it('is byte-identical to the other app’s copy', () => {
    expect(readFileSync(OWN_COPY, 'utf8')).toBe(readFileSync(TWIN_COPY, 'utf8'));
  });
});
