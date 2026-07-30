import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import tsconfigPaths from 'vite-tsconfig-paths';

// environment: 'node' is the workspace default (FRONTEND-CONVENTIONS.md §7); component
// tests opt into jsdom per-file via a `// @vitest-environment jsdom` pragma on line 1.
// globals: false — describe/it/expect/vi are imported explicitly in every test file.
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  test: {
    environment: 'node',
    globals: false,
    exclude: ['**/node_modules/**', '**/.next/**'],
  },
});
