# Phase 8 — UI Polish — Implementation Plan (sub-phases A, B and C — all merged)

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

## Tasks — sub-phase A (shared foundation) — MERGED (PR #28, main e3302e2)

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
sub-phase A): no 96px headings; no heading smaller than its surrounding body text; article title
appears once; buttons in sentence case; off-white page background with white cards/paper;
`/does-not-exist` shows the branded 404 in both apps; browser tab shows the navy "A" icon;
`loading.tsx` skeletons visible on a throttled reload.

---

## Sub-phase B — client screens (apps/client) — MERGED (PR #29, main a81f4da)

**Goal:** the public site becomes a finished content site on the A foundation: a header/footer
shell, a filterable article grid, an article reading layout with related articles, and a chat
surface with a welcome state, titled sources, and a proper composer (DESIGN.md §4).

**Additional constraints for B** (on top of Global Constraints above):
- **Client islands only where the browser is needed:** `SiteNav` (`usePathname`),
  `ArticleCard`/`TagFilter`/`TagChips` (next/link's client-side routing needs the browser —
  `common/Link` is a `'use client'` module, so its export is a client reference and may be passed
  as `component=` from a Server Component; a bare function imported from a server module is what
  cannot cross the boundary, task-04 F1), `ChatScreen` and its leaves. Everything else stays a
  Server Component.
- **Screenshot method:** the sandbox cannot resize Chrome windows — serve a local page with
  `<iframe width="1440" height="900">` / `<iframe width="390" height="844">` pointing at the dev
  server and capture that (headless Chrome `--screenshot` works; `--window-size` is clamped to
  ~500px, so never use it for the 390 view).
- **No real chat requests from screenshots** — render bubble states through a throwaway route
  that is deleted before commit. `API_URL=https://api.advisordesk.tyagiakanksha.com` for the dev
  server is fine (public read-only GETs).
- **Copy:** every new user-facing string in `src/lib/copy.ts` (constants named in each brief).
- **Existing pins:** a task that changes a pinned behaviour rewrites the pin in its RED step
  and says so; a task never silently deletes a pin.

| # | Task | Depends on | Review | Deliverable |
|---|---|---|---|---|
| 08 | [Client shell: SiteHeader, SiteNav, SiteFooter](task-08-client-shell.md) | 07 | Sonnet | header/nav/footer in the root layout, `DISCLAIMER` in copy, nav out of `page.tsx` |
| 09 | [Home: header block, URL tag filter, article grid](task-09-client-home.md) | 08 | Sonnet | `filterByTag`/`uniqueTags`, `ArticleCard`, `TagFilter`, `ContentListScreen` rewrite, `?tag=` RSC page, two empty states |
| 10 | [Article: reading layout, related, CTA](task-10-client-article.md) | 09 | Sonnet | `relatedArticles`, `cache()`d fetch, `RelatedArticles`, `md` column, disclaimer alert |
| 11 | [`useChatStream` stop/reset/retry](task-11-chat-stream-controls.md) | 08 | Sonnet | three hook controls with stream-fixture tests |
| 12 | [Chat screen: welcome, bubbles, sources, composer](task-12-chat-screen.md) ★ | 11 | Opus | `useChatComposer`, `ChatWelcome`, `ThinkingIndicator`, `ChatComposer`, Sources list, refusal/error alerts, `CircularProgress` primitive |

**Execution order:** 08 → 09 → 10 → 11 → 12 (11 only needs 08 and could run before 10; keep
one writer in the tree at a time). Sub-phase B ships when 12 is green, the whole-branch Opus
review passes, and the owner has done the visual checkpoint.

### Visual checkpoint (⚠️ owner, after 12)

Client only, 1440 and 390: header with wordmark and the active link highlighted on every
route; footer disclaimer; home = h1 + description + one gold CTA, tag chips filter via the URL,
3/1-column grid with dates; article = `md` column, back link, tag links, single h1, info-alert
disclaimer, related cards, chat CTA; chat = welcome with four suggested questions, navy/outlined
bubbles ≤ 640px, Thinking… row, titled Sources list, warning refusal, composer with Send→Stop
swap, New conversation, helper line; no horizontal scroll at 390 anywhere.

---

## Sub-phase C — admin screens + API redirect (apps/admin, apps/api) — MERGED (PR #31, main 9a1e74b; live)

**Goal:** the admin console becomes a finished, responsive internal app on the A foundation: a
sign-in card that explains a failed login (backed by a 5-line API change), a responsive shell
with a highlighted current route, a real dashboard, a URL-driven content table, an editor with
a live preview and proper feedback, a focused connected-apps page, and an agent panel with
collapsible tool cards (DESIGN.md §5). Sub-phases A and B are merged and live (PRs #28/#29,
prod `a81f4da`).

**Additional constraints for C** (on top of Global Constraints above):
- **API change (task 13 only):** `CONVENTIONS.md` §8 — `apps/api/openapi.json` and BOTH apps'
  `src/types/generated/schema.d.ts` are regenerated in the same commit; `pnpm gates:api` runs
  before that commit. No other backend change in this sub-phase.
- **MUI boundary holds for hooks too:** `useMediaQuery` is wrapped once as
  `common/useBreakpointDown` (task 14); no screen imports `@mui/*` or `@mui/material/useMediaQuery`.
- **Test seams (task 14):** URL-driven screens use the stateful `@/testing/nextNavigation`
  mock (`vi.mock('next/navigation', () => import('@/testing/nextNavigation'))` +
  `navigation.reset(href)`), responsive branches use `stubMatchMedia(true)`; every other test
  keeps mocking only `fetch`. Existing static `useRouter` mocks in files that never read the
  URL stay as they are.
- **jsdom/MUI 9 facts (from A/B):** MUI 9 emits SPLIT classes (`MuiButton-contained` +
  `MuiButton-colorError`, `MuiIconButton-colorInherit`, `MuiChip-outlined`); `userEvent.tab()`
  fires a real Tab keydown; a closed `keepMounted` Drawer is `visibility: hidden` (excluded from
  role queries; `{ hidden: true }` gives it an EMPTY name); jsdom resolves `vw` → px; jsdom has no
  `matchMedia` (MUI falls back to `false` = desktop); a disabled MUI button has `pointer-events:
  none` (hover its `<span>` wrapper); `Intl` emits U+202F before AM/PM (`\s` in regexes).
- **Skeleton matches screen:** every screen's loading state is a `role="status"
  aria-label={LOADING_LABEL}` skeleton shaped like the screen it replaces (no spinners in screens).
- **Feedback:** every mutation reports through `useSnackbar()` (exact copy per brief); the last
  `AppSnackbar` call site migrates in task 19 and the primitive is deleted there.
- **Pins:** a task that changes a pinned behaviour rewrites the pin in its RED step and says so
  (each brief lists which); pins in untouched files must stay green with zero edits.
- **Copy:** every new user-facing string in `apps/admin/src/lib/copy.ts` (constants named in
  each brief). Sentence case; no emoji; gold never appears on a destructive control.
- **Screenshots:** iframe technique (1440 + 390) from the real screens against the local API
  with the seed data, signed in as the allowlisted admin; throwaway routes/stubs used only to
  reach a state (never a real agent request) and deleted before commit.
- **Deferred minors from B carried in for the whole-branch review (not per-task scope):**
  article disclaimer `role="alert"` → `role="note"`; no h1 once client chat starts; `←` glyph
  outside copy; one `nav` landmark per Sources list; related-fetch failure taking down the
  article + `cache()` uniformity; `searchParams` string[] typing; `ArticleCard` `titleAs`; unused
  icon prune across BOTH apps; `retry`/`reset` guard tests; nav slack < 330px; TagChips/
  ArticleCard chip duplication; `theme.test` twin guard; TextField `onKeyDown` cast; `maxRows`
  pin. Owner calls parked from the B checkpoint: the article disclaimer appears three times
  (seed body italic + info Alert + footer); the teal info Alert is the only non-navy/gold hue.

| # | Task | Depends on | Review | Deliverable |
|---|---|---|---|---|
| 13 | [API: callback failures redirect to `/signin?error=`](task-13-api-signin-redirect.md) ★ | — | Opus | `state`/`forbidden` 303s, six pins rewritten + one new, openapi + both codegens |
| 14 | [Admin C foundation: test seams, `useBreakpointDown`, `lib/format`, primitive extensions](task-14-admin-c-foundation.md) | — | Sonnet | `testing/{nextNavigation,matchMedia}`, `useBreakpointDown`, `format.ts`, Grid/Chip/CircularProgress, EmptyState/IconButton/TextField/Autocomplete extensions, 5 icons, `APP_NAME` |
| 15 | [Admin shell: responsive nav, active route, single main](task-15-admin-shell.md) | 14 | Sonnet | `useAppShell`, `isActivePath`, `AccountMenu` leaf, temporary drawer below md, wordmark, agent drawer widths, `PageContainer` without `main` |
| 16 | [Sign-in card with `?error=`](task-16-admin-signin.md) | 13, 15 | Sonnet | centred card, `signInErrorMessage`, page reads `searchParams` |
| 17 | [Dashboard: linked stat cards, tag table, recent content](task-17-admin-dashboard.md) | 15 | Sonnet | `useDashboard`, `TagTable`, `RecentContent`, `DashboardSkeleton`, first `AppSnackbar` site retired |
| 18 | [Content list: URL-synced filters, MUI table, skeletons, empty states](task-18-admin-content-list.md) ★ | 15 | Opus | `contentListParams`, URL-as-state `useContentList` (debounce + clamp), `ContentFilters`, MUI `ContentTable`, `ContentTableSkeleton`, `Suspense` page |
| 19 | [Editor hook: validation, dirty guard, global snackbar, tag options](task-19-editor-hook.md) | 18 | Sonnet | `titleError`/`isDirty`/`tagOptions`/header fields, `beforeunload`, `AppSnackbar` deleted |
| 20 | [Editor screen: header meta, split live preview, action row, red delete](task-20-editor-screen.md) ★ | 19 | Opus | `EditorMeta`/`EditorForm`/`EditorPreview`/`EditorSkeleton`, `lib/markdown.ts` (admin), Publish tooltips, phone Preview toggle |
| 21 | [Connected apps: header, focused table, destructive revoke, refresh feedback](task-21-connected-apps.md) | 18 | Sonnet | Client/Connected/Last used/Revoke table, `ConnectedAppsSkeleton`, "Access revoked", F-5 closed |
| 22 | [`useAgentStream` stop/reset, text offsets, `turnSegments`](task-22-agent-stream-controls.md) | 14 | Sonnet | `stop`/`reset`, `ToolEvent.textOffset`, `lib/agentTurnSegments` |
| 23 | [Agent panel: header, suggestions, markdown turns, collapsible tool cards, Stop](task-23-agent-panel.md) ★ | 22, 15 | Opus | `useAgentComposer`, `AgentComposer`, `WorkingIndicator`, collapsible `ToolCallCard`, interleaved `AgentMessage`, `onClose` |

**Execution order:** 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22 → 23 (13 is independent
and could run last; keeping it first lets 16 verify end-to-end against the local API). One
writer in the tree at a time. Sub-phase C ships when 23 is green, the whole-branch Opus review
passes (with the carried-in B minors triaged), and the owner has done the visual checkpoint;
then one PR, merge, and one deploy of all three images.

### Visual checkpoint (⚠️ owner, after 23)

Admin at 1440 and 390: sign-in card centred, `?error=forbidden` message; shell with wordmark,
icons, highlighted current route, menu button + temporary drawer on the phone, no horizontal
scroll; dashboard cards link into filtered lists and the tag table links by tag; content list
filters rewrite the URL and the back button restores them, table scrolls sideways on the phone,
Edit/Delete tooltips, red Delete; editor two-column with sticky preview that matches the public
article, Preview toggle on the phone, "Title is required", Publish tooltip, snackbars on
save/publish/archive/delete, unsaved-changes prompt on reload; connected apps table with short
ids and red Revoke; agent panel with suggestions, a collapsed → expanded tool card, Working…,
Stop, Clear, full-width on the phone. API: a wrong-account sign-in lands on the card with the
allowlist message instead of raw JSON.
