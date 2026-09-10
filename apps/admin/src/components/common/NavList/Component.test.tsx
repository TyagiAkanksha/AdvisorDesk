// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { NavList } from '.';

// phase-8 task-04: the shell needs an active-item state and a way to close a temporary drawer
// after navigation (DESIGN.md §C1).
describe('NavList', () => {
  const items = [
    { label: 'Dashboard', href: '/', selected: false },
    { label: 'Content', href: '/content', selected: true },
  ];

  it('marks the selected item as the current page', () => {
    render(<NavList items={items} />);

    expect(screen.getByRole('link', { name: 'Content' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: 'Content' }).className).toContain('Mui-selected');
  });

  it('calls onNavigate when any item is clicked', async () => {
    const onNavigate = vi.fn();
    render(<NavList items={items} onNavigate={onNavigate} />);

    await userEvent.click(screen.getByRole('link', { name: 'Dashboard' }));

    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
