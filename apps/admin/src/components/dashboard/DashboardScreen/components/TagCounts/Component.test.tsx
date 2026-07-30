// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { TagCounts } from '.';

// fix round 1, F3 (controller-resolved plan conflict): the brief's Goal calls for
// "status/tag counts from GET /stats" — implement + pin the tag-count section. Direct
// props-driven test (mirrors common/Icon's precedent) — network wiring through
// DashboardScreen is exercised by the pinned Component.test.tsx's existing fixture, which
// already carries a `by_tag` payload.
describe('TagCounts', () => {
  it('renders each tag with its count from a by_tag fixture', () => {
    render(<TagCounts byTag={{ 'tax-planning': 2, retirement: 1 }} />);

    expect(screen.getByRole('heading', { name: 'tax-planning' })).toBeInTheDocument();
    expect(screen.getByText('2 items')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'retirement' })).toBeInTheDocument();
    expect(screen.getByText('1 item')).toBeInTheDocument();
  });

  it('renders a quiet empty affordance for an empty by_tag', () => {
    render(<TagCounts byTag={{}} />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent(/no tags yet/i);
  });
});
