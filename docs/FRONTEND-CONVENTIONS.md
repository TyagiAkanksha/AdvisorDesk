# AdvisorDesk — Frontend Conventions (apps/admin + apps/client)

**Scope:** both Next.js apps. Python rules live in [`../CONVENTIONS.md`](../CONVENTIONS.md). The PRD
([`../advisordesk-prd.md`](../advisordesk-prd.md)) wins on any conflict.

Distilled from the reference project's `cms_ui/CONVENTIONS.md` and adapted: AdvisorDesk uses
**Material UI** instead of the reference's private design system (PRD §11 row 6, updated v1.4), and
has **two** apps with different data-fetching defaults (§6).

---

## 1. Workspace & scripts

- pnpm workspace at the repo root; apps at `apps/admin` and `apps/client`.
- Pinned dev ports: **client 3000, admin 3001, API 8000** — matching `CORS_ORIGINS` in
  `.env.example`.
- Both apps expose the same scripts, and **every script is a gate**: a red result is the failing
  test telling you what to fix. `dev` · `build` · `lint` · `lint:fix` · `format` · `format:check` ·
  `type-check` · `test` · `test:watch` · `codegen`.
- TypeScript `strict: true` in both apps (PRD §9). `any` is banned; document any exception inline
  with the reason.

## 2. UI stack: Material UI (no Tailwind)

- `@mui/material` + `@mui/icons-material` + `@mui/material-nextjs` (App Router integration:
  `AppRouterCacheProvider` in the root layout), Emotion styling.
- `src/theme/theme.ts` (`createTheme()`) **is the design-token system**: palette, typography,
  spacing, shape, and component default-props/variants live there. Both apps share the same token
  values; the file is duplicated per app deliberately (apps deploy independently) with a header
  comment naming the other copy.
- A style used twice becomes a theme variant or a `styled()` component — never a copy-pasted `sx`
  blob. Ad-hoc `sx` is fine for one-off layout spacing.
- No Tailwind, no CSS modules, no global CSS beyond what MUI requires.

## 3. Component architecture

- **Folder-per-component:** `<Name>/{Component.tsx, interface.ts, index.ts[, Component.test.tsx]}`.
  `Component.tsx` is always `export default function Component(props: <Name>Props)`; `index.ts`
  re-exports under the real name (`export { default as Name } from './Component'`) plus the Props
  type. Zero-prop components have no `interface.ts`.
- **Pages are thin:** every `app/**/page.tsx` is import + render, ≤ ~20 lines. Screens live in
  `src/components/<domain>/` (`content`, `chat`, `shell`, `dashboard`, `agent`, ...). No screen
  code under `app/`.
- **View-model hooks are flat and colocated:** one `useX.ts` file next to the screen that uses it,
  with its Args/Result interfaces declared in-file. Reusable hooks get folder-per-hook under
  `src/lib/hooks/`.
- No inline Props interfaces in `Component.tsx` — they live in `interface.ts`.
- No classes anywhere in `src/` (`grep -rn "^\s*class " src` returns zero matches).

## 4. Primitives layer — wrap MUI, don't scatter it

- `src/components/common/` is the only place (besides `theme.ts` and the root `Providers`) that
  imports `@mui/*`. Call sites import from `@/components/common` — so an upstream swap or major
  version bump is a one-layer change.
- `common/Icon/` wraps `@mui/icons-material` behind a stable contract:
  `<Icon name="Search" label="Search" size="small|medium" color=... />` — `label` present →
  `role="img"` + `aria-label`; absent → `aria-hidden="true"`.
- Grow `common/` on demand (Button, StatusChip, ConfirmDialog, EmptyState, ErrorState,
  PageContainer, ...); wrap, don't hand-roll what MUI already provides.

## 5. Types — one codegen boundary

- `pnpm codegen` runs `openapi-typescript ../../apps/api/openapi.json -o
  src/types/generated/schema.d.ts`. The output is **committed and never hand-edited**; lint,
  format, and coverage all ignore `src/types/generated/**`.
- `src/types/` is the **only** layer that touches `components['schemas'][...]`:
  `export type ContentDto = components['schemas']['ContentResponse']`. Everything else imports the
  named types from `@/types`. Verification: `grep -rn "components\['schemas'\]" src/` hits only
  `src/types/`.
- Status enums are `as const` objects + `keyof typeof` unions — never TS `enum`, never bare
  `string`.

## 6. Data fetching — different defaults per app

- **Admin (`apps/admin`)** — RTK Query throughout: one `src/lib/api/baseApi.ts`
  (`fetchBaseQuery`, `credentials: 'include'` for the HttpOnly session cookie, base URL from env),
  per-domain `injectEndpoints` files (`authApi`, `contentApi`, `tagsApi`, `statsApi`), tag
  invalidation (`['Content','Tags','Stats','Me']`). Redux store holds server cache + UI state
  only; the session is never persisted client-side — it is rehydrated from `GET /auth/me`.
- **Client (`apps/client`)** — content pages are **React Server Components** fetching the public
  API server-side (`src/lib/publicApi.ts`) — SEO/TTFB matter here; RTK Query is not used in this
  app at all. The chat screen is a `'use client'` island.
- **Streams (both apps):** SSE endpoints are consumed by hand-rolled hooks (`useChatStream`,
  `useAgentStream`) using `fetch` + `ReadableStream` parsing of the PRD §5.3/§5.4 typed events —
  `EventSource` cannot POST. `session_id` lives in `localStorage` and is resent in the body
  (PRD §5.3; no cookies for client sessions).

## 7. Testing

- vitest + @testing-library/react + jest-dom. `environment: 'node'` is the default; component
  tests declare `// @vitest-environment jsdom` as the literal first line.
- `globals: false` — `describe`/`it`/`expect`/`vi` are imported explicitly.
- Tests are colocated (`Component.test.tsx` beside `Component.tsx`) and import through the barrel
  (`from '.'`), not `./Component`.
- Query by role/label first; test names state the rule being locked in, not the mechanics.
- Streaming hooks are tested against mocked `fetch`/`ReadableStream` fixtures.

## 8. Lint & format

- ESLint flat config: `eslint-config-next` (+ TS) with `eslint-config-prettier` **last**;
  `src/types/generated/**`, `.next/**`, `coverage/**` globally ignored.
- Prettier with every key explicit: `semi: true`, `singleQuote: true`, `trailingComma: 'all'`,
  `printWidth: 100`, `tabWidth: 2`, `arrowParens: 'always'`, `endOfLine: 'lf'`.

## 9. Accessibility & UX defaults

- Every interactive element has an accessible name; icon-only buttons get `aria-label`.
- Loading, empty, and error states are explicit components (`common/EmptyState`,
  `common/ErrorState`) — never a silent blank region.
- API errors surface the PRD §9 envelope's `message` in a friendly snackbar/notice; raw error
  bodies are never rendered.
- Placeholder copy ("—", "not available") comes from one typed module per app, not inline string
  literals.
