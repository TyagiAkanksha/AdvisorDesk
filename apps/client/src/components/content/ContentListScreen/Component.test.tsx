// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it } from 'vitest';

import type { PublicContentSummary } from '@/types';

import { ContentListScreen } from '.';

// task-04 (phase-3), PRD §2.2 ("As a client, I can browse published content"). Per the
// standard RSC split pinned by this task's brief, `ContentListScreen` is a DUMB synchronous
// component: it takes already-fetched `items` as a prop (fetching happens in the thin async
// page via `publicApi`, out of scope here — not testable in jsdom). Each item links to
// `/content/{slug}` — phase-4's citation links target exactly this path shape, so the href is
// pinned literally, not just "is a link".
//
// `import type` here is erased at transpile time (this repo's tsconfig has
// `isolatedModules: true`), so this file's RED failure is driven solely by the missing
// `ContentListScreen` barrel/component, not by `@/types` not yet exporting this alias.
//
// apps/client/vitest.config.ts has no `setupFiles` registering RTL's `cleanup()` (unlike
// apps/admin's — see apps/admin/vitest.setup.ts), so this file registers its own to keep its
// two renders from leaking DOM state into each other.
afterEach(() => {
  cleanup();
});

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

describe('ContentListScreen', () => {
  it('renders a card per item with visible title, tags, and a link to /content/{slug}', () => {
    render(<ContentListScreen items={items} />);

    for (const item of items) {
      expect(screen.getByText(item.title)).toBeInTheDocument();
      for (const tag of item.tags) {
        expect(screen.getByText(tag)).toBeInTheDocument();
      }

      const link = screen.getByRole('link', { name: new RegExp(item.title) });
      expect(link).toHaveAttribute('href', `/content/${item.slug}`);
    }
  });

  // p8 final I-1: theme h5/h6 (16px/14px) sit under body text under the new type scale — the
  // card title must use a variant that still reads larger than the card body (h4, 18px).
  it('renders the card title heading at the h4 variant', () => {
    render(<ContentListScreen items={items} />);

    const heading = screen.getByRole('heading', { level: 2, name: new RegExp(items[0]!.title) });
    expect(heading).toHaveClass('MuiTypography-h4');
  });

  it('shows a visible, non-empty empty-state message for an empty items list', () => {
    render(<ContentListScreen items={[]} />);

    // FRONTEND-CONVENTIONS.md §9: empty state is an explicit, visible component — never a
    // silent blank region. `role="status"` matches the existing EmptyState precedent
    // (apps/admin/src/components/common/EmptyState/Component.tsx).
    const status = screen.getByRole('status');
    expect(status.textContent?.trim().length ?? 0).toBeGreaterThan(0);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
