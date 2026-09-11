// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { EmptyState } from '.';

// phase-8 task-06: empty states can name their icon and offer a way out (DESIGN.md §B2).
describe('EmptyState', () => {
  it('renders the message in a polite live region with no link by default', () => {
    render(<EmptyState message="No published content yet." />);

    expect(screen.getByRole('status')).toHaveTextContent('No published content yet.');
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('renders an action link when given, outside the status region', () => {
    render(
      <EmptyState
        message="No articles tagged 'x'."
        icon="Search"
        action={{ label: 'Show all', href: '/' }}
      />,
    );

    expect(screen.getByRole('link', { name: 'Show all' })).toHaveAttribute('href', '/');
    // t23 M5: interactive controls must not live inside a polite live region.
    expect(within(screen.getByRole('status')).queryByRole('link')).toBeNull();
  });
});
