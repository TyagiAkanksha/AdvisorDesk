---
id: p8-t02
phase: phase-8-ui-polish
depends_on: []
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 02 — MUI import boundary as an ESLint rule (both apps)

## Goal

Turn FRONTEND-CONVENTIONS §4 ("`src/components/common/` is the only place that imports `@mui/*`")
from a convention into a gate: an ESLint `no-restricted-imports` block in both apps that fails
`pnpm lint` for any `@mui/*` import outside `src/components/common/**`, `src/theme/theme.ts`, and
`src/app/providers.tsx`. Today there are zero violations, so this lands green and protects
tasks 03–07 and sub-phases B/C. (DESIGN.md §A3 described a grep script; an ESLint rule is the
conventional tool, lives in the existing `lint` gate, and gives editors inline feedback.)

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §A3 "Lint gate".
- `docs/FRONTEND-CONVENTIONS.md` §4, §8.
- `apps/client/eslint.config.mjs`, `apps/admin/eslint.config.mjs` (flat config, prettier last).
- `apps/client/next.config.test.ts` (precedent: a node-env test at the app root that imports a
  config file).

## Files

**Modify**
- `apps/client/eslint.config.mjs` — add the block below before `eslintConfigPrettier`.
- `apps/admin/eslint.config.mjs` — same block.

**Create**
- `apps/client/eslint.config.test.ts`
- `apps/admin/eslint.config.test.ts`

## Interfaces

**Produces:** the lint gate. Later tasks that add primitives put them under
`src/components/common/**`; anything else importing `@mui/*` fails `pnpm lint`.

**Config block — exact (both apps), inserted as the third element, before `eslintConfigPrettier`:**

```js
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
```

## Steps (TDD)

- [ ] **RED — test-author.** `apps/client/eslint.config.test.ts` (node env; the admin copy is
  identical):

```ts
import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

// phase-8 task-02: pins the MUI import boundary (docs/FRONTEND-CONVENTIONS.md §4) as a lint
// gate. `lintText` with a virtual `filePath` resolves the flat config exactly as `eslint .`
// would for a real file at that path — no file needs to exist on disk.
const APP_ROOT = new URL('.', import.meta.url).pathname;
const eslint = new ESLint({ cwd: APP_ROOT });
const MUI_IMPORT = "import MuiButton from '@mui/material/Button';\nexport const x = MuiButton;\n";

async function ruleIdsFor(filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(MUI_IMPORT, { filePath });
  return (result?.messages ?? []).map((message) => message.ruleId ?? '');
}

describe('MUI import boundary (FRONTEND-CONVENTIONS §4)', () => {
  it('rejects an @mui import in a screen component', async () => {
    expect(await ruleIdsFor('src/components/content/Fake/Component.tsx')).toContain(
      'no-restricted-imports',
    );
  }, 20000);

  it('rejects an @mui import in a lib module', async () => {
    expect(await ruleIdsFor('src/lib/fake.ts')).toContain('no-restricted-imports');
  }, 20000);

  it('allows @mui imports inside src/components/common', async () => {
    expect(await ruleIdsFor('src/components/common/Fake/Component.tsx')).not.toContain(
      'no-restricted-imports',
    );
  }, 20000);

  it('allows @mui imports in theme.ts and providers.tsx', async () => {
    expect(await ruleIdsFor('src/theme/theme.ts')).not.toContain('no-restricted-imports');
    expect(await ruleIdsFor('src/app/providers.tsx')).not.toContain('no-restricted-imports');
  }, 20000);
});
```

- [ ] **Run RED:** `pnpm -C apps/client test -- eslint.config && pnpm -C apps/admin test -- eslint.config`
  Expected: the two "rejects" tests FAIL (no `no-restricted-imports` message yet); the "allows"
  tests pass already.

- [ ] **GREEN — implementer:** insert the config block into both `eslint.config.mjs` files.

- [ ] **Run GREEN:** same commands → PASS. Then `pnpm -C apps/client lint && pnpm -C apps/admin lint`
  → clean (confirms zero existing violations).

- [ ] **Negative proof for the report:** temporarily add
  `import Box from '@mui/material/Box';` to `apps/client/src/components/content/ArticleScreen/Component.tsx`,
  run `pnpm -C apps/client lint`, paste the error line into the report, then revert the file
  (`git checkout -- apps/client/src/components/content/ArticleScreen/Component.tsx`).

- [ ] **Gates:** `pnpm gates:client && pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/client/eslint.config.mjs apps/admin/eslint.config.mjs apps/client/eslint.config.test.ts apps/admin/eslint.config.test.ts`
  `git commit -m "chore(web): enforce the MUI import boundary with no-restricted-imports (p8 t02)"`

## Verify

```bash
pnpm -C apps/client test -- eslint.config
pnpm -C apps/admin test -- eslint.config
pnpm gates:client && pnpm gates:admin
```

## Acceptance

- Both test files pass; both `pnpm lint` runs are clean; the negative proof is in the report.
- The block sits before `eslintConfigPrettier` (prettier stays last, §8).
- No other lint rule changed.
