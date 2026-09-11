// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import NotFound from './not-found';

describe('not-found route', () => {
  it('renders a branded heading, a friendly message, and a way back', () => {
    render(<NotFound />);

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to dashboard' })).toHaveAttribute('href', '/');
  });

  it('keeps a main landmark of its own (it renders outside AppShell)', () => {
    render(<NotFound />);

    expect(screen.getByRole('main')).toBeInTheDocument();
  });
});
