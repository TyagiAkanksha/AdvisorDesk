// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it } from 'vitest';

import { Markdown } from '.';

// task-04 fix round 1 (F2 + F6 anti-drift pin). react-markdown@10 hardcodes `passNode: true` in
// its own `toJsxRuntime` call (node_modules/react-markdown/lib/index.js) — NOT opt-in, contrary
// to what `lib/index.d.ts` alone suggests. Every custom tag renderer therefore receives an
// extra `node` prop (the hast AST node); left in `{...props}` it lands on the DOM as a literal
// `node="[object Object]"` attribute and gets serialized whole into the RSC Flight payload.
//
// TWIN FIXTURE (F6): this file and apps/admin/src/components/content/MarkdownPreview/
// nodePropStripping.test.tsx share the SAME canonical fixture string, verbatim, and the same
// assertions. The two renderer maps (content/Markdown vs. MarkdownPreview) are byte-identical
// with no shared code enforcing that — this pair of tests is the enforcement: a `node`-stripping
// fix applied to one copy and not the other fails exactly one of these two suites, never neither.
const NODE_PROP_FIXTURE = `# Fixture Heading

Fixture paragraph with a [fixture link](https://example.com/fixture).
`;

afterEach(() => {
  cleanup();
});

describe('Markdown — node prop stripping (F2/F6 pin)', () => {
  it('renders the fixture heading, paragraph, and link without leaking a `node` DOM attribute', () => {
    const { container } = render(<Markdown markdown={NODE_PROP_FIXTURE} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Fixture Heading' })).toBeInTheDocument();
    expect(screen.getByText(/Fixture paragraph with a/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'fixture link' });
    expect(link).toHaveAttribute('href', 'https://example.com/fixture');

    // Every mapping must destructure `node` out before spreading `...props`, or react-markdown's
    // hardcoded `passNode: true` puts it on the DOM as `node="[object Object]"`.
    expect(container.innerHTML).not.toMatch(/\snode=/);
  });
});
