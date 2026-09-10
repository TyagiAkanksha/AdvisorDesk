// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';

import { Drawer } from '.';

// phase-8 task-04: the nav drawer must be able to switch to MUI's temporary (modal) variant below
// the md breakpoint, and the agent panel to full width on phones (DESIGN.md §C1).
describe('Drawer', () => {
  it('renders a temporary drawer as a modal dialog when open, with its content reachable', () => {
    render(
      <Drawer variant="temporary" open onClose={vi.fn()}>
        <nav aria-label="Primary">links</nav>
      </Drawer>,
    );

    expect(screen.getByRole('presentation')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
  });

  it('keeps a closed temporary drawer mounted but hidden (keepMounted)', () => {
    render(
      <Drawer variant="temporary" open={false} onClose={vi.fn()}>
        <nav aria-label="Primary">links</nav>
      </Drawer>,
    );

    expect(screen.queryByRole('navigation', { name: 'Primary' })).toBeNull();
    // MUI's Slide applies `visibility: hidden` to the closed paper, and Testing Library computes an
    // EMPTY accessible name for visibility-hidden nodes even with `hidden: true` — so the mounted
    // nav is found by role alone and identified by its content.
    const hiddenNavs = screen.queryAllByRole('navigation', { hidden: true });
    expect(hiddenNavs).toHaveLength(1);
    expect(hiddenNavs[0]).toHaveTextContent('links');
  });

  it('applies a width override to the drawer paper', () => {
    // A px fixture: jsdom's getComputedStyle resolves viewport units to px, so `100vw` can never
    // round-trip through toHaveStyle; the override mechanism is what this pins.
    const { container } = render(
      <Drawer anchor="right" variant="persistent" open width={480}>
        <div>panel</div>
      </Drawer>,
    );

    expect(container.querySelector('.MuiDrawer-paper')).toHaveStyle({ width: '480px' });
  });
});
