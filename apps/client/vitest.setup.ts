import { afterEach } from 'vitest';

// task-04: registers RTL's `cleanup()` in `afterEach` for jsdom test files — mirrors
// apps/admin/vitest.setup.ts's RTL-cleanup half (apps/client has no RTK Query store to reset,
// so that half of admin's setup doesn't apply here).
//
// `globals: false` (vitest.config.ts) means @testing-library/react's own auto-cleanup never
// self-wires (it only registers itself when it can detect a global `afterEach`). Without this,
// DOM trees rendered by one `it()` leak into the next `it()` in the same file, breaking `screen`
// queries (which search the whole `document`, not a single render's container) once more than
// one test in a file calls `render()`.
//
// Guarded on `document` so plain `environment: 'node'` test files (the workspace default —
// jsdom is opt-in per file via the `// @vitest-environment jsdom` pragma,
// docs/FRONTEND-CONVENTIONS.md §7) never pull in `@testing-library/react` at all.
//
// The three task-04 authored test files (Markdown/ContentListScreen/ArticleScreen
// `Component.test.tsx`) each still register their own local `afterEach(cleanup)` too — written
// before this workspace-level fix existed, per the test-author's own report (they're pinned and
// out of scope to edit). Calling `cleanup()` twice per test is harmless; new client component
// test files going forward don't need to repeat it themselves.
afterEach(async () => {
  if (typeof document !== 'undefined') {
    const { cleanup } = await import('@testing-library/react');
    cleanup();
  }
});
