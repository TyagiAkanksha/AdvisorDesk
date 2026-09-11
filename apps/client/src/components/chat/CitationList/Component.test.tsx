// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { CitationList } from '.';

// phase-8 task-12 (DESIGN.md §B4): sources are a titled list of real links, numbered in server
// order — a reader no longer has to hover a `[n]` chip to learn what it cites.
const citations = [
  { content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' },
  { content_id: 'c-2', title: 'Traditional IRA Basics', slug: 'traditional-ira-basics' },
];

describe('CitationList', () => {
  it('renders a Sources region with one numbered, titled link per citation in order', () => {
    render(<CitationList citations={citations} />);

    expect(screen.getByRole('region', { name: 'Sources' })).toBeInTheDocument();
    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      '[1] Roth IRA Basics',
      '[2] Traditional IRA Basics',
    ]);
    expect(links[0]).toHaveAttribute('href', '/content/roth-ira-basics');
    expect(links[1]).toHaveAttribute('href', '/content/traditional-ira-basics');
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  // fix round 1 (I-1): the browser's own decimal `<ol>` marker was doubling up with the `[n]`
  // prefix already in each link's text ("1. [1] Homeowners Liability Basics").
  it('suppresses the browser default list marker so the [n] prefix is not doubled', () => {
    render(<CitationList citations={citations} />);

    expect(screen.getByRole('list')).toHaveStyle({ listStyleType: 'none' });
  });

  it('renders nothing for an empty citations array', () => {
    const { container } = render(<CitationList citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
