---
id: p8-t24
phase: phase-8-ui-polish
depends_on: [p8-t23]
status: done
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 24 — Client carry-ins from the sub-phase B final review (one small PR)

## Goal

Close the fourteen minors the sub-phase B whole-branch review deferred (INDEX "Sub-phase C →
Additional constraints → Deferred minors from B"), kept out of the admin PR so the three-image
deploy's revert story stayed clean. Thirteen ship here; one (the `maxRows` pin) is dropped with
a reason. Every item is small; the a11y semantics (page heading during a conversation, the
disclaimer's live-region role, one landmark per Sources list) are the ones worth a real review.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2, §4 B1–B4.
- `docs/FRONTEND-CONVENTIONS.md` §3, §4, §7, §9.
- `apps/client/src/components/content/{ArticleScreen/Component.tsx, ArticleScreen/components/{TagChips,RelatedArticles}/*, ArticleCard/*}`
- `apps/client/src/components/chat/{ChatScreen/Component.tsx, ChatScreen/components/ChatWelcome/*, ChatScreen/useChatComposer.ts, ChatScreen/components/ChatComposer/interface.ts, CitationList/*, useChatStream.test.ts}`
- `apps/client/src/components/shell/{SiteHeader,SiteNav}/Component.tsx`
- `apps/client/src/components/common/{TextField/*, Icon/Component.tsx}`; `apps/admin/src/components/common/TextField/*`,
  `apps/admin/src/components/agent/AgentPanel/{useAgentComposer.ts, components/AgentComposer/interface.ts}`
- `apps/client/src/app/{page.tsx, content/[slug]/page.tsx}`, `apps/client/src/lib/{copy.ts, publicApi.ts}`
- `apps/client/src/theme/theme.twin.test.ts`, `apps/admin/src/theme/theme.twin.test.ts`
- Existing pins that this task REWRITES (declared): `ArticleScreen/Component.test.tsx:123`
  (`getByRole('alert')` for the disclaimer), `CitationList/Component.test.tsx:16-19`
  (`navigation` named Sources), `ChatWelcome/Component.test.tsx:14` (h1 inside the welcome),
  `ChatScreen/Component.test.tsx:307` (`queryByRole('heading', { level: 1 })` null after a
  message), `ArticleScreen/components/TagChips/Component.test.tsx` (moves with the component).

## Files

**Create**
- `apps/client/src/components/content/TagChips/{Component.tsx, interface.ts, index.ts, Component.test.tsx}` (moved from `ArticleScreen/components/TagChips/` — delete the old folder)

**Modify (client)**
- `src/lib/copy.ts` — `BACK_TO_ARTICLES_LINK_TEXT = '← Back to articles'`
- `src/components/content/ArticleScreen/Component.tsx` — `role="note"` on the disclaimer Alert; the back link text from copy; `TagChips` import path
- `src/components/content/ArticleScreen/Component.test.tsx` — pin rewrite (RED)
- `src/components/content/ArticleCard/{Component.tsx, interface.ts}` — `titleAs?: 'h2' | 'h3'` (default `'h2'`); chips via the shared `TagChips`
- `src/components/content/ArticleScreen/components/RelatedArticles/Component.tsx` — `titleAs="h3"`
- `src/components/chat/ChatScreen/Component.tsx` — always renders the page h1 (`variant="h1"` on the welcome, `variant="h4" component="h1"` once a conversation exists)
- `src/components/chat/ChatScreen/components/ChatWelcome/Component.tsx` — no h1 of its own
- `src/components/chat/CitationList/Component.tsx` — `section` (region) instead of `nav`
- `src/components/chat/ChatScreen/useChatComposer.ts`, `components/ChatComposer/interface.ts` — `KeyboardEvent<HTMLElement>`
- `src/components/common/TextField/{Component.tsx, interface.ts}` — typed `onKeyDown`, no cast
- `src/components/common/Icon/Component.tsx` — prune `Add, Chat, Close, Dashboard, Delete, Edit, Info, Logout, Menu` (used: `Article`, `Search`, `Send`, `Stop`)
- `src/components/shell/SiteHeader/Component.tsx` — header wraps below ~330px
- `src/app/page.tsx` — `tag?: string | string[]`
- `src/app/content/[slug]/page.tsx` — related list failure-tolerant
- `src/lib/publicApi.ts` — `getPublishedContent` wrapped in `cache()`; new `getPublishedContentOrEmpty`
- `src/theme/theme.twin.test.ts` — also guards `theme.test.ts`
- tests: `useChatStream.test.ts` (+2 guard cases), `CitationList`, `ChatWelcome`, `ChatScreen`, `ArticleCard`, `RelatedArticles`, `SiteHeader`, `lib/publicApi.test.ts` (new)

**Modify (admin — the two type twins)**
- `apps/admin/src/components/common/TextField/{Component.tsx, interface.ts}` — same typed `onKeyDown`
- `apps/admin/src/components/agent/AgentPanel/useAgentComposer.ts` — `KeyboardEvent<HTMLElement>`
- `apps/admin/src/theme/theme.twin.test.ts` — also guards `theme.test.ts`

## Interfaces

```ts
// client lib/copy.ts addition (the glyph lives in copy, not JSX)
export const BACK_TO_ARTICLES_LINK_TEXT = '← Back to articles';

// content/TagChips/interface.ts (moved; unchanged shape)
export interface TagChipsProps { tags: string[] }

// content/ArticleCard/interface.ts
export interface ArticleCardProps {
  item: PublicContentSummary;
  /** Heading level for the card title — 'h3' when the card sits under a section h2 (Related articles). */
  titleAs?: 'h2' | 'h3';   // default 'h2'; the Typography keeps variant="h4"
}

// chat/ChatScreen/Component.tsx — page heading always present:
//   messages.length === 0 → <Typography variant="h1" component="h1">{CHAT_TITLE}</Typography> then <ChatWelcome onAsk={send} />
//   otherwise            → <Typography variant="h4" component="h1" sx={{ mb: 2 }}>{CHAT_TITLE}</Typography> then the transcript
// chat/ChatScreen/components/ChatWelcome — region + description + suggestions only (no heading)

// chat/CitationList — <Box component="section" aria-label={SOURCES_LABEL}> … (role region, one per message; `nav` is for site navigation)

// content/ArticleScreen — <Alert severity="info" variant="outlined" role="note" sx={{ mt: 4 }}>{DISCLAIMER}</Alert>
//                          <Link href="/" …>{BACK_TO_ARTICLES_LINK_TEXT}</Link>

// common/TextField/interface.ts (both apps)
onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;   // passed straight to MuiTextField (KeyboardEvent<HTMLDivElement> is assignable) — no cast
// useChatComposer / useAgentComposer: onKeyDown: (event: KeyboardEvent<HTMLElement>) => void

// lib/publicApi.ts
export const getPublishedContent = cache(async (): Promise<PublicContentSummaryDto[]> => { …unchanged body… });
/** The related-articles list must never take an article page down: a failed list fetch → []. */
export async function getPublishedContentOrEmpty(): Promise<PublicContentSummaryDto[]> {
  try { return await getPublishedContent(); } catch { return []; }
}
// app/content/[slug]/page.tsx: Promise.all([getContentBySlug(slug), getPublishedContentOrEmpty()])
// app/page.tsx: searchParams: Promise<{ tag?: string | string[] }>; selectedTag = typeof tag === 'string' && tag.length > 0 ? tag : null

// shell/SiteHeader — Toolbar sx gains `flexWrap: 'wrap', rowGap: 1, columnGap: 2` so the wordmark and nav stack instead of colliding under ~330px

// theme.twin.test.ts (both apps) — second case: `theme.test.ts` byte-identical to the other app's
```

## Steps (TDD)

- [ ] **RED — test-author.**

**`ArticleScreen/Component.test.tsx`** — rewrite line 123's pin to:

```tsx
    expect(screen.getByRole('note')).toHaveTextContent('not financial advice');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
```

and append:

```tsx
  it('renders the back link with the glyph from copy', () => {
    renderArticle();   // the file's existing render helper
    expect(screen.getByRole('link', { name: '← Back to articles' })).toHaveAttribute('href', '/');
  });
```

**`content/TagChips/Component.test.tsx`** — the moved file (import from `'.'` in the new folder);
cases unchanged.

**`ArticleCard/Component.test.tsx`** — append:

```tsx
  it('renders the title as an h3 when titleAs="h3"', () => {
    render(<ArticleCard item={item} titleAs="h3" />);
    expect(screen.getByRole('heading', { level: 3, name: item.title })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();
  });
```

**`RelatedArticles/Component.test.tsx`** — append:

```tsx
  it('renders card titles as h3 under its own h2', () => {
    render(<RelatedArticles items={[itemA]} />);   // the file's fixture name
    expect(screen.getByRole('heading', { level: 2, name: 'Related articles' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: itemA.title })).toBeInTheDocument();
  });
```

**`ChatWelcome/Component.test.tsx`** — rewrite line 14 to assert NO heading inside the welcome
(`expect(screen.queryByRole('heading')).not.toBeInTheDocument()`) while the region, description
and four buttons are still asserted.

**`ChatScreen/Component.test.tsx`** — rewrite line 307 to:

```tsx
    expect(screen.getByRole('heading', { level: 1, name: 'Ask a question' })).toBeInTheDocument();
```

(the case's title becomes "keeps the page h1 once a conversation starts").

**`CitationList/Component.test.tsx`** — rewrite the first case: title "renders a Sources region
with one numbered, titled link per citation in order"; `getByRole('region', { name: 'Sources' })`;
append `expect(screen.queryByRole('navigation')).not.toBeInTheDocument();`.

**`useChatStream.test.ts`** — append (reuse the file's `streamResponse` + the gated helper):

```ts
  it('retry() is a no-op while streaming', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Partial' } },
      { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
    ]);
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('Q'));
    await waitFor(() => expect(result.current.streaming).toBe(true));

    act(() => result.current.retry());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    release();
    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.messages.map((m) => m.role)).toEqual(['user', 'assistant']);
  });

  it('reset() while streaming aborts and leaves no messages behind', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Partial' } },
      { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('Q'));
    await waitFor(() => expect(result.current.streaming).toBe(true));

    act(() => result.current.reset());
    release();

    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.messages).toEqual([]);
    expect(result.current.error).toBeNull();
  });
```

(If the hook file lacks `gatedStreamResponse`, copy the one from `ChatScreen/Component.test.tsx`
verbatim. If the reset-while-streaming case fails after GREEN because released frames land after
the abort, the implementer adds the same post-abort guard the admin hook has — see
`apps/admin/src/components/agent/useAgentStream.ts` `applyIfNotAborted` — never weaken the test.)

**`lib/publicApi.test.ts`** (new, node env):

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getPublishedContentOrEmpty } from './publicApi';

describe('getPublishedContentOrEmpty', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the list when the fetch succeeds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([{ slug: 'a' }]), { status: 200 })));
    await expect(getPublishedContentOrEmpty()).resolves.toEqual([{ slug: 'a' }]);
  });

  it('returns [] when the fetch fails or rejects — a broken list never takes an article page down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 500 })));
    await expect(getPublishedContentOrEmpty()).resolves.toEqual([]);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    await expect(getPublishedContentOrEmpty()).resolves.toEqual([]);
  });
});
```

**`SiteHeader/Component.test.tsx`** — append (or create the file if absent, rendering `<SiteHeader />`
with `vi.mock('next/navigation', () => ({ usePathname: () => '/' }))`):

```tsx
  it('lets the wordmark and nav wrap instead of colliding on very narrow screens', () => {
    render(<SiteHeader />);
    const toolbar = screen.getByRole('banner').querySelector('.MuiToolbar-root');
    expect(toolbar).toHaveStyle({ flexWrap: 'wrap' });
  });
```

**`theme.twin.test.ts`** (both apps) — append:

```ts
  it('keeps theme.test.ts byte-identical to the other app’s too', () => {
    expect(readFileSync(new URL('./theme.test.ts', import.meta.url), 'utf8')).toBe(
      readFileSync(new URL(TWIN_TEST_COPY, import.meta.url), 'utf8'),
    );
  });
```

with `const TWIN_TEST_COPY = '../../../admin/src/theme/theme.test.ts'` (client) /
`'../../../client/src/theme/theme.test.ts'` (admin) next to the existing `TWIN_COPY`.

**`common/TextField/Component.test.tsx`** (client) — append a type-level pin:

```tsx
  it('types onKeyDown as a plain HTMLElement keyboard event (no cast needed by callers)', async () => {
    const seen: string[] = [];
    const onKeyDown = (event: KeyboardEvent<HTMLElement>) => { seen.push(event.key); };
    render(<TextField label="Message" value="" onChange={vi.fn()} onKeyDown={onKeyDown} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'a');
    expect(seen).toContain('a');
  });
```

(`import type { KeyboardEvent } from 'react'`.) This compiles today too — it is a regression guard
for the interface; say so in the report.

- [ ] **Run RED:** `pnpm -C apps/client test` → the moved TagChips test unresolved; ArticleScreen
  note/link, ArticleCard/RelatedArticles h3, ChatWelcome/ChatScreen heading, CitationList region,
  publicApi (unresolved export), SiteHeader wrap, twin theme.test (GREEN today — guard), hook
  guard cases (retry-while-streaming may already pass — that is fine; reset-while-streaming is
  the RED one), TextField type pin (green — guard). `pnpm -C apps/admin test -- twin` green.

- [ ] **GREEN — implementer:** copy → `content/TagChips` move (+ ArticleCard + ArticleScreen use it;
  delete the old folder) → ArticleScreen role/link → ArticleCard `titleAs` + RelatedArticles →
  ChatScreen/ChatWelcome heading → CitationList section → TextField typing in BOTH apps +
  both composers → Icon prune → SiteHeader wrap → pages + publicApi → twin guards. `pnpm -C apps/client
  type-check && pnpm -C apps/admin type-check` after the typing change.

- [ ] **Run GREEN:** `pnpm -C apps/client test`; `pnpm -C apps/admin test` (TextField/composer/twin
  pins).

- [ ] **Screenshots** (iframe technique): client `/` at **320×568** (header wraps cleanly), article
  page 1440 (note-styled disclaimer unchanged visually, back link), `/chat` 1440 after one
  scripted message (compact h1 above the transcript; stub `fetch`, no real request). Store as
  `t24-*.jpg`.

- [ ] **Gates:** `pnpm gates:client` and `pnpm gates:admin` → clean, zero warnings; `pnpm -C apps/client build`
  and `pnpm -C apps/admin build` exit 0.

- [ ] **Commit:** path-scoped `git add apps/client/src apps/admin/src/components/common/TextField apps/admin/src/components/agent/AgentPanel/useAgentComposer.ts apps/admin/src/theme/theme.twin.test.ts`;
  `git commit -m "fix(client): sub-phase B carry-ins — a11y semantics, shared TagChips, typed onKeyDown, safe related list, icon prune (p8 t24)"`.

## Dropped (with reason)

- **`maxRows` pin** (t04 minor): MUI's `TextareaAutosize` exposes `maxRows` only through measured
  heights; jsdom has no layout, so no observable assertion exists. The primitive is a pass-through
  and `maxRows={6}` is exercised by the composer screenshots.

## Acceptance

- Disclaimer is `role="note"`; page h1 present before and after a conversation; one `region`
  named Sources per message and no `nav` inside the transcript; related card titles are h3.
- `TagChips` shared by the article page and `ArticleCard`; `onKeyDown` typed without a cast in
  both apps; nine unused icons gone from the client registry; `theme.test.ts` twin-guarded.
- A failing published-list fetch renders the article with no related section instead of an
  error page; `?tag=` repeated in the URL is treated as absent; the header wraps at 320px.
