// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { TagFilter } from '.';

describe('TagFilter', () => {
  it('renders All first, then one link per tag, inside a "Filter by tag" navigation', () => {
    render(<TagFilter tags={['insurance', 'retirement']} selectedTag={null} />);

    const nav = screen.getByRole('navigation', { name: 'Filter by tag' });
    const links = screen.getAllByRole('link');
    expect(nav).toBeInTheDocument();
    expect(links.map((link) => link.textContent)).toEqual(['All', 'insurance', 'retirement']);
    expect(links[0]).toHaveAttribute('href', '/');
    expect(links[1]).toHaveAttribute('href', '/?tag=insurance');
    expect(links[0]).toHaveAttribute('aria-current', 'page');
  });

  it('marks the selected tag current and All not current', () => {
    render(<TagFilter tags={['insurance', 'retirement']} selectedTag="retirement" />);

    expect(screen.getByRole('link', { name: 'retirement' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: 'All' })).not.toHaveAttribute('aria-current');
  });

  it('URL-encodes tags with special characters', () => {
    render(<TagFilter tags={['college savings']} selectedTag={null} />);

    expect(screen.getByRole('link', { name: 'college savings' })).toHaveAttribute(
      'href',
      '/?tag=college%20savings',
    );
  });
});
