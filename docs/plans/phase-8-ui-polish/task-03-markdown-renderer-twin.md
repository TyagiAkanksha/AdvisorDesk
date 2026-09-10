---
id: p8-t03
phase: phase-8-ui-polish
depends_on: [p8-t01]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 03 — Markdown renderer twin + `stripLeadingHeading`

## Goal

One complete markdown renderer, duplicated byte-for-byte into both apps and test-guarded, that
maps every tag react-markdown can emit onto the theme (lists, code, blockquotes, tables, rules,
images — not just headings/paragraphs/links), takes `variant: 'article' | 'chat'` and
`headingOffset: 0 | 1`, and — through a pure `stripLeadingHeading` helper — makes the article page
render its title **once**. Chat bubbles switch to the compact variant.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §A2 (and §2 principles).
- `docs/FRONTEND-CONVENTIONS.md` §3, §4, §7.
- `apps/client/src/components/content/Markdown/{Component.tsx, interface.ts, index.ts, Component.test.tsx, nodePropStripping.test.tsx}`
  — the current renderer and its pinned tests (all of which must keep passing).
- `apps/admin/src/components/content/MarkdownPreview/{Component.tsx, interface.ts, index.ts, Component.test.tsx, nodePropStripping.test.tsx}`
  — the twin; note it currently lives under `content/` (DESIGN.md's `common/` path is a typo —
  it imports from `@/components/common`, so it cannot live inside `common/`).
- `apps/client/src/components/common/{Box,Typography,Link}/` and the admin equivalents — the
  pass-through primitives the renderer composes (`Link` accepts every MUI `LinkProps`, so
  `target`/`rel` pass through).
- `apps/client/src/components/content/ArticleScreen/Component.tsx` (+ `Component.test.tsx`) —
  the doubled-title call site.
- `apps/client/src/components/chat/MessageBubble/Component.tsx` (+ `Component.test.tsx`) —
  the chat call site.
- `apps/admin/src/components/content/ContentEditorScreen/Component.tsx` line ~102 — the admin
  call site (props unchanged in this task; sub-phase C5 adds strip + offset once the editor has
  a header that shows the title).
- `apps/client/src/theme/theme.test.ts` (task 01) — for the `@media` key shape, not needed here.

## Files

**Create**
- `apps/client/src/components/common/Divider/{Component.tsx, interface.ts, index.ts}`
- `apps/admin/src/components/common/Divider/{Component.tsx, interface.ts, index.ts}`
- `apps/client/src/lib/markdown.ts` + `apps/client/src/lib/markdown.test.ts`
- `apps/client/src/components/content/Markdown/twin.test.ts`
- `apps/admin/src/components/content/MarkdownPreview/twin.test.ts`

**Modify**
- `apps/client/src/components/common/index.ts`, `apps/admin/src/components/common/index.ts` — export `Divider` + `DividerProps`.
- `apps/client/src/components/content/Markdown/Component.tsx` — replaced (content below).
- `apps/admin/src/components/content/MarkdownPreview/Component.tsx` — byte-identical copy.
- `apps/client/src/components/content/Markdown/interface.ts` — new props.
- `apps/admin/src/components/content/MarkdownPreview/interface.ts` — same props + compatibility alias.
- `apps/client/src/components/content/Markdown/Component.test.tsx` — new cases appended.
- `apps/admin/src/components/content/MarkdownPreview/Component.test.tsx` — one mapping case appended.
- `apps/client/src/components/content/ArticleScreen/Component.tsx` (+ test) — strip + offset.
- `apps/client/src/components/chat/MessageBubble/Component.tsx` (+ test) — `variant="chat"`.

## Interfaces

**Consumes:** `Box`, `Typography`, `Link` from `@/components/common` (both apps); theme tokens
from task 01 (`action.hover`, `grey.100`, `grey.50`, `divider`, `text.secondary`).

**Produces exactly:**

```ts
// common/Divider/interface.ts (both apps)
import type { DividerProps as MuiDividerProps } from '@mui/material/Divider';
// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4), same shape as Box.
export type DividerProps = MuiDividerProps;

// common/Divider/Component.tsx (both apps)
import MuiDivider from '@mui/material/Divider';
import type { DividerProps } from './interface';
export default function Component(props: DividerProps) {
  return <MuiDivider {...props} />;
}

// common/Divider/index.ts
export { default as Divider } from './Component';
export type { DividerProps } from './interface';

// client content/Markdown/interface.ts
export type MarkdownVariant = 'article' | 'chat';
export interface MarkdownProps {
  /** Markdown source. Prop name is the frozen contract from phase-3 task-04 — unchanged. */
  markdown: string;
  /** 'article' (default): reading sizes/margins. 'chat': body2, tighter, headings capped at h4 size. */
  variant?: MarkdownVariant;
  /** 1 → a `#` in the source renders as <h2> because the screen already owns the page h1. */
  headingOffset?: 0 | 1;
}

// admin content/MarkdownPreview/interface.ts — the same two declarations, plus:
/** Kept so ContentEditorScreen's existing import compiles; identical to MarkdownProps. */
export type MarkdownPreviewProps = MarkdownProps;
// admin index.ts keeps `export { default as MarkdownPreview } from './Component'` and exports
// both `MarkdownPreviewProps` and `MarkdownProps` types.

// client lib/markdown.ts
/**
 * Every CMS body starts with `# <title>` while the screen renders the title itself — remove that
 * first heading (case/whitespace-insensitive, trailing `#`s ignored) and any blank lines after it.
 * Anything else is returned unchanged.
 */
export function stripLeadingHeading(body: string, title: string): string;
```

**`Component.tsx` — exact content (both apps, byte-identical; the admin copy's `./interface`
exports the same `MarkdownProps`/`MarkdownVariant` names):**

```tsx
import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Box, Divider, Link, Typography } from '@/components/common';

import type { MarkdownProps, MarkdownVariant } from './interface';

// TWIN FILE (phase-8 task-03): apps/client/src/components/content/Markdown/Component.tsx and
// apps/admin/src/components/content/MarkdownPreview/Component.tsx are byte-identical, and each
// app's `twin.test.ts` fails if they diverge — edit both or neither. The two apps deploy
// independently, so the file is duplicated rather than shared (same rule as theme.ts).
//
// react-markdown (the synchronous default export — RSC-safe, no hooks) + remark-gfm, with every
// tag react-markdown can emit mapped onto the theme (DESIGN.md §A2). No `rehype-raw` is
// registered, so raw HTML inside markdown renders as escaped text, never as DOM nodes.
//
// react-markdown@10 hands every custom renderer a `node` prop (the hast AST node). Each mapping
// below takes an explicit prop allow-list — never `{...props}` — so `node` can't reach the DOM
// (`nodePropStripping.test.tsx` pins this in both apps).
//
// `variant`: 'article' = reading sizes and margins; 'chat' = body2, tighter margins, headings
// capped at the h4 size — an assistant answer is a bubble, not a page.
// `headingOffset`: 1 = a `#` in the source renders as <h2> (the screen already owns the h1);
// deeper headings shift with it, so the document outline stays correct.
type HeadingLevel = 1 | 2 | 3 | 4 | 5 | 6;
type HeadingVariant = `h${HeadingLevel}`;

interface Spacing {
  body: 'body1' | 'body2';
  paragraphMb: number;
  headingMt: number;
  headingMb: number;
  blockMy: number;
}

const SPACING: Record<MarkdownVariant, Spacing> = {
  article: { body: 'body1', paragraphMb: 2, headingMt: 4, headingMb: 1.5, blockMy: 2 },
  chat: { body: 'body2', paragraphMb: 1, headingMt: 1.5, headingMb: 0.5, blockMy: 1 },
};

const MONOSPACE = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

function clampLevel(level: number): HeadingLevel {
  return Math.min(Math.max(level, 1), 6) as HeadingLevel;
}

function isExternalHref(href: string): boolean {
  return /^https?:\/\//.test(href);
}

function buildComponents(variant: MarkdownVariant, headingOffset: 0 | 1): Components {
  const spacing = SPACING[variant];

  const heading = (level: HeadingLevel) => {
    const domLevel = clampLevel(level + headingOffset);
    const sizeLevel = variant === 'chat' ? clampLevel(Math.max(domLevel, 4)) : domLevel;
    const typographyVariant: HeadingVariant = `h${sizeLevel}`;
    return function Heading({ children }: { children?: ReactNode }) {
      return (
        <Typography
          variant={typographyVariant}
          component={`h${domLevel}`}
          sx={{ mt: spacing.headingMt, mb: spacing.headingMb }}
        >
          {children}
        </Typography>
      );
    };
  };

  return {
    h1: heading(1),
    h2: heading(2),
    h3: heading(3),
    h4: heading(4),
    h5: heading(5),
    h6: heading(6),
    p: ({ children }) => (
      <Typography variant={spacing.body} component="p" sx={{ mb: spacing.paragraphMb }}>
        {children}
      </Typography>
    ),
    a: ({ href, title, children }) => {
      const url = href ?? '';
      const external = isExternalHref(url);
      return (
        <Link
          href={url}
          title={title}
          target={external ? '_blank' : undefined}
          rel={external ? 'noopener noreferrer' : undefined}
        >
          {children}
        </Link>
      );
    },
    ul: ({ children }) => (
      <Box component="ul" sx={{ pl: 3, mt: 0, mb: spacing.paragraphMb }}>
        {children}
      </Box>
    ),
    ol: ({ children }) => (
      <Box component="ol" sx={{ pl: 3, mt: 0, mb: spacing.paragraphMb }}>
        {children}
      </Box>
    ),
    li: ({ children }) => (
      <Typography variant={spacing.body} component="li" sx={{ mb: 0.5 }}>
        {children}
      </Typography>
    ),
    blockquote: ({ children }) => (
      <Box
        component="blockquote"
        sx={{
          borderLeft: 3,
          borderColor: 'divider',
          color: 'text.secondary',
          pl: 2,
          ml: 0,
          my: spacing.blockMy,
        }}
      >
        {children}
      </Box>
    ),
    code: ({ children }) => (
      <Box
        component="code"
        sx={{
          fontFamily: MONOSPACE,
          fontSize: '0.875em',
          bgcolor: 'action.hover',
          borderRadius: 0.5,
          px: 0.5,
        }}
      >
        {children}
      </Box>
    ),
    pre: ({ children }) => (
      <Box
        component="pre"
        sx={{
          fontFamily: MONOSPACE,
          fontSize: '0.875rem',
          bgcolor: 'grey.100',
          borderRadius: 1,
          p: 2,
          my: spacing.blockMy,
          overflowX: 'auto',
          // The `code` mapping above also runs for the <code> inside a fenced block; undo its
          // inline styling here so the block reads as one surface.
          '& code': { bgcolor: 'transparent', px: 0, fontSize: 'inherit' },
        }}
      >
        {children}
      </Box>
    ),
    table: ({ children }) => (
      <Box sx={{ overflowX: 'auto', my: spacing.blockMy }}>
        <Box
          component="table"
          sx={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: variant === 'chat' ? '0.875rem' : '1rem',
            '& th, & td': {
              border: 1,
              borderColor: 'divider',
              px: 1.5,
              py: 1,
              textAlign: 'left',
              verticalAlign: 'top',
            },
            '& th': { fontWeight: 600, bgcolor: 'grey.50' },
          }}
        >
          {children}
        </Box>
      </Box>
    ),
    hr: () => <Divider sx={{ my: spacing.blockMy + 1 }} />,
    // A plain <img> on purpose: `common/Box` is typed as a <div> and has no `src`/`alt`; a
    // native element with one inline style is the smaller change than a new primitive.
    img: ({ src, alt }) => (
      <img
        src={typeof src === 'string' ? src : undefined}
        alt={alt ?? ''}
        style={{ maxWidth: '100%', height: 'auto', borderRadius: 8 }}
      />
    ),
  };
}

export default function Component({
  markdown,
  variant = 'article',
  headingOffset = 0,
}: MarkdownProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={buildComponents(variant, headingOffset)}>
      {markdown}
    </ReactMarkdown>
  );
}
```

(Run `pnpm -C apps/client lint:fix && pnpm -C apps/client format` on the client copy first —
import order and wrapping are decided by the tools — then copy the **final** file to the twin.)

**`lib/markdown.ts` — exact content (client):**

```ts
// phase-8 task-03 (DESIGN.md §A2). Every CMS body starts with `# <title>` (the seed articles
// and the editor convention), while `ArticleScreen` renders the title itself — so the page
// showed the title twice. Pure and tested here rather than special-cased inside the renderer:
// the renderer shouldn't know what a "title" is.
const LEADING_H1 = /^\s*#[ \t]+([^\n]*?)[ \t]*#*[ \t]*(?:\n|$)/;

export function stripLeadingHeading(body: string, title: string): string {
  const match = LEADING_H1.exec(body);
  if (!match) {
    return body;
  }
  const headingText = (match[1] ?? '').trim().toLowerCase();
  if (headingText !== title.trim().toLowerCase()) {
    return body;
  }
  return body.slice(match[0].length).replace(/^\n+/, '');
}
```

**Call sites:**
- `ArticleScreen/Component.tsx`:
  `<Markdown markdown={stripLeadingHeading(article.body_md, article.title)} headingOffset={1} />`
  (import `stripLeadingHeading` from `@/lib/markdown`). Nothing else changes in this task.
- `MessageBubble/Component.tsx`: `<Markdown markdown={message.text} variant="chat" />`.
- `ContentEditorScreen/Component.tsx`: unchanged (`<MarkdownPreview markdown={editor.body} />`).

## Steps (TDD)

- [ ] **RED — test-author.**

  1. `apps/client/src/lib/markdown.test.ts` (node env):

```ts
import { describe, expect, it } from 'vitest';

import { stripLeadingHeading } from './markdown';

describe('stripLeadingHeading', () => {
  it('removes a first-line `# Title` that matches the title and the blank lines after it', () => {
    expect(stripLeadingHeading('# Medicare Basics\n\nBody text.', 'Medicare Basics')).toBe(
      'Body text.',
    );
  });

  it('matches case- and whitespace-insensitively and ignores closing hashes', () => {
    expect(stripLeadingHeading('#   medicare BASICS  ##\nBody.', ' Medicare Basics ')).toBe(
      'Body.',
    );
  });

  it('leaves the body alone when the first heading is a different title', () => {
    const body = '# Something Else\n\nBody.';
    expect(stripLeadingHeading(body, 'Medicare Basics')).toBe(body);
  });

  it('leaves the body alone when it does not start with an h1', () => {
    expect(stripLeadingHeading('Intro\n\n# Medicare Basics', 'Medicare Basics')).toBe(
      'Intro\n\n# Medicare Basics',
    );
    expect(stripLeadingHeading('## Medicare Basics\nBody.', 'Medicare Basics')).toBe(
      '## Medicare Basics\nBody.',
    );
  });

  it('handles a body that is only the heading, and an empty body', () => {
    expect(stripLeadingHeading('# Medicare Basics', 'Medicare Basics')).toBe('');
    expect(stripLeadingHeading('', 'Medicare Basics')).toBe('');
  });
});
```

  2. Append to `apps/client/src/components/content/Markdown/Component.test.tsx` (inside the
     existing `describe`; existing fixtures/tests untouched):

```tsx
  it('shifts every heading down one level when headingOffset is 1 (the screen owns the h1)', () => {
    render(<Markdown markdown={'# Top\n\n## Section'} headingOffset={1} />);

    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
    expect(screen.getByRole('heading', { level: 2, name: 'Top' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Section' })).toBeInTheDocument();
  });

  it('caps chat-variant headings at the h4 size while keeping their semantic level', () => {
    render(<Markdown markdown={'# Answer heading'} variant="chat" />);

    const heading = screen.getByRole('heading', { level: 1, name: 'Answer heading' });
    expect(heading.className).toContain('MuiTypography-h4');
  });

  it('uses body2 paragraphs in the chat variant and body1 in the article variant', () => {
    const { unmount } = render(<Markdown markdown={'Plain paragraph.'} variant="chat" />);
    expect(screen.getByText('Plain paragraph.').className).toContain('MuiTypography-body2');
    unmount();

    render(<Markdown markdown={'Plain paragraph.'} />);
    expect(screen.getByText('Plain paragraph.').className).toContain('MuiTypography-body1');
  });

  it('renders fenced code as <pre><code> and inline code as <code>', () => {
    const { container } = render(
      <Markdown markdown={'Use `pnpm test`.\n\n```\nconst x = 1;\n```'} />,
    );

    const pre = container.querySelector('pre');
    expect(pre).not.toBeNull();
    expect(pre?.querySelector('code')).toHaveTextContent('const x = 1;');
    expect(container.querySelectorAll('code')).toHaveLength(2);
  });

  it('renders blockquotes, thematic breaks, and images as their semantic elements', () => {
    const { container } = render(
      <Markdown markdown={'> Quoted line\n\n---\n\n![A chart](https://example.com/c.png)'} />,
    );

    expect(container.querySelector('blockquote')).toHaveTextContent('Quoted line');
    expect(screen.getByRole('separator')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'A chart' })).toHaveAttribute(
      'src',
      'https://example.com/c.png',
    );
  });

  it('opens external links in a new tab with rel=noopener and keeps internal links in-tab', () => {
    render(<Markdown markdown={'[out](https://example.com) and [in](/content/slug)'} />);

    const external = screen.getByRole('link', { name: 'out' });
    expect(external).toHaveAttribute('target', '_blank');
    expect(external).toHaveAttribute('rel', 'noopener noreferrer');
    const internal = screen.getByRole('link', { name: 'in' });
    expect(internal).not.toHaveAttribute('target');
    expect(internal).toHaveAttribute('href', '/content/slug');
  });
```

  3. `apps/client/src/components/content/Markdown/twin.test.ts` (node env; admin copy at
     `MarkdownPreview/twin.test.ts` swaps the two paths):

```ts
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// phase-8 task-03: the renderer is duplicated into both apps on purpose (independent deploys).
// `nodePropStripping.test.tsx` only proves each copy strips `node`; this proves the copies ARE
// the same file.
const OWN_COPY = new URL('./Component.tsx', import.meta.url);
const TWIN_COPY = new URL(
  '../../../../../admin/src/components/content/MarkdownPreview/Component.tsx',
  import.meta.url,
);

describe('Markdown renderer twin guard', () => {
  it('is byte-identical to the other app’s copy', () => {
    expect(readFileSync(OWN_COPY, 'utf8')).toBe(readFileSync(TWIN_COPY, 'utf8'));
  });
});
```

  4. Append to `apps/admin/src/components/content/MarkdownPreview/Component.test.tsx`:

```tsx
  it('renders fenced code as <pre><code> (the full tag mapping is live in the admin twin)', () => {
    const { container } = render(<MarkdownPreview markdown={'```\nconst x = 1;\n```'} />);

    expect(container.querySelector('pre code')).toHaveTextContent('const x = 1;');
  });
```

  5. Append to `apps/client/src/components/content/ArticleScreen/Component.test.tsx` (use that
     file's existing fixture style; `body_md` here must start with `# <title>`):

```tsx
  it('renders the title exactly once as the only h1 even though body_md starts with `# <title>`', () => {
    render(
      <ArticleScreen
        article={{
          title: 'Medicare Basics',
          slug: 'medicare-basics',
          tags: ['insurance'],
          published_at: '2026-08-09T00:00:00Z',
          body_md: '# Medicare Basics\n\n## Parts of Medicare\n\nBody.',
        }}
      />,
    );

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'Medicare Basics' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Parts of Medicare' })).toBeInTheDocument();
  });
```

  6. Append to `apps/client/src/components/chat/MessageBubble/Component.test.tsx`:

```tsx
  it('renders assistant markdown in the compact chat variant (body2 paragraphs)', () => {
    const message: ChatMessage = { role: 'assistant', text: 'Short answer.' };

    render(<MessageBubble message={message} />);

    expect(screen.getByText('Short answer.').className).toContain('MuiTypography-body2');
  });
```

- [ ] **Run RED:**
  `pnpm -C apps/client test -- markdown Markdown ArticleScreen MessageBubble && pnpm -C apps/admin test -- MarkdownPreview`
  Expected: FAIL — `@/lib/markdown` missing; `headingOffset`/`variant` not props; `pre`
  present but `MuiTypography-body2`/`separator`/`target` assertions fail; twin files differ;
  ArticleScreen finds two h1s.

- [ ] **GREEN — implementer**, in this order: `Divider` primitive in both apps (+ barrel
  exports) → `lib/markdown.ts` → client `interface.ts` → client `Component.tsx` → run
  `pnpm -C apps/client lint:fix && pnpm -C apps/client format` → **copy the final file** to the
  admin path (`cp`) → admin `interface.ts` (+ alias) and `index.ts` type exports → `ArticleScreen`
  → `MessageBubble`.

- [ ] **Run GREEN:** same commands → PASS, including every pre-existing Markdown/MarkdownPreview
  test (`nodePropStripping` in both apps must still pass — the allow-list rule).

- [ ] `pnpm -C apps/client type-check && pnpm -C apps/admin type-check` → clean.

- [ ] **Screenshots:** client `/content/medicare-enrollment-basics` (or any seeded slug) at 1440
  and 390 — one title, h2 sections at 28px, lists indented; client `/chat` after sending one
  question locally (dev API) or, if no local API, a MessageBubble story rendered via a throwaway
  page — body2 text in the bubble. Admin editor Preview toggle showing a fenced code block.

- [ ] **Gates:** `pnpm gates:client && pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/client/src/components/common/Divider apps/admin/src/components/common/Divider apps/client/src/components/common/index.ts apps/admin/src/components/common/index.ts apps/client/src/lib/markdown.ts apps/client/src/lib/markdown.test.ts apps/client/src/components/content/Markdown apps/admin/src/components/content/MarkdownPreview apps/client/src/components/content/ArticleScreen apps/client/src/components/chat/MessageBubble`
  `git commit -m "feat(web): complete markdown renderer twin with article/chat variants; single article title (p8 t03)"`

## Verify

```bash
pnpm -C apps/client test -- markdown Markdown ArticleScreen MessageBubble
pnpm -C apps/admin test -- MarkdownPreview
diff apps/client/src/components/content/Markdown/Component.tsx apps/admin/src/components/content/MarkdownPreview/Component.tsx && echo TWIN_OK
pnpm gates:client && pnpm gates:admin
```

## Acceptance

- `diff` of the two `Component.tsx` files is empty; both twin tests pass.
- All previously pinned Markdown/MarkdownPreview tests still pass unchanged.
- Article page renders one h1; `##` sections become h3 under it (correct outline).
- Chat bubbles use body2 and h4-capped headings.
- No `{...props}` spread in any renderer mapping (reviewer greps for it).
- Reviewer (Opus) checks the five dimensions with file:line evidence, and that `Divider` is the
  only primitive added (no new MUI import outside `common/`).
