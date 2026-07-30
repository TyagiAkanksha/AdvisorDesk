// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { Icon } from '.';

describe('Icon', () => {
  it('exposes an accessible name via role=img when label is provided', () => {
    render(<Icon name="Search" label="Search" />);

    expect(screen.getByRole('img', { name: 'Search' })).toBeInTheDocument();
  });

  it('hides the glyph from assistive tech when label is omitted', () => {
    const { container } = render(<Icon name="Search" />);
    const svg = container.querySelector('svg');

    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).not.toHaveAttribute('aria-label');
  });
});
