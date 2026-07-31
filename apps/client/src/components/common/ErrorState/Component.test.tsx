// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it } from 'vitest';

import { ErrorState } from '.';

// task-04 fix round 1 (F4), docs/FRONTEND-CONVENTIONS.md §9: a friendly, visible error state —
// never a silent blank region, never a raw API error body. Mirrors the shape of
// apps/admin/src/components/common/ErrorState (`role="alert"`, optional `message` override).
afterEach(() => {
  cleanup();
});

describe('ErrorState', () => {
  it('renders a default friendly message in an assertive live region', () => {
    render(<ErrorState />);

    const alert = screen.getByRole('alert');
    expect(alert.textContent?.trim().length ?? 0).toBeGreaterThan(0);
  });

  it('renders a custom message when provided', () => {
    render(<ErrorState message="Could not load published content." />);

    expect(screen.getByText('Could not load published content.')).toBeInTheDocument();
  });
});
