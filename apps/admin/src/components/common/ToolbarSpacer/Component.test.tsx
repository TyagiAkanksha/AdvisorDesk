// @vitest-environment jsdom
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ToolbarSpacer } from '.';

// task-04 review round 1 (I3): jsdom can't assert pixel offsets or paint
// order, so this only pins what it CAN see — that the spacer renders as a
// real DOM element. The actual "content lands below the fixed AppBar"
// visual result is a checkpoint for the owner to confirm in a real browser
// (see fix-round-1 report).
describe('ToolbarSpacer', () => {
  it('renders an element', () => {
    const { container } = render(<ToolbarSpacer />);

    expect(container.firstChild).toBeInTheDocument();
  });
});
