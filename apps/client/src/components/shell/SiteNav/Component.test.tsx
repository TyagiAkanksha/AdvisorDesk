// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SiteNav } from '.';

// phase-8 task-08: the active link follows the route. `next/navigation` is a framework module
// (not one of our components/hooks), so mocking it is within FRONTEND-CONVENTIONS §7.
const pathnameMock = vi.fn<() => string>();
vi.mock('next/navigation', () => ({ usePathname: () => pathnameMock() }));

describe('SiteNav', () => {
  beforeEach(() => {
    pathnameMock.mockReturnValue('/');
  });

  it('renders Articles → / and Ask a question → /chat inside a Primary navigation landmark', () => {
    render(<SiteNav />);

    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Articles' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute('href', '/chat');
  });

  it('marks Articles current on / and on article pages, and Ask a question current on /chat', () => {
    pathnameMock.mockReturnValue('/content/medicare-basics');
    const { unmount } = render(<SiteNav />);
    expect(screen.getByRole('link', { name: 'Articles' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Ask a question' })).not.toHaveAttribute(
      'aria-current',
    );
    unmount();

    pathnameMock.mockReturnValue('/chat');
    render(<SiteNav />);
    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: 'Articles' })).not.toHaveAttribute('aria-current');
  });
});
