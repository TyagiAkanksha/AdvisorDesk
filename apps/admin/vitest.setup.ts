import { afterEach } from 'vitest';

import { baseApi } from '@/lib/api/baseApi';
import { store } from '@/lib/store';

// `@/lib/store` is a real singleton by design (task-04 Interfaces: one
// shared store, matching how the app actually runs) and component tests
// render the real, unmocked `Providers` around it — so every `it()` in a
// file shares ONE RTK Query cache. Left alone, an earlier test's in-flight
// or cached `getMe`/`logout` result leaks into the next test's fresh render
// (RTK Query dedupes an identical query against the existing cache entry
// instead of issuing a new `fetch`) — e.g. a query intentionally left
// "pending" by a never-resolving fetch mock in one test would still read as
// "pending" in the very next test. Reset the cache after every test so each
// one starts clean regardless of test order.
afterEach(async () => {
  // `globals: false` (vitest.config.ts) means @testing-library/react's own
  // auto-cleanup never self-wires (it only registers itself when it can
  // detect a global `afterEach`). Without this, DOM trees rendered by one
  // `it()` leak into the next `it()` in the same `describe` block, breaking
  // `screen` queries (which search the whole `document`, not a single
  // render's container) once more than one test in a file calls `render()`.
  //
  // Guarded on `document` so plain `environment: 'node'` test files (the
  // workspace default — jsdom is opt-in per file via the
  // `// @vitest-environment jsdom` pragma, docs/FRONTEND-CONVENTIONS.md §7)
  // never pull in `@testing-library/react` at all.
  //
  // Unmount BEFORE resetting the API state: resetting while a component is
  // still subscribed makes RTK Query's subscription effect notice its cache
  // entry vanished and re-`initiate()` a fresh request to "heal" it — an
  // unwanted extra dispatch racing the next test's own render.
  if (typeof document !== 'undefined') {
    const { cleanup } = await import('@testing-library/react');
    cleanup();
  }

  store.dispatch(baseApi.util.resetApiState());
});
