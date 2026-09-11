// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import type { PublicContentSummary } from '@/types';

import { ContentListScreen } from '.';

// phase-8 task-09 (DESIGN.md §B2) supersedes the phase-3 pins: the screen now owns the page
// header (h1 + description + the single gold CTA), the tag filter, a responsive grid of
// ArticleCards, and two distinct empty states.
const items: PublicContentSummary[] = [
  {
    slug: 'roth-ira-conversion-basics',
    title: 'Roth IRA Conversion Basics',
    tags: ['retirement', 'tax-planning'],
    published_at: '2026-01-15T00:00:00Z',
  },
  {
    slug: 'estate-planning-101',
    title: 'Estate Planning 101',
    tags: ['estate-planning'],
    published_at: '2025-12-01T00:00:00Z',
  },
];
const tags = ['estate-planning', 'retirement', 'tax-planning'];

describe('ContentListScreen', () => {
  it('renders the Articles h1, the description, and one CTA link to /chat', () => {
    render(<ContentListScreen items={items} tags={tags} selectedTag={null} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Articles' })).toBeInTheDocument();
    expect(screen.getByText(/Plain-English explainers/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute('href', '/chat');
  });

  it('renders the tag filter and one card per item, each linking to /content/{slug}', () => {
    render(<ContentListScreen items={items} tags={tags} selectedTag={null} />);

    expect(screen.getByRole('navigation', { name: 'Filter by tag' })).toBeInTheDocument();
    for (const item of items) {
      expect(screen.getByRole('link', { name: item.title })).toHaveAttribute(
        'href',
        `/content/${item.slug}`,
      );
    }
  });

  it('shows the no-content empty state with no article links and no tag filter when there is nothing at all', () => {
    render(<ContentListScreen items={[]} tags={[]} selectedTag={null} />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('No published content yet.');
    expect(within(status).queryByRole('link')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Show all' })).toBeNull();
    expect(screen.queryByRole('navigation', { name: 'Filter by tag' })).toBeNull();
  });

  it('shows the no-match empty state with a Show all link when a tag filters everything out', () => {
    render(<ContentListScreen items={[]} tags={tags} selectedTag="insurance" />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent("No articles tagged 'insurance'.");
    expect(screen.getByRole('link', { name: 'Show all' })).toHaveAttribute('href', '/');
    expect(within(status).queryByRole('link')).toBeNull();
    expect(screen.getByRole('navigation', { name: 'Filter by tag' })).toBeInTheDocument();
  });
});
