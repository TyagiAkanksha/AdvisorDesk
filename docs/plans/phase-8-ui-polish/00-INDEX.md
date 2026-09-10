# Phase 8 — UI Polish — Implementation Plan (sub-phase A: shared foundation)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Every task runs as a **three-agent SDD task**
> (test-author → implementer → reviewer; reviewer ≠ implementer — `CLAUDE.md`). Reviewers are
> Sonnet unless marked ★ (Opus); the whole-branch final review is Opus.

**Spec:** [`docs/plans/phase-8-ui-polish/DESIGN.md`](DESIGN.md) — authoritative on any conflict
with this plan. Product spec: [`advisordesk-prd.md`](../../../advisordesk-prd.md) (§8 disclaimer,
§12 scope). Conventions: [`docs/FRONTEND-CONVENTIONS.md`](../../FRONTEND-CONVENTIONS.md) (both
apps), [`CONVENTIONS.md`](../../../CONVENTIONS.md) (only sub-phase C touches apps/api).

**Goal (sub-phase A):** replace MUI's leaked defaults with a real design-token foundation in both
Next.js apps — type scale + fonts, a complete twin Markdown renderer, the primitives every later
screen needs, and branded route files — and deploy it alone so the theme is validated on real
content before any layout work (sub-phases B/C get their own task files after A ships).

**Architecture:** `src/theme/theme.ts` (byte-identical twins, now test-guarded) becomes the
single source of typography/palette/component defaults; fonts are self-hosted by `next/font` and
reach the theme through two CSS variables. `src/components/common/` stays the only MUI importer
(now ESLint-enforced) and grows the wrappers sub-phases B/C consume. The Markdown renderer is
one source file duplicated into both apps (twin-guarded), parameterised by `variant` and
`headingOffset`, with a pure `stripLeadingHeading` helper fixing the doubled article title.

**Tech Stack:** Next.js 16.2 App Router, React 19.2, TypeScript strict, MUI 9.2 (`@mui/material`,
`@mui/icons-material`, `@mui/material-nextjs`), Emotion, `next/font/google`, react-markdown 10 +
remark-gfm 4, vitest 4 + RTL + user-event, ESLint 9 flat config. **No new runtime dependencies.**

## Global Constraints

Every task's requirements implicitly include this section. Exact values are copied from the spec.

- **Design principles (DESIGN.md §2)** bind every brief and review: conventional patterns;
  sentence case everywhere (`button.textTransform: 'none'`); no gradients/glass/emoji/hero copy;
  navy = primary, gold `secondary` = call-to-action only, `color="error"` = destructive; explicit
  loading/empty/error states; one source of truth for tokens/primitives/copy/dates; every
  visual change ships a **screenshot at 1440 and 390 px** in the task report.
- **Tokens (exact):** `primary.main '#1E3A5F'`, `secondary.main '#C08A28'`,
  `background.default '#F6F7F9'`, `background.paper '#FFFFFF'`, `text.primary '#172033'`,
  `divider 'rgba(23, 32, 51, 0.12)'`, `shape.borderRadius 8`; type scale h1 `2.25rem/600`,
  h2 `1.75rem/600`, h3 `1.375rem/600` (heading font), h4 `1.125rem/600`, h5 `1rem/600`,
  h6 `0.875rem/600` (body font), body1 `1rem` lh `1.65`, body2 `0.875rem` lh `1.5`; wrapped in
  `responsiveFontSizes(theme, { factor: 2, disableAlign: true })`.
- **Fonts:** CSS variables `--font-heading` and `--font-body` set on `<html>` by each app's
  `app/layout.tsx` via `next/font/google` (`display: 'swap'`, `subsets: ['latin']`). Client:
  heading `Source_Serif_4`, body `Inter`. Admin: heading `Inter`, body `Inter`. `theme.ts`
  references only the variables. Fallback stacks: heading `Georgia, serif`; body `system-ui,
  -apple-system, "Segoe UI", Roboto, sans-serif`.
- **Twins:** `apps/client/src/theme/theme.ts` ≡ `apps/admin/src/theme/theme.ts` and
  `apps/client/src/components/content/Markdown/Component.tsx` ≡
  `apps/admin/src/components/content/MarkdownPreview/Component.tsx` — byte-identical, each
  guarded by a node-env vitest test in **both** apps (`fs.readFileSync` both paths, `toBe`).
- **MUI import boundary:** `@mui/*` may be imported only from `src/components/common/**`,
  `src/theme/theme.ts`, `src/app/providers.tsx` — enforced by ESLint `no-restricted-imports`
  (task 02) in both apps. Everything else imports from `@/components/common`.
- **Component shape (FRONTEND-CONVENTIONS §3):** `<Name>/{Component.tsx, interface.ts, index.ts}`
  (+ `Component.test.tsx` for anything with behaviour); `Component.tsx` is `export default
  function Component(props: <Name>Props)`; `index.ts` re-exports under the real name; zero-prop
  components have no `interface.ts`; pass-through primitives (`Box`-style) type their props as
  `export type XProps = MuiXProps` and need no test of their own — the composite/screen that
  uses them is the test.
- **Markdown contract:** `MarkdownProps = { markdown: string; variant?: 'article' | 'chat';
  headingOffset?: 0 | 1 }` (prop name `markdown` is the existing frozen contract — kept). No
  `rehype-raw` (HTML stays escaped). Renderer maps receive an explicit prop allow-list (never
  `{...props}`) so react-markdown's `node` prop never reaches the DOM.
- **Copy:** placeholder/user-facing strings come from `src/lib/copy.ts` per app (client has one;
  admin's is created in task 07 with the 404 copy and grows in sub-phase C).
- **Tests (FRONTEND-CONVENTIONS §7):** vitest, `globals: false`, jsdom via the
  `// @vitest-environment jsdom` first-line pragma, RTL + `@testing-library/user-event`, queries
  by role/label, mock only `fetch`. Node-env tests for pure helpers and file-twin guards. Tests
  import through the barrel (`from '.'`).
- **Gates before every commit:** `pnpm gates:client` and/or `pnpm gates:admin` (lint, type-check,
  format:check, test) for each app touched; `type-check` after every significant change.
  Task 01 additionally proves `pnpm build` for both apps and the Docker builder stage succeed
  with `next/font`.
- **SDD discipline:** the test-author writes the RED tests named in each task and proves they
  fail; the implementer may add tests but never weakens/edits authored tests without controller
  approval. Reports go in `.superpowers/sdd/progress.md` (ledger) + per-task report files.
- **Commits:** Conventional, scoped, path-scoped `git add`, suffix `(p8 t<NN>)`, e.g.
  `feat(web): theme type scale + next/font (p8 t01)`. Scope `web` = both apps, `client`/`admin`
  = one app.
- **Branch:** `feat/ui-polish-a`, one PR for sub-phase A. Merge, push, deploy are **owner gates**.

## Tasks

| # | Task | Depends on | Review | Deliverable |
|---|---|---|---|---|
| 01 | [Theme tokens + fonts (both apps)](task-01-theme-tokens-fonts.md) ★ | — | Opus | `theme.ts` twins with type scale/palette/defaults, `next/font` in both layouts, twin guard + token tests, build/Docker proof |
| 02 | [MUI import boundary lint rule (both apps)](task-02-mui-import-boundary-lint.md) | — | Sonnet | `no-restricted-imports` block in both `eslint.config.mjs`, ESLint-API test |
| 03 | [Markdown renderer twin + `stripLeadingHeading`](task-03-markdown-renderer-twin.md) ★ | 01 | Opus | full tag mapping, `variant`/`headingOffset`, `lib/markdown.ts` in both apps, `Divider` primitive, call sites wired, twin guard |
| 04 | [Admin base primitives + extensions](task-04-admin-base-primitives.md) | 01 | Sonnet | Table family, Skeleton, Stack, Tooltip, Alert, Paper; TextField/ConfirmDialog/Button/NavList/ErrorState/Drawer extensions |
| 05 | [Admin composite primitives](task-05-admin-composite-primitives.md) | 04 | Sonnet | `PageHeader`, `StatCard`, `SnackbarProvider` + `useSnackbar` mounted in `Providers` |
| 06 | [Client primitives + extensions](task-06-client-primitives.md) | 01 | Sonnet | AppBar, Toolbar, Stack, Skeleton, Grid, Tooltip, IconButton, Alert, Paper, Container; TextField/Button/ErrorState/EmptyState extensions |
| 07 | [Route files + metadata (both apps)](task-07-route-files.md) | 04, 06 | Sonnet | `not-found.tsx`, `loading.tsx`, `icon.tsx`, `metadata.title` templates, `error.tsx` retry, admin `lib/copy.ts` |

**Execution order:** 01 → 02 → 03 → 04 → 05 → 06 → 07 (02 can run in parallel with 01; 04/06 in
parallel after 01). Sub-phase A ships when 07 is green, the whole-branch Opus review passes, and
the owner has done the live visual checkpoint (DESIGN.md §6).

### Ordering rationale

- **01 first** because every later task's screenshots are meaningless against the old scale, and
  the `next/font` build risk (DESIGN.md §A1) must be retired before anything depends on it.
- **02 early** so the boundary rule is in force while 03–07 add code, not retrofitted.
- **03 before 04–06** because it is the biggest visible fix (doubled 96px article title) and it
  only needs `Divider`, which it adds itself.
- **04 → 05** because `PageHeader`/`StatCard`/`SnackbarProvider` compose `Stack`/`Paper`/`Alert`.
- **07 last** because `not-found`/`loading` consume `Skeleton`, `Button href`, `ErrorState action`.

### Visual checkpoint (⚠️ owner, after 07)

Chrome at 1440×900 and 390×844 against a local `pnpm dev` of both apps (or the deployed
sub-phase A): no 96px headings; article title appears once; buttons in sentence case; off-white
page background with white cards/paper; `/does-not-exist` shows the branded 404 in both apps;
browser tab shows the navy "A" icon; `loading.tsx` skeletons visible on a throttled reload.
