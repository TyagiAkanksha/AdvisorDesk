// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Link } from '.';

// task-04 fix round 1 (F3). `isInternalHref` used to treat ANY `/`-prefixed href as internal,
// including a protocol-relative href like `//evil.example.com` (which also starts with `/`) —
// handing it to `next/link` would resolve it relative to the current origin instead of
// navigating to the external host it actually names. `isInternalHref` now also requires the
// href NOT start with `//`.
//
// `next/link` is mocked here (not left real) because a real `next/link` and a plain MUI `<a>`
// render an indistinguishable `<a href=...>` in jsdom — the only way to assert WHICH path a
// given href took is to swap in a recognizable stand-in for `next/link` and check for its marker.
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children?: ReactNode }) => (
    <a href={href} data-next-link="true" {...rest}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
});

describe('Link', () => {
  it('routes an internal `/`-prefixed href through next/link', () => {
    render(<Link href="/content/some-slug">Internal</Link>);

    const link = screen.getByRole('link', { name: 'Internal' });
    expect(link).toHaveAttribute('href', '/content/some-slug');
    expect(link).toHaveAttribute('data-next-link', 'true');
  });

  it('renders a protocol-relative href as a plain anchor, not through next/link', () => {
    render(<Link href="//evil.example.com/path">External</Link>);

    const link = screen.getByRole('link', { name: 'External' });
    expect(link).toHaveAttribute('href', '//evil.example.com/path');
    expect(link).not.toHaveAttribute('data-next-link');
  });

  it('renders a normal external href as a plain anchor, not through next/link', () => {
    render(<Link href="https://example.com/resource">Resource</Link>);

    const link = screen.getByRole('link', { name: 'Resource' });
    expect(link).toHaveAttribute('href', 'https://example.com/resource');
    expect(link).not.toHaveAttribute('data-next-link');
  });
});
