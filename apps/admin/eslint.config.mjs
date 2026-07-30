import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';
import eslintConfigPrettier from 'eslint-config-prettier';

// eslint-config-prettier must be last: it only turns off stylistic rules that
// would conflict with `prettier --check` (docs/FRONTEND-CONVENTIONS.md §8).
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
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
