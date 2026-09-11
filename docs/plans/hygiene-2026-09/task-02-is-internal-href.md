---
id: hy-t02
phase: hygiene-2026-09
depends_on: []
status: done
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: sonnet
---

# Task 02 — One `isInternalHref` per app (twin-guarded), five call sites import it

## Goal

Close FINAL(C) X8 / t14 M2: "`isInternalHref` ×5 across both apps — extract a pure helper".
The identical three-line function is copied into `admin/common/{Button,IconButton,Link}` and
`client/common/{Button,Link}`. Move it to `src/lib/href.ts` in each app (a byte-identical
twin, guarded like `theme.ts`), unit-test it once per app, and make the five components import
it. Behaviour is unchanged: `/x` → internal (next/link), `//host/x`, `https://…`, `mailto:…`,
`#frag`, `x` → external (plain `<a>`).

## Context (read ONLY these)

- The five call sites (each has the function at the top of the file, under a long comment):
  `apps/admin/src/components/common/Button/Component.tsx`,
  `apps/admin/src/components/common/IconButton/Component.tsx`,
  `apps/admin/src/components/common/Link/Component.tsx`,
  `apps/client/src/components/common/Button/Component.tsx`,
  `apps/client/src/components/common/Link/Component.tsx`.
- Twin-guard idiom: `apps/admin/src/theme/theme.twin.test.ts` (and the client copy).
- `apps/admin/src/lib/format.ts` + `format.test.ts` — the pure-`lib/` module + test shape.
- `docs/FRONTEND-CONVENTIONS.md` §3 (logic in `lib/`), §7.

## Files

**Create (both apps — byte-identical)**
- `apps/admin/src/lib/href.ts`, `apps/client/src/lib/href.ts`
- `apps/admin/src/lib/href.test.ts`, `apps/client/src/lib/href.test.ts` (byte-identical too)
- `apps/admin/src/lib/href.twin.test.ts`, `apps/client/src/lib/href.twin.test.ts`

**Modify** — the five `Component.tsx` files above: delete the local function, import the
helper, shorten the comment.

## Interfaces

```ts
// src/lib/href.ts — identical in both apps
/**
 * Whether an `href` should be routed through `next/link` (client-side navigation).
 *
 * Internal = an absolute path on this app (`/content`, `/`), which is exactly what next/link
 * accepts. Everything else — an absolute URL (`https://…`), a protocol-relative URL
 * (`//host/x`, which also starts with `/`), `mailto:`, a bare fragment or a relative path —
 * renders as a plain `<a>` so the browser does a real navigation.
 *
 * Twin: apps/{admin,client}/src/lib/href.ts must stay byte-identical (`href.twin.test.ts`).
 */
export function isInternalHref(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//');
}
```

```ts
// src/lib/href.test.ts — identical in both apps
import { describe, expect, it } from 'vitest';

import { isInternalHref } from './href';

describe('isInternalHref', () => {
  it.each(['/', '/content', '/content/abc?x=1#y'])('routes %s through next/link', (href) => {
    expect(isInternalHref(href)).toBe(true);
  });

  it.each([
    '//cdn.example.com/x',
    'https://example.com/',
    'http://localhost:8000/api/v1/auth/login',
    'mailto:hi@example.com',
    '#top',
    'relative/path',
    '',
  ])('renders %s as a plain anchor', (href) => {
    expect(isInternalHref(href)).toBe(false);
  });
});
```

```ts
// src/lib/href.twin.test.ts — admin copy shown; the client copy swaps the relative paths
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// hygiene t02: `lib/href.ts` (and its test) are deliberately duplicated across the two apps —
// same rule as theme.ts (docs/FRONTEND-CONVENTIONS.md §2) — and this makes it a gate.
const OWN = new URL('./href.ts', import.meta.url);
const TWIN = new URL('../../../client/src/lib/href.ts', import.meta.url);
const OWN_TEST = new URL('./href.test.ts', import.meta.url);
const TWIN_TEST = new URL('../../../client/src/lib/href.test.ts', import.meta.url);

describe('href.ts twin guard', () => {
  it('is byte-identical to the other app’s href.ts', () => {
    expect(readFileSync(OWN, 'utf8')).toBe(readFileSync(TWIN, 'utf8'));
  });

  it('keeps href.test.ts byte-identical to the other app’s too', () => {
    expect(readFileSync(OWN_TEST, 'utf8')).toBe(readFileSync(TWIN_TEST, 'utf8'));
  });
});
```

In the client copy, `TWIN` is `'../../../admin/src/lib/href.ts'` and `TWIN_TEST` is
`'../../../admin/src/lib/href.test.ts'`.

## Steps

- [ ] **Step 1 (test-author, RED):** create the four test files exactly as above (two
  `href.test.ts`, two `href.twin.test.ts`). Do **not** create `href.ts`.
- [ ] **Step 2: run RED.** `cd apps/admin && npx vitest run src/lib/href` and the same in
  `apps/client` → `href.test.ts` fails to import `./href`; `href.twin.test.ts` fails with
  ENOENT. Paste the failure lines.
- [ ] **Step 3 (implementer, GREEN):** create both `href.ts` byte-identical to Interfaces. In
  each of the five components: delete the local `function isInternalHref`, add
  `import { isInternalHref } from '@/lib/href';` in the `@/` import group (alphabetical), and
  replace the paragraph of the header comment that explains the split with one line:
  `// The internal/external split is \`isInternalHref\` (src/lib/href.ts, hygiene t02).` —
  keep the rest of each header comment (the RSC-boundary rationale) intact.
- [ ] **Step 4: run GREEN + gates in both apps.** `npx vitest run` (full suite — the five
  components' existing tests are the behavioural pins; they must stay green untouched), then
  `type-check`, `lint`, prettier check.
- [ ] **Step 5: prove there is exactly one definition per app.**
  `grep -rn "function isInternalHref" apps/admin/src apps/client/src` → exactly two hits, both
  in `lib/href.ts`. Paste the output in the report.
- [ ] **Step 6: commit.** `git commit -m "refactor(common): extract isInternalHref into lib/href.ts twins (p8 final X8)"`

## Acceptance criteria

- `grep -rn "function isInternalHref"` → 2 hits, both `src/lib/href.ts`.
- `md5sum apps/admin/src/lib/href.ts apps/client/src/lib/href.ts` identical; same for
  `href.test.ts`.
- No `common/` component test changed. Both apps' full gate sets green.

## Report

Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-02-test-author.md`;
implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-02-implementer.md` (include the
grep output and md5sums).
