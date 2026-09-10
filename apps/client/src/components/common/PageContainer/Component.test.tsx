// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { PageContainer } from '.';

// phase-8 task-06: reading-width pages (article, chat) use 'md'; lists keep 'lg' (DESIGN.md §B3/§B4).
describe('PageContainer', () => {
  it('renders a main landmark at lg width by default', () => {
    render(<PageContainer>content</PageContainer>);

    expect(screen.getByRole('main').className).toContain('MuiContainer-maxWidthLg');
  });

  it('accepts a narrower maxWidth', () => {
    render(<PageContainer maxWidth="md">content</PageContainer>);

    expect(screen.getByRole('main').className).toContain('MuiContainer-maxWidthMd');
  });
});
