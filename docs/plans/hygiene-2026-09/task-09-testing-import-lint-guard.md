---
id: hy-t09
phase: hygiene-2026-09
depends_on: [hy-t04]
status: todo
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: sonnet
---

# Task 09 — ESLint guard: `@/testing/*` is importable only from test files (admin)

## Goal

Close the FINAL(C) RIDE item "testing-import lint guard". `apps/admin/src/testing/` holds
test seams (`nextNavigation.ts`, `matchMedia.ts`) that mock framework modules; nothing in
production code may import them, but today only convention says so. Add a `no-restricted-
imports` pattern for `@/testing`, `@/testing/*`, `@/testing/**` that applies to every
`src/**` file **except** `*.test.{ts,tsx}` files and `src/testing/**` itself, and pin it in the
existing `eslint.config.test.ts` next to the MUI-boundary pins.

**Flat-config gotcha that shapes the design:** rule options are *replaced*, not merged, by a
later matching block. The MUI-boundary block already sets `no-restricted-imports` for
`src/**` (exempting `common/**`, `theme.ts`, `providers.tsx`). A second block that sets the
same rule for an overlapping set of files would silently drop the MUI patterns for those
files. So the config must be composed so that **every file gets exactly one
`no-restricted-imports` configuration carrying every pattern that applies to it**.

Admin only — `apps/client` has no `src/testing/` (INDEX plan-time ruling).

## Context (read ONLY these)

- `apps/admin/eslint.config.mjs` — the MUI-boundary block and the `argsIgnorePattern` block.
- `apps/admin/eslint.config.test.ts` — the `lintText` + virtual `filePath` pin idiom (copy it).
- `apps/admin/src/testing/` — the seams; `grep -rn "@/testing" apps/admin/src -l` shows every
  importer is a `*.test.tsx` today (the tree is already clean — confirm and record).
- `docs/FRONTEND-CONVENTIONS.md` §4, §7, §8.

## Files

**Modify**
- `apps/admin/eslint.config.mjs`
- `apps/admin/eslint.config.test.ts`

## Interfaces

```js
// apps/admin/eslint.config.mjs — replace the single MUI-boundary block with this composition
// (keep the `argsIgnorePattern` block and everything else as is)

const MUI_EXEMPT = ['src/components/common/**', 'src/theme/theme.ts', 'src/app/providers.tsx'];
const TEST_FILES = ['src/**/*.test.{ts,tsx}', 'src/testing/**'];

// phase-8 task-02, docs/FRONTEND-CONVENTIONS.md §4: `src/components/common/` is the only place
// that imports MUI, plus the theme file and the Providers client boundary.
const MUI_PATTERN = {
  group: ['@mui/*', '@mui/**'],
  message: 'Import MUI only through @/components/common (docs/FRONTEND-CONVENTIONS.md §4).',
};
// hygiene t09: `src/testing/` holds test seams that mock framework modules — production code
// must never import them.
const TESTING_PATTERN = {
  group: ['@/testing', '@/testing/*', '@/testing/**'],
  message: 'Test seams (@/testing/*) may only be imported from *.test files (hygiene t09).',
};

// Flat config REPLACES a rule's options when a later block matches the same file, so each file
// must get exactly one `no-restricted-imports` block carrying every pattern that applies to it:
//   production code outside common/theme/providers → MUI + testing patterns
//   test files outside common                       → MUI pattern only
//   common/theme/providers (non-test)               → testing pattern only
//   test files inside common, and src/testing/**    → no restriction
const restrictImports = (...patterns) => ({
  'no-restricted-imports': ['error', { patterns }],
});

// …inside defineConfig([...]) in place of the old MUI block:
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: [...MUI_EXEMPT, ...TEST_FILES],
    rules: restrictImports(MUI_PATTERN, TESTING_PATTERN),
  },
  {
    files: ['src/**/*.test.{ts,tsx}'],
    ignores: ['src/components/common/**'],
    rules: restrictImports(MUI_PATTERN),
  },
  {
    files: MUI_EXEMPT,
    ignores: ['src/**/*.test.{ts,tsx}'],
    rules: restrictImports(TESTING_PATTERN),
  },
```

## Steps

- [ ] **Step 1 (test-author, RED): extend `eslint.config.test.ts`.** Add a second `lintText`
  source and a second describe block; keep the four MUI pins untouched:

  ```ts
  const TESTING_IMPORT =
    "import { navigation } from '@/testing/nextNavigation';\nexport const x = navigation;\n";

  async function ruleIdsForText(text: string, filePath: string): Promise<string[]> {
    const [result] = await eslint.lintText(text, { filePath });
    return (result?.messages ?? []).map((message) => message.ruleId ?? '');
  }

  describe('test-seam import boundary (hygiene t09)', () => {
    it('rejects an @/testing import in a screen component', async () => {
      expect(
        await ruleIdsForText(TESTING_IMPORT, 'src/components/content/Fake/Component.tsx'),
      ).toContain('no-restricted-imports');
    }, 20000);

    it('rejects an @/testing import in a common primitive, a hook and a lib module', async () => {
      expect(
        await ruleIdsForText(TESTING_IMPORT, 'src/components/common/Fake/Component.tsx'),
      ).toContain('no-restricted-imports');
      expect(
        await ruleIdsForText(TESTING_IMPORT, 'src/components/content/Fake/useFake.ts'),
      ).toContain('no-restricted-imports');
      expect(await ruleIdsForText(TESTING_IMPORT, 'src/lib/fake.ts')).toContain(
        'no-restricted-imports',
      );
    }, 20000);

    it('allows @/testing imports from test files anywhere and from src/testing itself', async () => {
      expect(
        await ruleIdsForText(TESTING_IMPORT, 'src/components/content/Fake/Component.test.tsx'),
      ).not.toContain('no-restricted-imports');
      expect(
        await ruleIdsForText(TESTING_IMPORT, 'src/components/common/Fake/Component.test.tsx'),
      ).not.toContain('no-restricted-imports');
      expect(await ruleIdsForText(TESTING_IMPORT, 'src/testing/other.test.tsx')).not.toContain(
        'no-restricted-imports',
      );
    }, 20000);

    // The composition must not drop the MUI boundary for any file class it re-configures.
    it('keeps the MUI boundary in place for test files outside common', async () => {
      expect(
        await ruleIdsForText(MUI_IMPORT, 'src/components/content/Fake/Component.test.tsx'),
      ).toContain('no-restricted-imports');
    }, 20000);
  });
  ```

- [ ] **Step 2: run RED.** `cd apps/admin && npx vitest run eslint.config` → the first two new
  tests fail (no rule fires); the "allows" test passes; the "keeps the MUI boundary" test —
  record whether it passes today (it should: the current MUI block matches test files). Paste
  the failure lines.
- [ ] **Step 3 (implementer, GREEN):** rewrite `eslint.config.mjs` per Interfaces. Keep the
  original explanatory comments (task-02 rationale, `ignores` being block-local) where they
  still apply.
- [ ] **Step 4: run GREEN + gates.** `npx vitest run eslint.config`, then `pnpm -C apps/admin
  lint` (zero errors, zero warnings on the real tree), `type-check`, `format:check`, and the
  full `npx vitest run`.
- [ ] **Step 5: real-tree probe (evidence, not committed).** Create
  `src/components/content/__probe__.tsx` containing `TESTING_IMPORT`'s two lines, run
  `pnpm -C apps/admin lint` → exactly one error naming `no-restricted-imports` and the t09
  message; delete the probe; `git status` clean apart from the two intended files. Paste the
  error line.
- [ ] **Step 6: commit.** `git commit -m "chore(admin): lint guard — @/testing seams only importable from test files (p8 final RIDE)"`

## Acceptance criteria

- All eight `eslint.config.test.ts` tests pass.
- `pnpm -C apps/admin lint` clean on the real tree; the probe produces exactly one error.
- `git diff --stat` shows only `eslint.config.mjs` and `eslint.config.test.ts`.

## Report

Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-09-test-author.md`;
implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-09-implementer.md` (include the
probe error line).
