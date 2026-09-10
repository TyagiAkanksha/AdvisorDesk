// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Button } from '.';

// p8 final: `next/link` mocked with a recognizable marker (same idiom as common/Link's
// Component.test.tsx) so the protocol-relative-href test below can prove the render did NOT
// route through next/link — a real next/link and a plain MUI `<a>` are otherwise
// indistinguishable in jsdom.
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children?: ReactNode }) => (
    <a href={href} data-next-link="true" {...rest}>
      {children}
    </a>
  ),
}));

// phase-8 task-06: the client Button gains the admin Button's href mode (DESIGN.md §A3).
describe('Button', () => {
  it('renders an internal href as a link with the href attribute', () => {
    render(<Button href="/chat">Ask a question</Button>);

    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute('href', '/chat');
  });

  it('renders an external href as a plain link', () => {
    render(<Button href="https://example.com">Docs</Button>);

    expect(screen.getByRole('link', { name: 'Docs' })).toHaveAttribute(
      'href',
      'https://example.com',
    );
  });

  // p8 final I-2 (Button host guard): `isInternalHref` used to treat any `/`-prefixed href as
  // internal, including a protocol-relative `//evil.example` href — matches common/Link's fix.
  it('renders a protocol-relative href as a plain anchor, not through next/link', () => {
    render(<Button href="//evil.example">External</Button>);

    const link = screen.getByRole('link', { name: 'External' });
    expect(link).toHaveAttribute('href', '//evil.example');
    expect(link).not.toHaveAttribute('data-next-link');
  });

  it('routes a `/`-prefixed href through next/link', () => {
    render(<Button href="/content">Content</Button>);

    const link = screen.getByRole('link', { name: 'Content' });
    expect(link).toHaveAttribute('href', '/content');
    expect(link).toHaveAttribute('data-next-link', 'true');
  });

  it('still renders a button that fires onClick when no href is given', async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} color="error" startIcon={<span data-testid="icon" />}>
        Delete
      </Button>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });
});
