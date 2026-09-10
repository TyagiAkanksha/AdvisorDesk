import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// phase-8 task-01: layout.tsx can't be imported under vitest (next/font is a Next compiler
// transform), so this pins the seam between layout and theme as text — the two CSS variable
// names theme.ts reads must be the ones layout.tsx declares.
const LAYOUT = readFileSync(new URL('./layout.tsx', import.meta.url), 'utf8');

describe('root layout fonts', () => {
  it('declares --font-heading and --font-body via next/font/google and applies them to <html>', () => {
    expect(LAYOUT).toContain("from 'next/font/google'");
    expect(LAYOUT).toContain("variable: '--font-heading'");
    expect(LAYOUT).toContain("variable: '--font-body'");
    expect(LAYOUT).toContain('Source_Serif_4(');
    expect(LAYOUT).toMatch(
      /<html lang="en" className=\{`\$\{headingFont\.variable\} \$\{bodyFont\.variable\}`\}>/,
    );
  });
});
