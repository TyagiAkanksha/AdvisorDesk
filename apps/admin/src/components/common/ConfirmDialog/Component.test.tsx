// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';

import { ConfirmDialog } from '.';

// phase-8 task-04: destructive confirmations must LOOK destructive (DESIGN.md §2: error colour =
// destructive; gold is never used for delete).
describe('ConfirmDialog', () => {
  it('renders the confirm button in the error colour when destructive', () => {
    render(
      <ConfirmDialog
        open
        title="Delete article?"
        body="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        isPending={false}
        destructive
      />,
    );

    // MUI 9 emits separate `contained` + `colorError` classes (no combined `containedError`).
    expect(screen.getByRole('button', { name: 'Delete' }).className).toContain(
      'MuiButton-colorError',
    );
  });

  it('keeps the primary colour when not destructive', () => {
    render(
      <ConfirmDialog
        open
        title="Publish?"
        body="Readers will see it."
        confirmLabel="Publish"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        isPending={false}
      />,
    );

    expect(screen.getByRole('button', { name: 'Publish' }).className).toContain(
      'MuiButton-colorPrimary',
    );
  });
});
