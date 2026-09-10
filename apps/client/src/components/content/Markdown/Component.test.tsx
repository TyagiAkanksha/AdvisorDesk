// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it } from 'vitest';

import { Markdown } from '.';

// task-04 (phase-3): the shared markdown renderer — `{markdown: string}` in, react-markdown +
// remark-gfm mapped onto MUI components out (docs/plans/phase-3-publish-client-content/
// task-04-client-content-ui.md, "Interfaces"). Phase-4 task-05 reuses this component verbatim
// for assistant answers, and the admin `MarkdownPreview` swaps its internals onto it without a
// props change (apps/admin/src/components/content/MarkdownPreview/Component.test.tsx is pinned
// against the TEXT it renders, not markup, so that swap stays green by construction).
//
// apps/client/vitest.config.ts has no `setupFiles` (unlike apps/admin's, which registers RTL's
// `cleanup()` because auto-cleanup doesn't fire under `globals: false` — see
// apps/admin/vitest.setup.ts). Until that gap is closed for apps/client too, this file
// registers its own `afterEach(cleanup)` so its multiple renders-per-file don't leak DOM state
// between `it` blocks.
afterEach(() => {
  cleanup();
});

const gfmFixture = `# Primary Heading

## Secondary Heading

- Bullet one
- Bullet two

1. Ordered one
2. Ordered two

Some **bold text** and _italic text_ in a paragraph.

[Learn more](https://example.com/resource)
`;

const tableFixture = `| Fund | Fee |
| --- | --- |
| Total Market Index | 0.03% |
| Bond Index | 0.05% |
`;

const rawHtmlFixture = `Safe intro text.

<script>alert(1)</script>

<img src="x" onerror="alert(2)" />

Safe outro text.
`;

describe('Markdown', () => {
  it('renders headings at their correct levels', () => {
    render(<Markdown markdown={gfmFixture} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Primary Heading' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 2, name: 'Secondary Heading' }),
    ).toBeInTheDocument();
  });

  it('renders bullet and ordered lists as list/listitem roles', () => {
    render(<Markdown markdown={gfmFixture} />);

    // Two lists (one bullet, one ordered) — both `ul` and `ol` expose ARIA role "list".
    expect(screen.getAllByRole('list')).toHaveLength(2);
    expect(screen.getByText('Bullet one')).toBeInTheDocument();
    expect(screen.getByText('Bullet two')).toBeInTheDocument();
    expect(screen.getByText('Ordered one')).toBeInTheDocument();
    expect(screen.getByText('Ordered two')).toBeInTheDocument();
  });

  it('renders a link with an accessible name and the correct href', () => {
    render(<Markdown markdown={gfmFixture} />);

    const link = screen.getByRole('link', { name: 'Learn more' });
    expect(link).toHaveAttribute('href', 'https://example.com/resource');
  });

  it('renders bold and italic emphasis as visible text', () => {
    render(<Markdown markdown={gfmFixture} />);

    expect(screen.getByText('bold text')).toBeInTheDocument();
    expect(screen.getByText('italic text')).toBeInTheDocument();
  });

  it('renders a GFM table (remark-gfm proof) with header and cell text', () => {
    render(<Markdown markdown={tableFixture} />);

    // Pipe-table syntax only becomes a real `<table>` with remark-gfm — plain remark-parse
    // leaves it as an unparsed paragraph, so this is the plugin's structural proof.
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Fund' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Fee' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Total Market Index' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '0.03%' })).toBeInTheDocument();
  });

  it('neutralizes raw HTML injection: no script element, and any img is not left executable', () => {
    const { container } = render(<Markdown markdown={rawHtmlFixture} />);

    // react-markdown skips raw HTML nodes by default (no rehype-raw) — pin that property.
    expect(container.querySelector('script')).toBeNull();

    // Either the img never made it into the tree, or — if a future renderer choice sanitizes
    // raw HTML instead of dropping it — the dangerous handler attribute must not survive.
    const img = container.querySelector('img');
    if (img) {
      expect(img).not.toHaveAttribute('onerror');
    }

    // The component didn't blank out entirely — surrounding safe text still renders.
    expect(screen.getByText(/Safe intro text/)).toBeInTheDocument();
    expect(screen.getByText(/Safe outro text/)).toBeInTheDocument();
  });

  // phase-8 task-03 (DESIGN.md §A2): `variant`/`headingOffset` are new props — RED until the
  // implementer adds them to `MarkdownProps` and wires up the full tag mapping.
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

  // fix round 1 (Important 1): the tag-map object handed to `ReactMarkdown` must be a STABLE
  // reference across renders of the same (variant, headingOffset) pair, or react-markdown treats
  // every renderer as a brand-new component type and unmounts/remounts the whole subtree instead
  // of reconciling it (a real cost for e.g. `ContentEditorScreen` re-rendering `MarkdownPreview`
  // on every keystroke). A remount would create a NEW DOM node for the same text on `rerender`.
  it('reconciles the same DOM node across a re-render instead of remounting the subtree', () => {
    const { rerender } = render(<Markdown markdown={'Para'} />);
    const first = screen.getByText('Para');

    rerender(<Markdown markdown={'Para'} />);

    expect(screen.getByText('Para')).toBe(first);
  });

  // fix round 1 (Important 2, controller ruling): `headingOffset` shifts the DOM tag (semantic
  // outline correction) but visual SIZE follows the SOURCE level, floored at `headingOffset + 1`
  // so a body heading never grows to the page title's own size.
  it('sizes a shifted heading by its source level, floored so it never matches the page title size', () => {
    render(<Markdown markdown={'## Section'} headingOffset={1} />);

    const heading = screen.getByRole('heading', { level: 3, name: 'Section' });
    expect(heading.className).toContain('MuiTypography-h2');
  });

  it('floors a top-level shifted heading at the offset size instead of the page title size', () => {
    render(<Markdown markdown={'# Body top'} headingOffset={1} />);

    const heading = screen.getByRole('heading', { level: 2, name: 'Body top' });
    expect(heading.className).toContain('MuiTypography-h2');
  });

  // fix round 1 (Minor 3): the `table` mapping had no test of its own — pin that a GFM table
  // renders as a real `table` role wrapped in a horizontally-scrollable container.
  it('wraps a GFM table in a horizontally scrollable container', () => {
    const { container } = render(
      <Markdown markdown={'| Fund | Fee |\n| --- | --- |\n| Total Market Index | 0.03% |\n'} />,
    );

    expect(screen.getByRole('columnheader', { name: 'Fund' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Fee' })).toBeInTheDocument();
    const wrapper = container.querySelector('table')?.parentElement;
    expect(wrapper).toHaveStyle({ overflowX: 'auto' });
  });
});
