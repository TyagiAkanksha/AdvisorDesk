// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { MarkdownPreview } from '.';

// task-06 Interfaces: `MarkdownPreview` renders as a `<pre>` placeholder THIS phase; phase-3
// task-04 swaps the internals for the shared markdown renderer without the props contract
// changing. This file pins the contract itself — `{markdown: string}` in, the text visible
// out — not the placeholder tag, so it survives that later swap unmodified.
//
// `MarkdownPreview` does not exist yet — every test below is RED until the implementer
// creates it (task-06 Step 3/4).
describe('MarkdownPreview', () => {
  it('renders the markdown prop as visible text', () => {
    const markdown = '# Roth IRA Conversion Basics\n\nSample body for preview.';
    render(<MarkdownPreview markdown={markdown} />);

    // Assert the TEXT is present, not the specific tag/markup — the brief pins the props
    // contract, not the placeholder implementation.
    expect(screen.getByText(/Roth IRA Conversion Basics/)).toBeInTheDocument();
    expect(document.body.textContent).toContain('Sample body for preview.');
  });

  it('re-rendering with different markdown updates the visible text — no stale prior content', () => {
    const { rerender } = render(<MarkdownPreview markdown="First version" />);
    expect(screen.getByText('First version')).toBeInTheDocument();

    rerender(<MarkdownPreview markdown="Second version" />);
    expect(screen.queryByText('First version')).not.toBeInTheDocument();
    expect(screen.getByText('Second version')).toBeInTheDocument();
  });

  it('renders an empty markdown string without throwing', () => {
    expect(() => render(<MarkdownPreview markdown="" />)).not.toThrow();
  });

  // phase-8 task-03: the full tag mapping (pre/code, blockquote, hr, img, table, variant,
  // headingOffset) lives in the client twin's own test suite; this is a light mapping-drift
  // smoke check on the admin copy.
  it('renders fenced code as <pre><code> (the full tag mapping is live in the admin twin)', () => {
    const { container } = render(<MarkdownPreview markdown={'```\nconst x = 1;\n```'} />);

    expect(container.querySelector('pre code')).toHaveTextContent('const x = 1;');
  });
});
