// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { formatDate } from '@/lib/format';
import type { ContentDto } from '@/types/api/content';

import { RecentContent } from '.';

const itemA: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics',
  created_at: '2026-01-01T12:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-03-15T12:00:00Z',
  updated_by: null,
};

const itemB: ContentDto = {
  author_id: null,
  body_md: '# Estate Planning 101',
  created_at: '2025-12-01T12:00:00Z',
  id: '22222222-2222-2222-2222-222222222222',
  published_at: '2025-12-05T12:00:00Z',
  slug: 'estate-planning-101',
  status: 'published',
  tags: ['estate-planning', 'retirement'],
  title: 'Estate Planning 101',
  updated_at: '2025-12-20T12:00:00Z',
  updated_by: null,
};

describe('RecentContent', () => {
  it('renders title links, status chips and formatted dates', () => {
    render(<RecentContent items={[itemA, itemB]} />);

    const table = screen.getByRole('table', { name: 'Recent content' });
    const rowA = within(table).getByRole('row', { name: new RegExp(itemA.title) });
    expect(within(rowA).getByRole('link', { name: itemA.title })).toHaveAttribute(
      'href',
      `/content/${itemA.id}`,
    );
    expect(within(rowA).getByText('Draft')).toBeInTheDocument();
    expect(within(rowA).getByText(formatDate(itemA.updated_at))).toBeInTheDocument();
    const rowB = within(table).getByRole('row', { name: new RegExp(itemB.title) });
    expect(within(rowB).getByText('Published')).toBeInTheDocument();
  });

  it('renders the empty message for no items', () => {
    render(<RecentContent items={[]} />);

    expect(screen.getByRole('status')).toHaveTextContent('No content yet.');
  });
});
