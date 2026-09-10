// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { SiteFooter } from '.';

describe('SiteFooter', () => {
  it('renders a contentinfo landmark carrying the PRD §8 disclaimer', () => {
    render(<SiteFooter />);

    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'Sample content for demonstration purposes — not financial advice.',
    );
  });
});
