// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Button } from '.';

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
