// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ArticleSkeleton } from '.';

describe('ArticleSkeleton', () => {
  it('announces itself as a loading status region', () => {
    render(<ArticleSkeleton />);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });
});
