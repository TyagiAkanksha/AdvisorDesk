// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { StatCard } from '.';

describe('StatCard', () => {
  it('renders the label and value as plain content without href', () => {
    render(<StatCard label="Draft" value={4} />);

    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('renders the whole card as one link when href is set', () => {
    render(<StatCard label="Published" value={27} href="/content?status=published" />);

    const link = screen.getByRole('link', { name: /Published/ });
    expect(link).toHaveAttribute('href', '/content?status=published');
    expect(link).toHaveTextContent('27');
  });
});
