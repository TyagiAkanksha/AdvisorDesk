// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ThinkingIndicator } from '.';

describe('ThinkingIndicator', () => {
  it('announces Thinking… in a polite status region with a progress indicator', () => {
    render(<ThinkingIndicator />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Thinking…');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });
});
