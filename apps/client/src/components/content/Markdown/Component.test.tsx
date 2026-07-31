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
});
