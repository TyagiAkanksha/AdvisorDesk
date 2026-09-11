import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';
import eslintConfigPrettier from 'eslint-config-prettier';

// phase-8 task-02, docs/FRONTEND-CONVENTIONS.md §4: `src/components/common/` is the only place
// that imports MUI, plus the theme file and the Providers client boundary. Was a comment-only
// convention; now `pnpm lint` enforces it.
const MUI_EXEMPT = ['src/components/common/**', 'src/theme/theme.ts', 'src/app/providers.tsx'];
// Test files, the app-level seams, and any colocated `testing/` folder (test-only support code
// such as task 07's `ContentEditorScreen/testing/renderEditor.tsx`).
const TEST_FILES = ['src/**/*.test.{ts,tsx}', 'src/testing/**', 'src/**/testing/**'];

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
//   common/theme/providers (non-test)                → testing pattern only
//   test files inside common, src/testing/**, **/testing/** → no restriction
const restrictImports = (...patterns) => ({
  'no-restricted-imports': ['error', { patterns }],
});

// eslint-config-prettier must be last: it only turns off stylistic rules that
// would conflict with `prettier --check` (docs/FRONTEND-CONVENTIONS.md §8).
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // `ignores` here is block-local (flat config), so these paths are merely exempt from THIS
  // rule, not from linting.
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
  // phase-8 task-14 fix round 1: `eslint-config-next/typescript` sets
  // `@typescript-eslint/no-unused-vars` to `'warn'` with no `argsIgnorePattern`, so a trailing
  // intentionally-unused param only escapes it when a LATER param in the same list is used
  // (the rule's default `args: 'after-used'`) — that's why `_event` leading params already
  // scattered across `common/` (e.g. `Autocomplete/Component.tsx`'s `onChange={(_event,
  // newValue) => ...}`) never warned, but `src/testing/nextNavigation.ts`'s `_options` (the
  // LAST param in `replace`/`push`'s `vi.fn((href, _options?) => ...)`) does. This is a
  // project-wide convention (leading AND trailing `_`-prefixed params both mean "intentionally
  // unused"), not a `src/testing/`-only concern, so it's its own block — `files:
  // ['src/**/*.{ts,tsx}']` with no `ignores` — rather than folded into the MUI-boundary block
  // above (which excludes `src/components/common/**`, `theme.ts`, `providers.tsx` — this rule
  // must still apply there).
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    },
  },
  eslintConfigPrettier,
  globalIgnores([
    // Default ignores of eslint-config-next:
    '.next/**',
    'out/**',
    'build/**',
    'next-env.d.ts',
    // AdvisorDesk additions (FRONTEND-CONVENTIONS.md §8):
    'coverage/**',
    'src/types/generated/**',
  ]),
]);

export default eslintConfig;
