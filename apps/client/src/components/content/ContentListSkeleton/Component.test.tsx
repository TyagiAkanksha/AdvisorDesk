// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ContentListSkeleton } from '.';

describe('ContentListSkeleton', () => {
  it('announces itself as a loading status region', () => {
    render(<ContentListSkeleton />);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });
});
