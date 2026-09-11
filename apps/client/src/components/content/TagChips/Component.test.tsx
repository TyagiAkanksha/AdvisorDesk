// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { TagChips } from '.';

// p8 final (I-2, DESIGN.md §B3): asserts the chips are real client-side links (`common/Link`,
// same pattern as `ArticleCard`/`TagFilter`) with correctly-encoded `href`s — not the plain `<a>`
// full-navigation chips this leaf replaces.
//
// p8 t24: moved from `content/ArticleScreen/components/TagChips` to `content/TagChips` — shared
// by both `ArticleScreen` and `ArticleCard` now, not article-screen-private. Cases unchanged.
describe('TagChips', () => {
  it('renders a link chip per tag pointing at the filtered list', () => {
    render(<TagChips tags={['retirement', 'tax-planning']} />);

    expect(screen.getByRole('link', { name: 'retirement' })).toHaveAttribute(
      'href',
      '/?tag=retirement',
    );
    expect(screen.getByRole('link', { name: 'tax-planning' })).toHaveAttribute(
      'href',
      '/?tag=tax-planning',
    );
  });

  it('encodes a tag with characters unsafe in a query string', () => {
    render(<TagChips tags={['tax planning']} />);

    expect(screen.getByRole('link', { name: 'tax planning' })).toHaveAttribute(
      'href',
      '/?tag=tax%20planning',
    );
  });

  it('renders nothing when there are no tags', () => {
    render(<TagChips tags={[]} />);

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
