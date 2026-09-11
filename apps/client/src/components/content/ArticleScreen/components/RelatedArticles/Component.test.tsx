// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { RelatedArticles } from '.';

const items = [
  { slug: 'a', title: 'Article A', tags: ['retirement'], published_at: '2026-01-01T00:00:00Z' },
  { slug: 'b', title: 'Article B', tags: ['tax'], published_at: '2026-02-01T00:00:00Z' },
];

describe('RelatedArticles', () => {
  it('renders a labelled section with a card link per item', () => {
    render(<RelatedArticles items={items} />);

    const section = screen.getByRole('region', { name: 'Related articles' });
    expect(section).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Article A' })).toHaveAttribute('href', '/content/a');
    expect(screen.getByRole('link', { name: 'Article B' })).toHaveAttribute('href', '/content/b');
  });

  it('renders nothing for an empty list', () => {
    const { container } = render(<RelatedArticles items={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
