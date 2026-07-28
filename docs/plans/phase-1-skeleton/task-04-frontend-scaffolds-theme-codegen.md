---
id: task-04
phase: phase-1-skeleton
depends_on: [task-01]
status: planned
spec: advisordesk-prd.md §3.1, §9, §11 row 6
---

# task-04 — Scaffold both Next.js apps with MUI theme and codegen wiring

## Goal

`apps/admin` (port 3001) and `apps/client` (port 3000) exist as TS-strict Next.js App Router apps
wired for MUI SSR, each with the shared theme tokens, a seeded `components/common/` layer (Icon,
PageContainer), the full gate script set, and a working `pnpm codegen` from
`apps/api/openapi.json`. Every UI task in phases 2–5 builds inside these apps.

## Context (read ONLY these)

- `docs/FRONTEND-CONVENTIONS.md` — all sections; this task instantiates them.
- `advisordesk-prd.md` §3.1 (app locations), §11 row 6 (MUI decision, v1.4).
- `apps/api/openapi.json` (from task-03) — the codegen source.

## Files

- Create: root `package.json` + `pnpm-workspace.yaml` (`apps/*`)
- Create per app (`apps/admin`, `apps/client`): `package.json`, `tsconfig.json` (strict),
  `next.config.ts`, `eslint.config.mjs`, `.prettierrc.json`, `vitest.config.ts`,
  `src/app/layout.tsx` (AppRouterCacheProvider + ThemeProvider + CssBaseline),
  `src/app/page.tsx` (thin), `src/theme/theme.ts`,
  `src/components/common/Icon/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`,
  `src/components/common/PageContainer/{Component.tsx,index.ts}`,
  `src/types/index.ts`, `src/types/generated/schema.d.ts` (generated, committed)

## Interfaces

- **Consumes:** task-01 repo root; task-03 `apps/api/openapi.json` (final step only).
- **Produces (later tasks rely on — produce exactly):**
  - `@/theme/theme` — the `createTheme()` token file (palette, typography, spacing, shape,
    component defaults); same values in both apps, header comment naming the twin copy.
  - `@/components/common` barrel with `Icon` (`IconProps = { name: keyof typeof icons;
    label?: string; size?: 'small'|'medium'|'large'; color?: string }`; `label` → `role="img"` +
    `aria-label`, absent → `aria-hidden`) and `PageContainer`.
  - `@/types` barrel — the only module importing `./generated/schema` (empty re-export until
    phase-2 adds DTO aliases).
  - Scripts in both apps: `dev` (admin `-p 3001`), `build`, `lint`, `lint:fix`, `format`,
    `format:check`, `type-check`, `test`, `test:watch`,
    `codegen` = `openapi-typescript ../../apps/api/openapi.json -o src/types/generated/schema.d.ts`.

## Steps (TDD)

- [ ] **Step 1: Workspace + app scaffolds.** Root `pnpm-workspace.yaml`; `create-next-app` both
  apps (TS, App Router, no Tailwind); add `@mui/material @emotion/react @emotion/styled
  @mui/icons-material @mui/material-nextjs`; dev deps `vitest @vitejs/plugin-react
  @testing-library/react @testing-library/jest-dom jsdom openapi-typescript
  eslint-config-prettier prettier`.
- [ ] **Step 2: Failing Icon test first** (`Icon/Component.test.tsx`, jsdom pragma line 1,
  explicit vitest imports): with `label="Search"` → `getByRole('img', {name:'Search'})`; without
  label → svg has `aria-hidden="true"`.
- [ ] **Step 3:** `pnpm -C apps/admin test` → FAIL (component missing).
- [ ] **Step 4: Implement** `theme.ts`, `layout.tsx` (AppRouterCacheProvider → ThemeProvider →
  CssBaseline), `Icon`, `PageContainer`, thin `page.tsx` rendering PageContainer with the app
  name. Mirror into `apps/client` (ports/titles differ).
- [ ] **Step 5:** `pnpm -C apps/admin test` and `pnpm -C apps/client test` → PASS.
- [ ] **Step 6: Codegen** (after task-03): run `pnpm -C apps/admin codegen` + same for client;
  commit the generated files; add `src/types/generated/**` to eslint/prettier ignore.
- [ ] **Step 7: Gates → commit:**
  `feat(web): next.js scaffolds with MUI theme + codegen (phase-1 task-04)`

## Verify

```bash
pnpm -C apps/admin lint && pnpm -C apps/admin type-check && pnpm -C apps/admin test   # clean
pnpm -C apps/client lint && pnpm -C apps/client type-check && pnpm -C apps/client test # clean
pnpm -C apps/admin dev &   # http://localhost:3001 renders themed shell page
pnpm -C apps/client dev &  # http://localhost:3000 renders themed page
grep -rn "@mui/" apps/admin/src --include='*.tsx' -l | grep -v -E 'common/|theme/|layout'  # empty
```

## Acceptance

- Both apps build and pass all gates; strict TS; MUI SSR wired via `@mui/material-nextjs`.
- The `@mui/*` import boundary holds (only theme, layout/Providers, `common/`).
- `codegen` reproduces `schema.d.ts` byte-identically from the committed `openapi.json`.
- Icon a11y contract pinned by test in both apps.
