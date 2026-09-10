// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ChatSkeleton } from '.';

describe('ChatSkeleton', () => {
  it('announces itself as a loading status region', () => {
    render(<ChatSkeleton />);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });
});
