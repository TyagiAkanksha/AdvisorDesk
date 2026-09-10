// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { PageHeader } from '.';

describe('PageHeader', () => {
  it('renders the title as the page h1 inside a banner-style header with description, meta, and actions', () => {
    render(
      <PageHeader
        title="Content"
        description="Everything published or in draft."
        meta={<span>Updated today</span>}
        actions={<button type="button">New content</button>}
      />,
    );

    expect(screen.getByRole('heading', { level: 1, name: 'Content' })).toBeInTheDocument();
    expect(screen.getByText('Everything published or in draft.')).toBeInTheDocument();
    expect(screen.getByText('Updated today')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New content' })).toBeInTheDocument();
  });

  it('renders only the title when nothing else is given', () => {
    render(<PageHeader title="Dashboard" />);

    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
