// @vitest-environment jsdom
import { screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { stubMatchMedia } from '@/testing/matchMedia';

import { draftFixture, mockEditorFetch as mockFetch, renderEdit } from './testing/renderEditor';

// task-20 (DESIGN.md §5 C5): below the `md` breakpoint the form and the live preview no longer
// share a two-column row — a header Preview/Edit toggle swaps one for the other. Copied from
// Component.test.tsx: the `next/navigation` mock block, `draftFixture` (with task-20's new
// body — a bare `# Title` strips to nothing, which this suite doesn't want to assert against),
// `mockFetch`, and `renderEdit`.
const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

describe('ContentEditorScreen below the md breakpoint', () => {
  let restore: (() => void) | null = null;

  beforeEach(() => {
    restore = stubMatchMedia(true);
  });

  afterEach(() => {
    restore?.();
    restore = null;
    vi.restoreAllMocks();
  });

  it('a header Preview button swaps the form for the preview, and Edit swaps back', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    await screen.findByRole('textbox', { name: /title/i });
    expect(screen.queryByRole('region', { name: 'Preview' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Preview' }));
    expect(screen.getByRole('region', { name: 'Preview' })).toHaveTextContent('Body.');
    expect(screen.queryByRole('textbox', { name: /title/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('textbox', { name: /title/i })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Preview' })).not.toBeInTheDocument();
  });
});
