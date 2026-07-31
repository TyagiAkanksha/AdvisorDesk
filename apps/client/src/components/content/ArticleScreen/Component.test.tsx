// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it } from 'vitest';

import type { PublicContentDetail } from '@/types';

import { ArticleScreen } from '.';

// task-04 (phase-3), PRD §2.2 (detail page renders markdown) + §8. `ArticleScreen` is a DUMB
// synchronous component taking the already-fetched `article` as a prop (fetching is the thin
// async page's job, out of scope/not testable in jsdom, per this task's brief).
//
// §8 pin ("Seed data"): the PRD's only "disclaimer" text is the seed pipeline's required footer
// line on every seeded article — *"Sample content for demonstration purposes — not financial
// advice."* (advisordesk-prd.md §8, verbatim, quoted in the doc). That seed pipeline doesn't
// exist until phase-4 (PRD §10: "seed articles ... authored and loaded" is a Phase 4 deliverable),
// so `ArticleScreen` cannot be relying on the line being baked into `body_md` — task-04's own
// acceptance criterion ("Disclaimer footer visible on every article (§8)") only holds today if
// the screen renders it itself, unconditionally, as a static footer. This file pins that design:
// the fixture's `body_md` deliberately does NOT contain the line, so the assertion only passes
// if `ArticleScreen` supplies it independently of article content.
//
// apps/client/vitest.config.ts has no `setupFiles` registering RTL's `cleanup()` (unlike
// apps/admin's — see apps/admin/vitest.setup.ts), so this file registers its own to keep its
// renders from leaking DOM state into each other.
afterEach(() => {
  cleanup();
});

const article: PublicContentDetail = {
  slug: 'roth-ira-conversion-basics',
  title: 'Roth IRA Conversion Basics',
  tags: ['retirement', 'tax-planning'],
  published_at: '2026-01-15T00:00:00Z',
  body_md:
    '## Key Considerations\n\n- Evaluate your current tax bracket\n- Consider a multi-year conversion plan\n\nConsult a professional before proceeding.',
};

describe('ArticleScreen', () => {
  it('renders the title as the top-level heading', () => {
    render(<ArticleScreen article={article} />);

    expect(screen.getByRole('heading', { level: 1, name: article.title })).toBeInTheDocument();
  });

  it('renders the markdown body through the Markdown component — real structure, not raw text or a mock', () => {
    render(<ArticleScreen article={article} />);

    // `body_md`'s `## Key Considerations` must come out as a genuine level-2 heading — proof
    // it went through the shared Markdown renderer (never our own component mocked out, per
    // FRONTEND-CONVENTIONS.md §7), not dumped as a raw `<pre>`/text blob.
    expect(
      screen.getByRole('heading', { level: 2, name: 'Key Considerations' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Evaluate your current tax bracket')).toBeInTheDocument();
    expect(screen.getByText('Consider a multi-year conversion plan')).toBeInTheDocument();
    // The raw markdown syntax must not leak through as literal, unparsed text.
    expect(screen.queryByText(/##\s*Key Considerations/)).not.toBeInTheDocument();
  });

  it('renders each tag as a visible chip', () => {
    render(<ArticleScreen article={article} />);

    for (const tag of article.tags) {
      expect(screen.getByText(tag)).toBeInTheDocument();
    }
  });

  it('renders the published date visibly', () => {
    const { container } = render(<ArticleScreen article={article} />);

    // Not pinning an exact format — just that the fixture's `published_at` year is visible
    // somewhere on the page (matches the precedent in
    // apps/admin/src/components/content/ContentListScreen/Component.test.tsx).
    expect(container.textContent).toContain('2026');
  });

  it('renders the §8 disclaimer footer text on every article', () => {
    render(<ArticleScreen article={article} />);

    // Verbatim PRD §8 wording, tolerant of the exact dash glyph: "Sample content for
    // demonstration purposes — not financial advice."
    expect(
      screen.getByText(/Sample content for demonstration purposes.*not financial advice/i),
    ).toBeInTheDocument();
  });
});
