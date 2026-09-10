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
  it('renders a Sources navigation with one numbered, titled link per citation in order', () => {
    render(<CitationList citations={citations} />);

    expect(screen.getByRole('navigation', { name: 'Sources' })).toBeInTheDocument();
    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      '[1] Roth IRA Basics',
      '[2] Traditional IRA Basics',
    ]);
    expect(links[0]).toHaveAttribute('href', '/content/roth-ira-basics');
    expect(links[1]).toHaveAttribute('href', '/content/traditional-ira-basics');
  });

  it('renders nothing for an empty citations array', () => {
    const { container } = render(<CitationList citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
