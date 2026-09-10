// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ArticleCard } from '.';

const item = {
  slug: 'roth-ira-conversion-basics',
  title: 'Roth IRA Conversion Basics',
  tags: ['retirement', 'tax-planning'],
  published_at: '2026-01-15T00:00:00Z',
};

describe('ArticleCard', () => {
  it('renders the title as an h2 link to the article, the published date, and tag links to the filter', () => {
    render(<ArticleCard item={item} />);

    const title = screen.getByRole('heading', { level: 2, name: 'Roth IRA Conversion Basics' });
    expect(title).toHaveClass('MuiTypography-h4');
    expect(screen.getByRole('link', { name: 'Roth IRA Conversion Basics' })).toHaveAttribute(
      'href',
      '/content/roth-ira-conversion-basics',
    );
    expect(screen.getByText('Jan 15, 2026')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'retirement' })).toHaveAttribute(
      'href',
      '/?tag=retirement',
    );
    expect(screen.getByRole('link', { name: 'tax-planning' })).toHaveAttribute(
      'href',
      '/?tag=tax-planning',
    );
  });
});
