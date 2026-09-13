// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { NO_WEAK_QUERIES_MESSAGE, WEAK_QUERIES_ARIA_LABEL } from '@/lib/copy';
import type { WeakQueryGroupDto } from '@/types/api/weakQueries';

import { WeakQueries } from '.';

// phase-9 task-19 (RED): `app/lib/copy`'s `NO_WEAK_QUERIES_MESSAGE`/`WEAK_QUERIES_ARIA_LABEL`,
// `@/types/api/weakQueries`'s `WeakQueryGroupDto`, and this leaf's own `Component`/`index.ts`
// none exist yet — this whole module fails to resolve, which IS the RED evidence.
const groupA: WeakQueryGroupDto = {
  normalized_question: 'does the firm cover crypto rsus',
  count: 2,
  kinds: ['negative_feedback', 'near_miss'],
  worst_top_similarity: 0.601,
  examples: [],
};

const groupB: WeakQueryGroupDto = {
  normalized_question: 'anything on qsbs',
  count: 1,
  kinds: ['refused'],
  worst_top_similarity: null,
  examples: [],
};

describe('WeakQueries', () => {
  it('renders a row per group with kind chips, the asked count and worst similarity', () => {
    render(<WeakQueries items={[groupA, groupB]} />);

    const table = screen.getByRole('table', { name: WEAK_QUERIES_ARIA_LABEL });
    const rowA = within(table).getByRole('row', {
      name: new RegExp(groupA.normalized_question),
    });
    expect(within(rowA).getByText('Thumbs down')).toBeInTheDocument();
    expect(within(rowA).getByText('Near miss')).toBeInTheDocument();
    expect(within(rowA).getByText('×2')).toBeInTheDocument();
    expect(within(rowA).getByText('0.60')).toBeInTheDocument();

    const rowB = within(table).getByRole('row', {
      name: new RegExp(groupB.normalized_question),
    });
    expect(within(rowB).getByText('Refused')).toBeInTheDocument();
    expect(within(rowB).getByText('×1')).toBeInTheDocument();
    expect(within(rowB).getByText('—')).toBeInTheDocument();
  });

  it('renders the empty message for no items', () => {
    render(<WeakQueries items={[]} />);

    expect(screen.getByRole('status')).toHaveTextContent(NO_WEAK_QUERIES_MESSAGE);
  });
});
