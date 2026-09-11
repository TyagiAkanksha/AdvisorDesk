// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';

import { SiteHeader } from '.';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

describe('SiteHeader', () => {
  it('renders a banner with the wordmark linking home and the primary navigation', () => {
    render(<SiteHeader />);

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AdvisorDesk home' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
  });

  it('lets the wordmark and nav wrap instead of colliding on very narrow screens', () => {
    render(<SiteHeader />);
    const toolbar = screen.getByRole('banner').querySelector('.MuiToolbar-root');
    expect(toolbar).toHaveStyle({ flexWrap: 'wrap' });
  });
});
