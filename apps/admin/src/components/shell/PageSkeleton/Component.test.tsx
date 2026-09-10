// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { PageSkeleton } from '.';

describe('PageSkeleton', () => {
  it('announces itself as a loading status region', () => {
    render(<PageSkeleton />);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });
});
