---
id: p8-t01
phase: phase-8-ui-polish
depends_on: []
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 01 — Theme tokens + fonts (both apps)

## Goal

Replace the palette-only `theme.ts` in both apps with the full design-token system from
DESIGN.md §A1 — type scale, palette additions, component defaults — fed by self-hosted fonts via
`next/font/google`. Byte-identical twins, now enforced by a test in each app. After this task,
every screen in both apps renders with a 36px h1 (not 96px), sentence-case buttons, an off-white
page background, and the chosen fonts — with **no screen code changed**.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2 (principles) and §3 A1.
- `docs/FRONTEND-CONVENTIONS.md` §2 (theme is the token system, twin rule), §7 (tests).
- `apps/client/src/theme/theme.ts` and `apps/admin/src/theme/theme.ts` (current 35-line twins).
- `apps/client/src/app/layout.tsx`, `apps/admin/src/app/layout.tsx` (where the font classes go).
- `apps/client/src/app/providers.tsx` (`ThemeProvider` + `CssBaseline` — unchanged; `CssBaseline`
  paints `palette.background.default` on `<body>` automatically).
- `apps/client/vitest.config.ts` (node env default; `// @vitest-environment jsdom` pragma per file).
- `infra/Dockerfile.web` lines 27–58 (builder stage runs `pnpm build` — must reach Google Fonts).
- `node_modules/@mui/material/styles/responsiveFontSizes.js` (variants ≤ 1rem are skipped; the
  largest breakpoint preserves the exact max size — the tests below rely on both facts).

## Files

**Modify**
- `apps/client/src/theme/theme.ts` — replaced wholesale (content below).
- `apps/admin/src/theme/theme.ts` — byte-identical to the client copy.
- `apps/client/src/app/layout.tsx` — add `next/font/google` (Source Serif 4 + Inter) → `<html className>`.
- `apps/admin/src/app/layout.tsx` — add `next/font/google` (Inter for both variables).

**Create**
- `apps/client/src/theme/theme.test.ts` — token values (node env).
- `apps/admin/src/theme/theme.test.ts` — same assertions (node env).
- `apps/client/src/theme/theme.twin.test.ts` — byte-identical guard.
- `apps/admin/src/theme/theme.twin.test.ts` — byte-identical guard (mirror path).
- `apps/client/src/app/layout.fonts.test.ts` — pins the two CSS-variable names in `layout.tsx`.
- `apps/admin/src/app/layout.fonts.test.ts` — same.

## Interfaces

**Consumes:** nothing new.

**Produces (later tasks rely on):**
- CSS variables `--font-heading`, `--font-body` on `<html>` in both apps.
- `theme.typography.{h1..h6,body1,body2,button}` per the Global Constraints scale;
  `theme.palette.background.default '#F6F7F9'`, `theme.palette.divider`.
- Component defaults: `MuiButton.disableElevation`, `MuiCard.variant='outlined'`,
  `MuiChip.size='small'`, `MuiLink.underline='hover'`, `MuiTextField.size='small'`.

**`theme.ts` — exact content (both apps, byte-identical):**

```ts
// AdvisorDesk shared design tokens (docs/FRONTEND-CONVENTIONS.md §2, DESIGN.md §A1).
//
// This file is INTENTIONALLY duplicated: apps/client/src/theme/theme.ts and
// apps/admin/src/theme/theme.ts must stay byte-identical (the two apps deploy independently,
// so each carries its own copy rather than importing a shared package). `theme.twin.test.ts`
// beside each copy fails the suite if they diverge — edit both, or neither.
import { createTheme, responsiveFontSizes } from '@mui/material/styles';

// Font families arrive as CSS variables set on <html> by each app's app/layout.tsx via
// next/font, so this file stays free of Next imports (importable from Server Components and
// node-env tests). Client: heading = Source Serif 4, body = Inter. Admin: both = Inter.
// The fallbacks are what renders if a variable is missing.
const HEADING_FONT = 'var(--font-heading), Georgia, serif';
const BODY_FONT = 'var(--font-body), system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

const baseTheme = createTheme({
  palette: {
    // Deep navy — trust/stability register for an advisory product.
    primary: { main: '#1E3A5F' },
    // Muted gold — calls to action ONLY (DESIGN.md §2); destructive actions use `color="error"`.
    secondary: { main: '#C08A28' },
    // Off-white page ground so white Paper/Card surfaces have visible edges.
    background: { default: '#F6F7F9', paper: '#FFFFFF' },
    text: { primary: '#172033' },
    divider: 'rgba(23, 32, 51, 0.12)',
  },
  typography: {
    fontFamily: BODY_FONT,
    // Desktop sizes; responsiveFontSizes below scales h1–h3 down on phones (factor 2).
    h1: { fontFamily: HEADING_FONT, fontSize: '2.25rem', fontWeight: 600, lineHeight: 1.2 },
    h2: { fontFamily: HEADING_FONT, fontSize: '1.75rem', fontWeight: 600, lineHeight: 1.25 },
    h3: { fontFamily: HEADING_FONT, fontSize: '1.375rem', fontWeight: 600, lineHeight: 1.3 },
    h4: { fontSize: '1.125rem', fontWeight: 600, lineHeight: 1.35 },
    h5: { fontSize: '1rem', fontWeight: 600, lineHeight: 1.4 },
    h6: { fontSize: '0.875rem', fontWeight: 600, lineHeight: 1.4 },
    body1: { fontSize: '1rem', lineHeight: 1.65 },
    body2: { fontSize: '0.875rem', lineHeight: 1.5 },
    // Sentence case everywhere (DESIGN.md §2) — Material's uppercase default reads as shouting.
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiCard: { defaultProps: { variant: 'outlined' } },
    MuiChip: { defaultProps: { size: 'small' } },
    MuiLink: { defaultProps: { underline: 'hover' } },
    MuiTextField: { defaultProps: { size: 'small' } },
  },
  // spacing is intentionally left at the MUI default (theme.spacing(n) = n * 8px).
});

// factor 2: h1 2.25rem → 1.625rem on phones, growing back to 2.25rem at the `lg` breakpoint.
// disableAlign: keep the line heights above instead of snapping them to a 4px grid.
export const theme = responsiveFontSizes(baseTheme, { factor: 2, disableAlign: true });
```

**`apps/client/src/app/layout.tsx` — exact content:**

```tsx
import type { Metadata } from 'next';
import { Inter, Source_Serif_4 } from 'next/font/google';
import type { ReactNode } from 'react';

import Providers from './providers';

// phase-8 task-01: next/font downloads these at build time and self-hosts them (no runtime
// request to Google, no CSP change). They reach theme.ts only as the two CSS variables below,
// set on <html> — theme.ts stays Next-free (DESIGN.md §A1). Client = editorial content site,
// so headings are serif; the admin twin of this file uses Inter for both variables.
const headingFont = Source_Serif_4({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-heading',
});
const bodyFont = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-body' });

export const metadata: Metadata = {
  title: 'AdvisorDesk',
  description: 'Ask questions about our published research and insights.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${headingFont.variable} ${bodyFont.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

**`apps/admin/src/app/layout.tsx`** — identical shape; both calls are `Inter(...)`:

```tsx
const headingFont = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-heading' });
const bodyFont = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-body' });
```

(keep the existing `metadata` object; `<html lang="en" className={...}>` as above).

## Steps (TDD)

- [ ] **RED — test-author.** Create the six test files. `theme.test.ts` (both apps, node env —
  no pragma needed):

```ts
import { describe, expect, it } from 'vitest';

import { theme } from './theme';

// phase-8 task-01, DESIGN.md §A1 — the token values every screen inherits. Pinned here so a
// drift in either twin fails loudly (theme.twin.test.ts pins that the twins match; this file
// pins what they say).
describe('theme tokens', () => {
  it('keeps the navy/gold brand palette and adds the page ground, text, and divider tokens', () => {
    expect(theme.palette.primary.main).toBe('#1E3A5F');
    expect(theme.palette.secondary.main).toBe('#C08A28');
    expect(theme.palette.background.default).toBe('#F6F7F9');
    expect(theme.palette.background.paper).toBe('#FFFFFF');
    expect(theme.palette.text.primary).toBe('#172033');
    expect(theme.palette.divider).toBe('rgba(23, 32, 51, 0.12)');
  });

  it('sets a 36px desktop h1 that scales down on phones (never MUI’s 96px default)', () => {
    expect(theme.typography.h1['@media (min-width:1200px)']).toEqual({ fontSize: '2.25rem' });
    expect(theme.typography.h1.fontSize).toBe('1.625rem');
    expect(theme.typography.h2['@media (min-width:1200px)']).toEqual({ fontSize: '1.75rem' });
    expect(theme.typography.h3['@media (min-width:1200px)']).toEqual({ fontSize: '1.375rem' });
  });

  it('uses the heading font variable for h1–h3 and the body font variable for h4–h6 and body', () => {
    expect(theme.typography.h1.fontFamily).toContain('var(--font-heading)');
    expect(theme.typography.h3.fontFamily).toContain('var(--font-heading)');
    expect(theme.typography.h4.fontFamily).toContain('var(--font-body)');
    expect(theme.typography.body1.fontFamily).toContain('var(--font-body)');
  });

  it('renders buttons in sentence case', () => {
    expect(theme.typography.button.textTransform).toBe('none');
  });

  it('sets flat, outlined, small, hover-underline component defaults', () => {
    expect(theme.components?.MuiButton?.defaultProps?.disableElevation).toBe(true);
    expect(theme.components?.MuiCard?.defaultProps?.variant).toBe('outlined');
    expect(theme.components?.MuiChip?.defaultProps?.size).toBe('small');
    expect(theme.components?.MuiLink?.defaultProps?.underline).toBe('hover');
    expect(theme.components?.MuiTextField?.defaultProps?.size).toBe('small');
  });
});
```

  `theme.twin.test.ts` (client copy; the admin copy swaps the two path strings):

```ts
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// phase-8 task-01: docs/FRONTEND-CONVENTIONS.md §2 says the two theme.ts files are deliberately
// duplicated and must keep identical values. Until now that was a comment; this makes it a gate.
const OWN_COPY = new URL('./theme.ts', import.meta.url);
const TWIN_COPY = new URL('../../../admin/src/theme/theme.ts', import.meta.url);

describe('theme.ts twin guard', () => {
  it('is byte-identical to the other app’s theme.ts', () => {
    expect(readFileSync(OWN_COPY, 'utf8')).toBe(readFileSync(TWIN_COPY, 'utf8'));
  });
});
```

  `layout.fonts.test.ts` (client copy; admin asserts `Inter(` twice instead of `Source_Serif_4(`):

```ts
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
    expect(LAYOUT).toMatch(/<html lang="en" className=\{`\$\{headingFont\.variable\} \$\{bodyFont\.variable\}`\}>/);
  });
});
```

- [ ] **Run RED:** `pnpm -C apps/client test -- theme layout.fonts && pnpm -C apps/admin test -- theme layout.fonts`
  Expected: FAIL — `theme.palette.background.default` is MUI's `#fff`, no `@media` key on h1,
  `layout.tsx` lacks `next/font/google`. Record the output in the test-author report.

- [ ] **GREEN — implementer:** write `theme.ts` exactly as above into both apps (copy the file,
  do not retype), then both `layout.tsx` files.

- [ ] **Run GREEN:** the same two test commands → PASS. Then `pnpm -C apps/client type-check &&
  pnpm -C apps/admin type-check`.

- [ ] **Full suites:** `pnpm -C apps/client test && pnpm -C apps/admin test` → all green. If any
  existing test asserted an MUI default (uppercase text, default sizes), fix the test's
  expectation to the new token and note it in the report — those pins were accidents.

- [ ] **Build proof (the DESIGN.md §A1 risk):**
  `API_URL=http://localhost:8000 pnpm -C apps/client build` and
  `NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm -C apps/admin build` → both succeed (fonts
  downloaded). Then the builder image:
  `docker build -f infra/Dockerfile.web --build-arg APP=client -t advisordesk-client:p8t01 .`
  → succeeds. If the Docker build fails on font download only, switch both layouts to
  `next/font/local` with the two families vendored under `src/fonts/` (same `variable` names)
  and update the `layout.fonts.test.ts` expectation from `'next/font/google'` to
  `'next/font/local'` — record which path was taken.

- [ ] **Screenshots:** `pnpm -C apps/client dev` + `pnpm -C apps/admin dev` (API on :8000 or the
  prod API URL in env); capture client `/` and `/content/<any-slug>`, admin `/content` at
  1440 and 390 px. Attach to the implementer report. (The doubled article title is still there —
  task 03 fixes it — but both copies must now be 36px.)

- [ ] **Gates:** `pnpm gates:client && pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/client/src/theme apps/admin/src/theme apps/client/src/app/layout.tsx apps/admin/src/app/layout.tsx apps/client/src/app/layout.fonts.test.ts apps/admin/src/app/layout.fonts.test.ts`
  `git commit -m "feat(web): theme type scale, palette tokens, next/font (p8 t01)"`

## Verify

```bash
pnpm -C apps/client test -- theme layout.fonts
pnpm -C apps/admin test -- theme layout.fonts
pnpm gates:client && pnpm gates:admin
API_URL=http://localhost:8000 pnpm -C apps/client build
```

## Acceptance

- Both `theme.ts` files are byte-identical and the twin test passes in both apps.
- Token tests pass; `pnpm build` passes for both apps; Docker builder stage passes (or the
  documented `next/font/local` fallback was taken and recorded).
- Screenshots show 36px h1, sentence-case buttons, off-white background, serif headings on the
  client and Inter on the admin.
- No file outside `theme.ts`, the two `layout.tsx`, and the new tests changed (screens untouched).
- Reviewer (Opus) checks the five dimensions with file:line evidence, and specifically that no
  `sx` overrides were added anywhere to "fix" a size the theme should own.
