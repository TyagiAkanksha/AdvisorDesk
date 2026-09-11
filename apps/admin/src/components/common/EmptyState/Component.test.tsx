// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { EmptyState } from '.';

describe('EmptyState', () => {
  it('renders title and description inside the status region and the action OUTSIDE it', () => {
    render(
      <EmptyState
        title="No content yet"
        description="Create your first article to get started."
        action={<button type="button">Create your first article</button>}
      />,
    );

    const status = screen.getByRole('status');
    expect(within(status).getByText('No content yet')).toBeInTheDocument();
    expect(
      within(status).getByText('Create your first article to get started.'),
    ).toBeInTheDocument();
    // t23 M5: interactive controls must not live inside a polite live region.
    expect(within(status).queryByRole('button')).toBeNull();
    expect(screen.getByRole('button', { name: 'Create your first article' })).toBeInTheDocument();
  });

  it('renders the requested icon (hidden from assistive tech) instead of the default', () => {
    const { container } = render(<EmptyState message="Nothing here" icon="SmartToy" />);

    const svg = container.querySelector('svg[data-testid="SmartToyIcon"]');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the single-message form unchanged', () => {
    render(<EmptyState message="No content found." />);

    expect(screen.getByRole('status')).toHaveTextContent('No content found.');
  });
});
