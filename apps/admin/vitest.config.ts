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
    // task-04: registers RTL's `cleanup()` in `afterEach` for jsdom test
    // files — see vitest.setup.ts for why this can't rely on RTL's own
    // auto-cleanup under `globals: false`.
    setupFiles: ['./vitest.setup.ts'],
    // Final review (F3): under the default parallel file execution, three tests —
    // ContentEditorScreen/{resilientRefetch,tagOrderDirty,publishGuard}.test.tsx — intermittently
    // fail with `Test timed out in 5000ms` under full-suite CPU/scheduling load (first observed
    // p3-t04, ledgered across p3-t04's implementer + reviewer rounds; not a regression from any
    // one task, root cause not yet isolated). `pnpm -C apps/admin test` is the documented gate
    // (README/CLAUDE.md), so it needs to be reliable as invoked, not only under
    // `--no-file-parallelism` passed by hand — encoding that flag here, rather than chasing the
    // timeout's root cause, is the fix for THIS wave; root cause stays open (ledgered).
    fileParallelism: false,
  },
});
