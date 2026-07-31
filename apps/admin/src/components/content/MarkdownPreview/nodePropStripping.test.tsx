// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it } from 'vitest';

import { MarkdownPreview } from '.';

// task-04 fix round 1 (F2 + F6 anti-drift pin). react-markdown@10 hardcodes `passNode: true` in
// its own `toJsxRuntime` call (node_modules/react-markdown/lib/index.js) — NOT opt-in, contrary
// to what `lib/index.d.ts` alone suggests. Every custom tag renderer therefore receives an
// extra `node` prop (the hast AST node); left in `{...props}` it lands on the DOM as a literal
// `node="[object Object]"` attribute.
//
// TWIN FIXTURE (F6): this file and apps/client/src/components/content/Markdown/
// nodePropStripping.test.tsx share the SAME canonical fixture string, verbatim, and the same
// assertions.
//
// Scope of what this actually pins (final review correction — the original wording here
// overstated this as a general anti-drift guarantee): it proves each renderer map
// independently strips `node` before it reaches the DOM — a `node`-stripping regression in
// either copy fails exactly that copy's suite. It does NOT prove the two maps otherwise stay
// identical (e.g. a `Typography` variant/tag or `Link` prop that drifts in one copy but not the
// other) — that broader mapping-drift guarantee doesn't exist and is separately ledgered.
const NODE_PROP_FIXTURE = `# Fixture Heading

Fixture paragraph with a [fixture link](https://example.com/fixture).
`;

afterEach(() => {
  cleanup();
});

describe('MarkdownPreview — node prop stripping (F2/F6 pin)', () => {
  it('renders the fixture heading, paragraph, and link without leaking a `node` DOM attribute', () => {
    const { container } = render(<MarkdownPreview markdown={NODE_PROP_FIXTURE} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Fixture Heading' })).toBeInTheDocument();
    expect(screen.getByText(/Fixture paragraph with a/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'fixture link' });
    expect(link).toHaveAttribute('href', 'https://example.com/fixture');

    // Every mapping must destructure `node` out before spreading `...props`, or react-markdown's
    // hardcoded `passNode: true` puts it on the DOM as `node="[object Object]"`.
    expect(container.innerHTML).not.toMatch(/\snode=/);
  });
});

// Final review (F2): the XSS-inertness pin previously existed only on the client renderer's
// twin (apps/client/src/components/content/Markdown/Component.test.tsx) — MarkdownPreview
// shares the same "no rehype-raw plugin" property (see that component's own module comment)
// but had no test of its own proving it. Same fixture, verbatim, as the client twin.
const RAW_HTML_FIXTURE = `Safe intro text.

<script>alert(1)</script>

<img src="x" onerror="alert(2)" />

Safe outro text.
`;

describe('MarkdownPreview — raw HTML injection is inert (F2 twin pin)', () => {
  it('neutralizes raw HTML injection: no script element, and any img is not left executable', () => {
    const { container } = render(<MarkdownPreview markdown={RAW_HTML_FIXTURE} />);

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
