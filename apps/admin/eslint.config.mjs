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
