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
    render(<ArticleScreen article={article} related={[]} />);

    expect(screen.getByRole('heading', { level: 1, name: article.title })).toBeInTheDocument();
  });

  it('renders the markdown body through the Markdown component — real structure, not raw text or a mock', () => {
    render(<ArticleScreen article={article} related={[]} />);

    // `body_md`'s `## Key Considerations` must come out as a genuine heading — proof it went
    // through the shared Markdown renderer (never our own component mocked out, per
    // FRONTEND-CONVENTIONS.md §7), not dumped as a raw `<pre>`/text blob. phase-8 task-03:
    // `ArticleScreen` now passes `headingOffset={1}` unconditionally (the screen owns the page
    // h1), so a source `##` lands one level deeper, at h3 — see that task's `Component.tsx`.
    expect(
      screen.getByRole('heading', { level: 3, name: 'Key Considerations' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Evaluate your current tax bracket')).toBeInTheDocument();
    expect(screen.getByText('Consider a multi-year conversion plan')).toBeInTheDocument();
    // The raw markdown syntax must not leak through as literal, unparsed text.
    expect(screen.queryByText(/##\s*Key Considerations/)).not.toBeInTheDocument();
  });

  it('renders each tag as a visible chip', () => {
    render(<ArticleScreen article={article} related={[]} />);

    for (const tag of article.tags) {
      expect(screen.getByText(tag)).toBeInTheDocument();
    }
  });

  it('renders the published date visibly', () => {
    const { container } = render(<ArticleScreen article={article} related={[]} />);

    // Not pinning an exact format — just that the fixture's `published_at` year is visible
    // somewhere on the page (matches the precedent in
    // apps/admin/src/components/content/ContentListScreen/Component.test.tsx).
    expect(container.textContent).toContain('2026');
  });

  it('renders the §8 disclaimer footer text on every article', () => {
    render(<ArticleScreen article={article} related={[]} />);

    // Verbatim PRD §8 wording, tolerant of the exact dash glyph: "Sample content for
    // demonstration purposes — not financial advice."
    expect(
      screen.getByText(/Sample content for demonstration purposes.*not financial advice/i),
    ).toBeInTheDocument();
  });

  // phase-8 task-03 (DESIGN.md §A2): every CMS body starts with `# <title>` (seed convention),
  // duplicating the title `ArticleScreen` already renders. RED until the implementer strips the
  // leading heading and passes `headingOffset={1}` so `##` sections land at h3 under the one h1.
  it('renders the title exactly once as the only h1 even though body_md starts with `# <title>`', () => {
    render(
      <ArticleScreen
        article={{
          title: 'Medicare Basics',
          slug: 'medicare-basics',
          tags: ['insurance'],
          published_at: '2026-08-09T00:00:00Z',
          body_md: '# Medicare Basics\n\n## Parts of Medicare\n\nBody.',
        }}
        related={[]}
      />,
    );

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'Medicare Basics' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 3, name: 'Parts of Medicare' }),
    ).toBeInTheDocument();
  });

  it('renders the back link, tag links to the filter, the disclaimer as an info alert, and the chat CTA', () => {
    render(<ArticleScreen article={article} related={[]} />);

    expect(screen.getByRole('link', { name: /Back to articles/ })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: article.tags[0]! })).toHaveAttribute(
      'href',
      `/?tag=${encodeURIComponent(article.tags[0]!)}`,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('not financial advice');
    expect(screen.getByRole('link', { name: 'Ask a question about this topic' })).toHaveAttribute(
      'href',
      '/chat',
    );
  });

  it('renders related articles when given and omits the section when empty', () => {
    const related = [
      { slug: 'r', title: 'Related One', tags: ['x'], published_at: '2026-01-01T00:00:00Z' },
    ];
    const { unmount } = render(<ArticleScreen article={article} related={related} />);
    expect(screen.getByRole('region', { name: 'Related articles' })).toBeInTheDocument();
    unmount();

    render(<ArticleScreen article={article} related={[]} />);
    expect(screen.queryByRole('region', { name: 'Related articles' })).toBeNull();
  });
});
