// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Pagination } from '.';

// fix round 1, F1 (C1: pagination UI was entirely missing). Direct props-driven test of the
// primitive, mirroring the existing common/Icon precedent — network/screen wiring is covered
// separately by ContentListScreen/pagination.test.tsx.
describe('Pagination', () => {
  it('shows a "Showing X–Y of Z" affordance computed from page/pageSize/total', () => {
    render(<Pagination page={1} pageSize={20} total={45} onPageChange={vi.fn()} />);

    expect(screen.getByText('Showing 1–20 of 45')).toBeInTheDocument();
  });

  it('clamps the shown range to total on a partial last page', () => {
    render(<Pagination page={3} pageSize={20} total={45} onPageChange={vi.fn()} />);

    expect(screen.getByText('Showing 41–45 of 45')).toBeInTheDocument();
  });

  it('renders nothing at all when total is zero (fix round, F7: pager suppressed entirely)', () => {
    const { container } = render(
      <Pagination page={1} pageSize={20} total={0} onPageChange={vi.fn()} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('shows "No items" (not a nonsensical range) but keeps the pager mounted on a stranded page (fix round, F7 / t05 M10)', () => {
    // The exact M10 repro: page 2, pageSize 20, total 20 (a stranding refetch after the sole
    // page-2 row was deleted) previously rendered "Showing 21–20 of 20".
    render(<Pagination page={2} pageSize={20} total={20} onPageChange={vi.fn()} />);

    expect(screen.getByText('No items')).toBeInTheDocument();
    expect(screen.queryByText(/showing/i)).not.toBeInTheDocument();
    // The escape hatch stays: the pager control itself is still mounted, offering a way back.
    expect(screen.getByRole('button', { name: 'Go to previous page' })).toBeInTheDocument();
  });

  it('calls onPageChange with the clicked page number', async () => {
    const onPageChange = vi.fn();
    const user = userEvent.setup();
    render(<Pagination page={1} pageSize={20} total={45} onPageChange={onPageChange} />);

    await user.click(screen.getByRole('button', { name: 'Go to page 2' }));

    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('calls onPageChange when advancing via the next-page control', async () => {
    const onPageChange = vi.fn();
    const user = userEvent.setup();
    render(<Pagination page={1} pageSize={20} total={45} onPageChange={onPageChange} />);

    await user.click(screen.getByRole('button', { name: 'Go to next page' }));

    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});
