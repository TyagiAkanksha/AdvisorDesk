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
