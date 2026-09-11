// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { TagTable } from '.';

describe('TagTable', () => {
  it('renders a linked row per tag with its count', () => {
    render(
      <TagTable
        rows={[
          { tag: 'tax-planning', count: 2 },
          { tag: 'retirement', count: 1 },
        ]}
      />,
    );

    const table = screen.getByRole('table', { name: 'Content by tag' });
    expect(within(table).getByRole('link', { name: 'tax-planning' })).toHaveAttribute(
      'href',
      '/content?tag=tax-planning',
    );
    expect(within(table).getByRole('cell', { name: '2' })).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'retirement' })).toBeInTheDocument();
  });

  it('URL-encodes tag names in the link', () => {
    render(<TagTable rows={[{ tag: 'a&b', count: 1 }]} />);

    expect(screen.getByRole('link', { name: 'a&b' })).toHaveAttribute('href', '/content?tag=a%26b');
  });

  it('renders a quiet empty state for no rows', () => {
    render(<TagTable rows={[]} />);

    expect(screen.getByRole('status')).toHaveTextContent('No tags yet.');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
