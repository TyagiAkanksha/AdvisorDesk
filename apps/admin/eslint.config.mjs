import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';
import eslintConfigPrettier from 'eslint-config-prettier';

// eslint-config-prettier must be last: it only turns off stylistic rules that
// would conflict with `prettier --check` (docs/FRONTEND-CONVENTIONS.md §8).
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // phase-8 task-02, docs/FRONTEND-CONVENTIONS.md §4: `src/components/common/` is the only place
  // that imports MUI, plus the theme file and the Providers client boundary. Was a comment-only
  // convention; now `pnpm lint` enforces it. `ignores` here is block-local (flat config), so
  // these paths are merely exempt from THIS rule, not from linting.
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/components/common/**', 'src/theme/theme.ts', 'src/app/providers.tsx'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@mui/*', '@mui/**'],
              message:
                'Import MUI only through @/components/common (docs/FRONTEND-CONVENTIONS.md §4).',
            },
          ],
        },
      ],
    },
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
