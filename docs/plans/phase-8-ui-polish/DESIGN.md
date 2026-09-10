# Phase 8 — UI Polish (apps/client + apps/admin) — Design Spec

**Status:** approved by owner 2026-09-09 (brainstorm, five sections approved one by one;
plan approved via Plan Mode). Implementation plan: `docs/plans/phase-8-ui-polish/00-INDEX.md`
+ task files (written per sub-phase).
**Goal:** make both Next.js apps look and behave like a standard, practical product — a public
content site with a grounded chat assistant, and an internal admin console — good enough to show
in a portfolio, on desktop and on phones. No new backend features; one 5-line API change (§C0).

**Owner decisions (brainstorm, 2026-09-09):** portfolio showcase for *both* apps · responsive on
phones, both apps · refined navy/gold + real type scale, **light mode only** · foundation-led in
three sub-phases (A shared foundation → B client → C admin), each its own PR + deploy ·
"standard, practical app — not an AI-generated look" · include the API redirect so the sign-in
page can explain a 403.

Governing docs: `docs/FRONTEND-CONVENTIONS.md` (§2 tokens, §3 folder-per-component, §4
primitives-only-import-MUI, §7 TDD, §9 a11y); `advisordesk-prd.md` (§5.3/§5.4 SSE contracts,
§7.5 citations/refusal copy, §8 disclaimer). PRD §12 "mobile apps" means native apps; responsive
web is in scope here by owner decision.

---

## 1. Why (audit summary, 2026-09-09)

Read-only audit of every screen (code + prod screenshots at 1440×900). The owner's verdict —
"components haven't been arranged properly" — traces to five foundations, not to individual
screens:

1. **`theme.ts` is a palette + radius only.** MUI's 2014 defaults leak through: `h1` renders at
   96px; the article page shows its title **twice** at 96px (the screen's `h1` plus the `# Title`
   that every `body_md` starts with); `h2` at 60px; buttons in ALL CAPS.
2. **No shell on the client** (no header, brand, nav, or footer; the only navigation is a text
   link on `/`). **Non-responsive shell on the admin** (empty AppBar, no active-nav state, zero
   breakpoints, permanent 240px drawer collides with content on phones, nested `<main>`).
3. **Loading = full-page spinner; success = silence.** No admin mutation confirms it worked.
   Delete is gold (`color="secondary"`), i.e. styled like the brand accent.
4. **Markdown renderer maps only headings/paragraphs/links.** Lists, code, tables, blockquotes
   fall through to browser defaults. Chat bubbles reuse the article renderer, so a `#` in an LLM
   answer renders at 96px inside a bubble.
5. **No `not-found.tsx` / `loading.tsx`; no client favicon.** 404s are Next's black default page.

Per-screen findings are folded into §4–§6 below as requirements.

## 2. Design principles (bind every task brief and every review)

- **Conventional over clever.** AppBar + drawer admin, plain data tables, forms with a normal
  action row, cards in a grid, a content site with a header and footer. If a pattern would look
  at home in a Material/Ant/Bootstrap admin template, it's the right one.
- **Sentence case everywhere.** Buttons, nav, headings, table headers. `textTransform: 'none'`.
- **No decoration.** No gradients, glassmorphism, emoji, illustrations, hero marketing sections,
  animated backgrounds, or "AI-generated" filler copy. Information density over prose.
- **Colour has meaning.** Navy = brand/primary actions; gold = call-to-action only (one per
  screen at most); `color="error"` = destructive; status colours only in `StatusChip`.
- **Explicit states.** Every data region has loading (skeleton), empty, and error states from
  `common/`; every mutation gets a success snackbar; disabled buttons explain why (tooltip).
- **One source of truth.** Tokens in `theme.ts` (byte-identical twins, test-guarded); primitives
  in `common/` are the only MUI importers; copy in `lib/copy.ts` per app; dates through one
  `lib/` formatter per app.
- **Evidence, not vibes.** Every task that changes what a screen looks like attaches a rendered
  screenshot (desktop 1440 + phone 390) to its report. A green test is not a visual check.

## 3. Sub-phase A — shared foundation (both apps, one PR, deployed alone)

### A1 Design tokens — `apps/{client,admin}/src/theme/theme.ts`

Byte-identical twins (existing rule, now test-enforced). The file stays Next-free; fonts arrive
through CSS variables set by each app's `app/layout.tsx` (`next/font/google`, build-time
self-hosted — no runtime request to Google, no CSP change).

```ts
// theme.ts (both apps) — shape, not full code
export const theme = responsiveFontSizes(
  createTheme({
    palette: {
      primary: { main: '#1E3A5F' },
      secondary: { main: '#C08A28' },
      background: { default: '#F6F7F9', paper: '#FFFFFF' },
      text: { primary: '#172033' },
      divider: 'rgba(23, 32, 51, 0.12)',
    },
    typography: {
      fontFamily: 'var(--font-body), system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      h1: { fontFamily: 'var(--font-heading), Georgia, serif', fontSize: '2.25rem', fontWeight: 600, lineHeight: 1.2 },
      h2: { fontFamily: 'var(--font-heading), Georgia, serif', fontSize: '1.75rem', fontWeight: 600, lineHeight: 1.25 },
      h3: { fontFamily: 'var(--font-heading), Georgia, serif', fontSize: '1.375rem', fontWeight: 600, lineHeight: 1.3 },
      h4: { fontSize: '1.125rem', fontWeight: 600 },
      h5: { fontSize: '1rem', fontWeight: 600 },
      h6: { fontSize: '0.875rem', fontWeight: 600 },
      body1: { fontSize: '1rem', lineHeight: 1.65 },
      body2: { fontSize: '0.875rem', lineHeight: 1.5 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    shape: { borderRadius: 8 },
    components: {
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiCard: { defaultProps: { variant: 'outlined' } },
      MuiPaper: { defaultProps: { elevation: 0 } },
      MuiChip: { defaultProps: { size: 'small' } },
      MuiLink: { defaultProps: { underline: 'hover' } },
      MuiTextField: { defaultProps: { size: 'small' } },
    },
  }),
);
```

Fonts per app (`app/layout.tsx`): **client** heading = Source Serif 4, body = Inter;
**admin** heading = Inter, body = Inter (an admin tool is sans-serif throughout). Each font is
declared with `variable: '--font-heading' | '--font-body'` and the class names go on `<html>`.
`display: 'swap'`. **Build-time risk:** `next/font/google` downloads the font files during
`next build` (CI and the `infra/Dockerfile.web` builder stage). If either environment cannot
reach `fonts.googleapis.com`, switch to `next/font/local` with the same two families vendored
under `src/fonts/` — same CSS variables, no other change. The A1 task verifies the Docker build
before the PR.

Tests: `src/theme/theme.twin.test.ts` (node env) in each app reads both files via
`fs.readFileSync` (path relative to the workspace root) and asserts equality. Existing tests that
assert MUI default sizes/uppercase text are updated by the implementer (they were pinning
accidents, not rules).

### A2 Markdown renderer (twin) — `client/src/components/content/Markdown` + `admin/src/components/content/MarkdownPreview`

Same `Component.tsx` source in both places, twin-guarded like the theme (a test asserts the two
`Component.tsx` files are byte-identical; each app keeps its own `interface.ts`/`index.ts`).
(Plan-time correction: the admin twin lives under `content/`, not `common/` — it imports from
`@/components/common`, so it cannot live inside it.)

```ts
export interface MarkdownProps {
  markdown: string;                 // markdown source — the existing frozen prop name, kept
  variant?: 'article' | 'chat';     // default 'article'
  headingOffset?: 0 | 1;            // 1 → '#' renders as h2 (screen owns the h1); default 0
}
```

Mapping (react-markdown `components`): h1–h6 → `Typography` (offset applied, chat variant caps
at h4-size), p → `Typography body1|body2`, a → `Link` (external href → `target="_blank"
rel="noopener noreferrer"`), ul/ol/li → themed lists (`pl: 3`, `mb: 1`), blockquote → left
border + secondary text, `code` inline → monospace with subtle background, `pre` → block,
monospace, `overflowX: 'auto'`, table → a semantic `<table>` styled through `Box` (borders,
padding, header tint; wrapped in an `overflowX: auto` box — keeps the twin's dependencies to
primitives both apps already share), hr → `Divider`, img → `max-width: 100%`. No `rehype-raw`
(HTML stays escaped — unchanged security posture).

`lib/markdown.ts` (client now; admin in C5 when its preview gains a title header — tested, pure):
`stripLeadingHeading(body: string, title: string): string` — removes a first line `# <title>`
(case/whitespace-insensitive match) plus following blank lines; returns `body` unchanged
otherwise. Used by client `ArticleScreen` (A) and the admin editor preview (C5).

### A3 Primitives (`src/components/common/`)

All new primitives follow `<Name>/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
and are exported from `common/index.ts`. Wrap MUI; don't restyle it beyond the theme.

| App | New | Extend |
|---|---|---|
| admin | `Table`, `TableContainer`, `TableHead`, `TableBody`, `TableRow`, `TableCell` (thin wrappers, `TableCell` accepts `align`, `component`, `scope`); `Skeleton`; `Stack`; `Divider`; `Tooltip`; `Alert`; `Paper`; `PageHeader`; `StatCard`; `SnackbarProvider` + `useSnackbar` | `TextField` (+`error`, `helperText`, `multiline`, `minRows`, `maxRows`, `onBlur`); `ConfirmDialog` (+`destructive?: boolean` → confirm button `color="error"`); `Button` (+`href`, `startIcon`, `size`, `color: 'error'`); `NavList` items (+`icon?: IconName`, `selected?: boolean`); `ErrorState` (+`action?: {label, onClick}`); `Drawer` (+`variant: 'permanent' \| 'temporary'`, `open`, `onClose`) |
| client | `AppBar`, `Toolbar`, `Stack`, `Divider`, `Skeleton`, `Grid`, `Tooltip`, `IconButton` (label required, like admin), `Alert`, `Paper` | `TextField` (+`multiline`, `minRows`, `maxRows`, `onKeyDown`); `Button` (+`href`, `startIcon`, `color`, `size`, `fullWidth`); `ErrorState` (+`action`); `EmptyState` (+`icon?: IconName`, `action?: {label, href}`); `PageContainer` (+`maxWidth: 'sm' \| 'md' \| 'lg'`, default `lg` — instead of a separate `Container`); `Chip` already passes MUI's generic props through (`<Chip<'a'> component="a" href clickable>`), no change needed |

```ts
// admin PageHeader
export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;      // right-aligned; wraps under title on xs
  meta?: ReactNode;         // small secondary line under the title (editor uses it)
}
// admin StatCard
export interface StatCardProps { label: string; value: number | string; href?: string; }
// admin snackbar
export interface SnackbarApi { success(message: string): void; error(message: string): void; }
export function useSnackbar(): SnackbarApi; // throws outside SnackbarProvider
```

`SnackbarProvider` is mounted once in admin `app/providers.tsx`; `AppSnackbar` is removed after
its last call site migrates (sub-phase C).

Lint gate (both apps, inside the existing `pnpm lint`): an ESLint `no-restricted-imports` block
in `eslint.config.mjs` fails on any `@mui/*` import outside `src/components/common/**`,
`src/theme/theme.ts`, and `src/app/providers.tsx` (`next/font` and `next/og` in
`layout.tsx`/`icon.tsx` are not MUI imports). Pinned by an ESLint-API test per app.

### A4 Route files (both apps)

- `app/not-found.tsx`: heading "Page not found", one line, `Button href` back to `/` ("Back to
  articles" / "Back to dashboard"). Rendered inside the app's shell (admin: `AppShell` for
  signed-in users; client: the B1 header/footer once they exist — in sub-phase A it is a plain
  centred block).
- `app/loading.tsx` at root + per data route (`content/[slug]`, admin `(app)/content`,
  `(app)/content/[id]`): skeletons shaped like the screen they replace.
- `app/icon.tsx` (both apps — both `favicon.ico` files turned out to be the untouched
  create-next-app default, so both are deleted): Next `ImageResponse`, 32×32 navy rounded
  square with a white serif "A".
- `metadata.title` per page: client `"<Article title> · AdvisorDesk"`, `"Ask a question ·
  AdvisorDesk"`; admin `"Content · AdvisorDesk Admin"` etc. (`title.template` in layout).
- Client `error.tsx` passes Next's `reset` into `ErrorState action={{label:'Try again', onClick: reset}}`.

Deploy A on its own. Visible change: fonts, sizes, buttons in sentence case, off-white
background, branded 404, single article title. It validates the theme on real content before any
layout work.

## 4. Sub-phase B — client (`apps/client`)

### B1 Shell — `src/components/shell/{SiteHeader,SiteFooter}`, mounted in `app/layout.tsx`

- Header: white `AppBar position="static" color="inherit"` with a bottom border, no elevation.
  `Container maxWidth="lg"` inside. Left: wordmark "AdvisorDesk" (`Typography h5`, heading
  font, `Link` to `/`). Right: `Articles` → `/`, `Ask a question` → `/chat`; the active link is
  `fontWeight 600` + primary colour (`usePathname` in a tiny `'use client'` island
  `SiteNav`). Two links fit at 390px; no hamburger.
- Footer: `Container`, top border, `Typography body2 color="text.secondary"` with the PRD §8
  disclaimer copy from `lib/copy.ts` (`DISCLAIMER` moves here from `ArticleScreen`).
- `page.tsx` loses its inline `<nav>`; the pinned "empty list has no link" test is rewritten
  against `SiteHeader`.

### B2 Home `/` — `ContentListScreen`

- Header block: `Typography h1` "Articles", one-line description (`lib/copy.ts`
  `HOME_DESCRIPTION`), and one gold `Button variant="contained" color="secondary"
  href="/chat"` "Ask a question".
- Tag filter row: `Chip`s as links (`/?tag=<tag>`), "All" first; the selected tag is
  `color="primary"`. Tags are derived from the list (unique, sorted). Filtering is server-side in
  the RSC from `searchParams.tag` via `lib/filterByTag.ts` (pure, tested). Unknown tag → the
  "no match" empty state with a "Show all" link.
- Grid: `Grid container spacing={2}`, item `xs=12 sm=6 md=4`. Card: title (`Typography h5
  component="h2"` link), `formatPublishedDate(published_at)` in `body2 text.secondary`, tag
  chips (links to the filter). Cards are equal height (`height: '100%'`).
- `loading.tsx`: 6 skeleton cards. Empty states: no content at all → existing copy; no match →
  "No articles tagged '<tag>'" + Show all.

### B3 Article `/content/[slug]` — `ArticleScreen`

- `Container maxWidth="md"`. `Link` "← All articles". `Typography h1` title. Meta line:
  date · tag chips (links to `/?tag=`). `Divider`.
- Body: `<Markdown variant="article" headingOffset={1}>{stripLeadingHeading(body_md, title)}</Markdown>`.
- Disclaimer: `Alert severity="info" variant="outlined"` (same copy as footer).
- Related: `Typography h3` "Related articles" + up to 3 cards from `lib/related.ts`
  (`relatedArticles(all, current, max=3)`: same-tag first, most recent, excluding current;
  tested). Section omitted when empty.
- CTA: `Button variant="outlined" href="/chat"` "Ask a question about this topic".
- `getContentBySlug` wrapped in React `cache()` in `lib/publicApi.ts` so `generateMetadata` and
  the page share one fetch. Missing slug → branded `not-found.tsx`.

### B4 Chat `/chat` — `ChatScreen`

- `Container maxWidth="md"`, flex column, `minHeight: calc(100vh - header - footer)`; message
  list scrolls; composer pinned at the bottom.
- Empty state: `Typography h1` "Ask a question", description, four suggested questions as
  `Button variant="outlined"` in a wrap row (copy: `SUGGESTED_QUESTIONS` in `lib/copy.ts`).
  Clicking sends immediately.
- Messages: user = `Paper` navy background, white text, right-aligned; assistant = `Paper
  variant="outlined"`, left-aligned; both `maxWidth: 'min(100%, 640px)'`. Assistant text through
  `<Markdown variant="chat">`. Before the first token: a row with a 16px `CircularProgress` and
  "Thinking…" (`aria-live="polite"`).
- Sources: under an assistant message with citations, `Typography overline` "Sources" and a
  list of `Link`s `[1] <title>` → `/content/<slug>`. Replaces the tooltip-only chips.
- Refusal: `Alert severity="warning" variant="outlined"` in place of a bubble (PRD §7.5 copy).
- Composer: `TextField multiline maxRows={6}` placeholder "Ask about retirement, insurance,
  taxes or college savings"; **Enter sends, Shift+Enter inserts a newline**; send
  `IconButton label="Send"` (disabled when empty); while streaming the send button becomes
  `Stop` (`IconButton label="Stop"`); `Button variant="text"` "New conversation" clears messages
  and the `localStorage` session; helper line `Typography caption` from `lib/copy.ts`
  ("Educational answers grounded in the published articles — not financial advice.").
- `useChatStream` gains `stop(): void` (one `AbortController` per request; aborting finalises
  the partial assistant message) and `reset(): void`. Tested with stream fixtures.
- Error: `Alert severity="error"` with the envelope `message` + `Retry` (re-sends the last
  user message).

## 5. Sub-phase C — admin (`apps/admin`) + one API change

### C0 API — `apps/api/app/routes/auth_routes.py` (callback)

The two failure branches that today raise `ForbiddenError` (state mismatch, non-allowlisted
email) instead return `RedirectResponse(f"{settings.admin_app_url}/signin?error=<reason>",
status_code=303)` with `reason ∈ {"state", "forbidden"}`. WARNING logs unchanged; the email
never appears in the URL. The docstring is updated → `apps/api/openapi.json` regenerated and
both apps' `pnpm codegen` re-run in the same commit (standing gate). Tests: one per branch
asserting 303 + `Location`, plus the existing success test.

### C1 Shell — `components/shell/AppShell` + `useAppShell.ts`

- AppBar: left = menu `IconButton label="Open navigation"` (below `md` only) + wordmark
  "AdvisorDesk Admin" (`Typography h6`, links `/`). Right = `Button variant="outlined"
  color="inherit" startIcon={<Icon name="SmartToy" />}` "Agent" (`SmartToy` added to
  `common/Icon`'s name map), avatar menu (unchanged).
- Nav drawer: `permanent` at `md`+ (240px), `temporary` below `md` (opens from the menu button,
  closes on navigation). `useAppShell` holds `isNarrow = useMediaQuery(theme.breakpoints.down('md'))`,
  `navOpen`, `agentOpen`. `NavList` items get icons (Dashboard, Article, Link) and
  `selected = pathname === href || (href !== '/' && pathname.startsWith(href))`.
- Agent drawer: `anchor="right"`, 400px at `md`+, `100vw` below.
- One `<main>`: `AppShell` renders `Box component="main"`; `PageContainer` becomes a plain
  `Container maxWidth="lg"` with no `component="main"` and no vertical padding (the shell pads
  once: `p: {xs: 2, md: 3}`).

### C2 Sign-in — `auth/SignInScreen`

Centred (`minHeight: 100vh`, flex) `Paper variant="outlined"` `maxWidth 400`, `p: 4`: wordmark,
`Typography body1` "Sign in to manage AdvisorDesk content", `Button variant="contained"
href=<API>/api/v1/auth/login` "Sign in with Google", `Typography caption` "Access is limited to
allowlisted admin accounts." `useSearchParams().get('error')` → `Alert severity="error"` above
the button with copy from `lib/copy.ts`: `forbidden` → "This Google account isn't on the admin
allowlist.", `state` → "Sign-in expired or was tampered with. Please try again." Any other value
→ no alert.

### C3 Dashboard — `dashboard/DashboardScreen`

`PageHeader title="Dashboard"`. Row of three `StatCard`s (`Grid xs=12 sm=4`): Draft / Published /
Archived → `href="/content?status=<status>"`. Below, `Grid md=6 | md=6`: **Content by tag**
(`Table`: Tag · Count, tag name links to `/content?tag=<tag>`) and **Recently updated**
(`Table`: Title (link) · Status · Updated; `contentApi.list({page_size: 5})`). Skeletons while
loading. The "N item(s)" test is rewritten.

### C4 Content list — `content/ContentListScreen` + `useContentList.ts`

- `PageHeader title="Content" actions={<Button href="/content/new" variant="contained">New content</Button>}`.
- Filters (`Stack direction={{xs:'column', sm:'row'}}`): Status `Select`, Tag `Select`, Search
  `TextField`; `Button variant="text"` "Clear filters" appears when any is set; `Typography
  body2` "Showing 1–20 of 31".
- **URL is the filter state:** `useContentList` reads `useSearchParams()` (`status`, `tag`, `q`,
  `page`) and writes with `router.replace` (debounced 300ms for `q`). Tested by rendering with a
  mocked `next/navigation`.
- `TableContainer component={Paper} variant="outlined"` + `Table`: Title (`Link` to editor) ·
  Status (`StatusChip`) · Tags (`Chip`s, `size="small" variant="outlined"`) · Updated
  (`formatDate` from new `lib/format.ts`, `Intl.DateTimeFormat('en-US', {dateStyle:'medium'})`) ·
  actions (`IconButton` Edit → editor, Delete → `ConfirmDialog destructive`). `hover` rows.
  Below `sm`, the container scrolls horizontally (`overflowX: 'auto'`).
- Loading: 5 skeleton rows. Empty: no filters + zero total → `EmptyState` "No content yet" +
  "Create your first article" button; filters set + zero → "No content matches these filters" +
  Clear filters. Stranded page (page > last) → `useContentList` clamps to the last page (WR-60).

### C5 Editor — `content/ContentEditorScreen` + `useContentEditor.ts`

- `PageHeader title={title || 'New content'} meta=<StatusChip + "Created … · Updated … ·
  Published …">` (fields from `ContentResponse`; omitted when null).
- Layout at `md`+: `Grid md=7` form | `Grid md=5` sticky preview (`position: sticky; top`),
  preview = `<Markdown variant="article" headingOffset={1}>{stripLeadingHeading(body, title)}`
  inside `Paper variant="outlined"`. Below `md`: existing Preview toggle switches the column.
- Form: `<form onSubmit>`; Title `TextField required` (`error` + `helperText` "Title is
  required" after blur or submit when empty; value trimmed on save); Body `TextField multiline
  minRows={16}` with `fontFamily: monospace`; Tags `Autocomplete freeSolo multiple` with
  `options` from `tagsApi.list` names.
- Action row (`Stack direction="row"`, wraps on xs): `Save`/`Create` (`contained`), `Publish`
  (`outlined`; when disabled wrapped in `Tooltip` "Save first" / "Already published"), `Archive`
  (`outlined`, when applicable), spacer, `Delete` (`outlined color="error"` → `ConfirmDialog
  destructive`).
- Feedback: `useSnackbar().success('Saved' | 'Published' | 'Archived' | 'Deleted')`; errors →
  `useSnackbar().error(message)`. Delete navigates to `/content`.
- Dirty guard: `useContentEditor` tracks `isDirty`; `beforeunload` listener while dirty. In-app
  navigation is not blocked (App Router has no supported blocker) — documented in the hook.

### C6 Connected apps — `connectedApps/ConnectedAppsScreen`

`PageHeader title="Connected apps" description="Apps authorised to use AdvisorDesk over MCP (for
example Claude). Revoking removes their access immediately."`. `Table`: Client (`client_name`
+ `Typography caption` short client id, first 12 chars) · Connected (`formatDateTime`) · Last
used (`last_used_at` or `PLACEHOLDER_DASH` from `lib/copy.ts`) · `Button variant="outlined"
color="error" size="small"` Revoke. Empty state renders under the header. Background refetch
failure → `useSnackbar().error(...)`.

### C7 Agent panel — `agent/AgentPanel` + `useAgentStream.ts`

- Header row in the drawer: `Typography h6` "Agent" · `Button variant="text"` "Clear" · close
  `IconButton`.
- Empty state: `EmptyState` with three suggested commands (buttons; `lib/copy.ts`).
- Turns: user = right-aligned `Paper`; assistant text via `<Markdown variant="chat">`; tool
  events render **in arrival order** interleaved with text segments. `ToolCallCard` becomes a
  collapsible `Paper variant="outlined"`: collapsed row "Ran `<tool>` · <summary>" (result) or
  "Running `<tool>`…" (call without result yet); expanded shows args and result in `<pre>`.
- "Working…" indicator while streaming; auto-scroll to the newest message; `Stop`
  (`useAgentStream.stop()`); composer `TextField multiline maxRows={4}`, Enter sends.

### Folded-in backlog

`docs/plans/phase-6-remediation/task-12-ui-polish.md` (never executed) is closed by this phase:
success snackbars (C5), unsaved-changes guard (C5), title trim (C5), logout redirect kept as is,
admin `lib/copy.ts` (C2), dead Drawer `onClose` (C1), AgentPanel → `EmptyState` (C7), dashboard
test scoping (C3), Markdown twin anti-drift (A2). Review findings closed: WR-60 (C4), F-5 (C6).
WR-12 (SSE parser duplication across apps) stays out of scope.

## 6. Testing

- TDD per task (RED evidence, then GREEN). Component tests: `// @vitest-environment jsdom`,
  RTL + user-event, queries by role/label, network mocked at the fetch edge only.
- Twin guards: `theme.twin.test.ts`, `Markdown.twin.test.ts` (node env, `fs`).
- Pure helpers get unit tests: `stripLeadingHeading`, `filterByTag`, `relatedArticles`,
  `formatDate`/`formatDateTime`, URL-state parsing in `useContentList`.
- Responsive behaviour is tested by mocking `window.matchMedia` in `useAppShell` tests
  (drawer variant switches).
- Gates before every commit: `pnpm -C apps/<app> type-check && lint && format:check && test`;
  API change (C0): `uv run pytest`, `uv run mypy`, openapi baseline + codegen re-run.
- Live visual checkpoint at the end of each sub-phase (owner + Chrome, desktop 1440 and phone
  390): no 96px headings; single article title; header/footer present; drawer collapses; delete
  is red; snackbars on save/publish/archive/delete; 404 branded; sources list clickable; no
  horizontal page scroll at 390px.

## 7. Out of scope

Dark mode · breadcrumbs · charts · react-hook-form/zod · MUI X DataGrid · in-app navigation
blocking · new API endpoints (tag filtering and related articles are computed client/RSC-side
from the existing list endpoint) · SEO beyond `metadata.title` · revoking the stale DCR clients
(owner's desktop-session item).
