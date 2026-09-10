---
id: p8-t04
phase: phase-8-ui-polish
depends_on: [p8-t01]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 04 — Admin base primitives + extensions (apps/admin)

## Goal

Grow `apps/admin/src/components/common/` with the MUI wrappers sub-phase C's screens need
(Table family, Skeleton, Stack, Tooltip, Alert, Paper) and extend six existing primitives
(`TextField`, `ConfirmDialog`, `Button`, `NavList`, `ErrorState`, `Drawer`) with the props DESIGN.md
§A3 lists — behind the same "wrap, don't hand-roll" contract, with tests for every behaviour
that is more than a prop pass-through. No screen changes in this task.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §A3 (admin row of the table) and §2.
- `docs/FRONTEND-CONVENTIONS.md` §3, §4, §7, §9.
- `apps/admin/src/components/common/index.ts` (barrel — every new primitive is added here, alphabetically).
- `apps/admin/src/components/common/Box/{Component.tsx,interface.ts,index.ts}` — the pass-through
  template every new layout primitive copies.
- `apps/admin/src/components/common/{TextField,ConfirmDialog,Button,NavList,ErrorState,Drawer}/`
  — the six primitives being extended (read all three files of each).
- `apps/admin/src/components/common/Pagination/Component.test.tsx` — primitive test style
  (jsdom pragma, RTL, user-event, `from '.'`).
- `apps/admin/vitest.setup.ts` — cleanup is registered globally in the admin (no `afterEach(cleanup)` needed).

## Files

**Create (pass-throughs — `Component.tsx`, `interface.ts`, `index.ts` each; no tests needed, the
composites in task 05 and the screens in sub-phase C exercise them):**

| Folder | MUI import | Props type alias |
|---|---|---|
| `common/Stack/` | `import MuiStack from '@mui/material/Stack'` | `export type StackProps = MuiStackProps` (`import type { StackProps as MuiStackProps } from '@mui/material/Stack'`) |
| `common/Skeleton/` | `@mui/material/Skeleton` | `SkeletonProps = MuiSkeletonProps` |
| `common/Tooltip/` | `@mui/material/Tooltip` | `TooltipProps = MuiTooltipProps` |
| `common/Alert/` | `@mui/material/Alert` | `AlertProps = MuiAlertProps` |
| `common/Paper/` | `@mui/material/Paper` | `PaperProps = MuiPaperProps` |
| `common/Table/` | `@mui/material/Table` | `TableProps = MuiTableProps` |
| `common/TableContainer/` | `@mui/material/TableContainer` | `TableContainerProps = MuiTableContainerProps` |
| `common/TableHead/` | `@mui/material/TableHead` | `TableHeadProps = MuiTableHeadProps` |
| `common/TableBody/` | `@mui/material/TableBody` | `TableBodyProps = MuiTableBodyProps` |
| `common/TableRow/` | `@mui/material/TableRow` | `TableRowProps = MuiTableRowProps` |
| `common/TableCell/` | `@mui/material/TableCell` | `TableCellProps = MuiTableCellProps` |

Template (this is `Stack`; every row above is the same three files with the names swapped):

```tsx
// common/Stack/interface.ts
import type { StackProps as MuiStackProps } from '@mui/material/Stack';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — a generic layout
// primitive like Box, not a bespoke contract like Icon. phase-8 task-04.
export type StackProps = MuiStackProps;
```

```tsx
// common/Stack/Component.tsx
import MuiStack from '@mui/material/Stack';

import type { StackProps } from './interface';

export default function Component(props: StackProps) {
  return <MuiStack {...props} />;
}
```

```ts
// common/Stack/index.ts
export { default as Stack } from './Component';
export type { StackProps } from './interface';
```

**Create (tests for extended behaviour):**
- `common/TextField/Component.test.tsx`
- `common/ConfirmDialog/Component.test.tsx`
- `common/NavList/Component.test.tsx`
- `common/ErrorState/Component.test.tsx`
- `common/Drawer/Component.test.tsx`

**Modify**
- `common/index.ts` — export the 11 new primitives (+ prop types), alphabetically.
- `common/TextField/{interface.ts,Component.tsx}`
- `common/ConfirmDialog/{interface.ts,Component.tsx}`
- `common/Button/{interface.ts,Component.tsx}`
- `common/NavList/{interface.ts,Component.tsx}`
- `common/ErrorState/{interface.ts,Component.tsx}`
- `common/Drawer/{interface.ts,Component.tsx}`

## Interfaces

**Produces exactly (additions marked `// NEW`; everything not shown is unchanged):**

```ts
// common/TextField/interface.ts
import type { KeyboardEvent } from 'react';
export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  size?: 'small' | 'medium';
  fullWidth?: boolean;
  type?: 'text' | 'search';
  multiline?: boolean;
  minRows?: number;
  maxRows?: number;                                                   // NEW
  disabled?: boolean;
  required?: boolean;                                                 // NEW
  /** Validation state — pairs with `helperText` (phase-8 task-04, DESIGN.md §C5). */
  error?: boolean;                                                    // NEW
  helperText?: string;                                                // NEW
  onBlur?: () => void;                                                // NEW
  /** Raw key events, e.g. Enter-to-send in a chat composer. */
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void; // NEW
}
// Component.tsx passes each new prop straight to MuiTextField (`onBlur={onBlur}`, etc.).

// common/ConfirmDialog/interface.ts
export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  isPending: boolean;
  errorMessage?: string;
  /** Destructive confirmations (delete, revoke) render the confirm button in the error colour. */
  destructive?: boolean;                                              // NEW
}
// Component.tsx: <Button ... color={destructive ? 'error' : 'primary'} variant="contained">

// common/Button/interface.ts
export interface ButtonProps {
  children: ReactNode;
  href?: string;
  onClick?: MouseEventHandler<HTMLElement>;
  variant?: 'text' | 'outlined' | 'contained';
  color?: 'primary' | 'secondary' | 'inherit' | 'error';             // 'error' NEW
  size?: 'small' | 'medium' | 'large';
  disabled?: boolean;
  fullWidth?: boolean;
  type?: 'button' | 'submit' | 'reset';
  startIcon?: ReactNode;                                              // NEW
  'aria-expanded'?: boolean;
  'aria-haspopup'?: boolean | 'true' | 'false' | 'menu' | 'listbox' | 'tree' | 'grid' | 'dialog';
  'aria-controls'?: string;
  'aria-label'?: string;
}
// Component.tsx: `startIcon` is already inside `...rest` — no change beyond the interface.

// common/NavList/interface.ts
export interface NavListItem {
  label: string;
  href: string;
  icon?: IconProps['name'];
  /** The current route — rendered with MUI's `selected` state (phase-8 task-04, DESIGN.md §C1). */
  selected?: boolean;                                                 // NEW
}
export interface NavListProps {
  items: NavListItem[];
  /** Fired after any item is clicked — a temporary drawer uses it to close itself. */
  onNavigate?: () => void;                                            // NEW
}
// Component.tsx: <ListItemButton ... selected={item.selected} onClick={onNavigate}
//   aria-current={item.selected ? 'page' : undefined}>

// common/ErrorState/interface.ts
export interface ErrorStateProps {
  message?: string;
  /** Optional recovery action rendered as an outlined button under the message (e.g. "Retry"). */
  action?: { label: string; onClick: () => void };                    // NEW
}
// Component.tsx: message as before; when `action` is set, render
//   <Button variant="outlined" onClick={action.onClick} sx={{ mt: 2 }}>{action.label}</Button>
//   inside the same role="alert" Box (import Button from '../Button').

// common/Drawer/interface.ts
export interface DrawerProps {
  children: ReactNode;
  anchor?: 'left' | 'right';
  variant?: 'permanent' | 'persistent' | 'temporary';                 // 'temporary' NEW
  open?: boolean;
  onClose?: () => void;
  id?: string;
  /** Overrides the anchor's default width (240 left / 400 right), e.g. '100vw' on phones. */
  width?: number | string;                                            // NEW
}
// Component.tsx: `const width = widthProp ?? (anchor === 'left' ? NAV_DRAWER_WIDTH : PANEL_DRAWER_WIDTH)`;
// the `flexShrink` block stays permanent-only; `temporary` passes `ModalProps={{ keepMounted: true }}`
// (MUI's recommended mobile-drawer setting — better open performance on phones).
```

## Steps (TDD)

- [ ] **RED — test-author.** Five test files (jsdom pragma first line; imports from `'.'`):

  `TextField/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TextField } from '.';

// phase-8 task-04 (DESIGN.md §A3): validation and keyboard props the editor and composers need.
describe('TextField', () => {
  it('shows helper text and marks the input invalid when error is set', () => {
    render(
      <TextField label="Title" value="" onChange={vi.fn()} error helperText="Title is required" />,
    );

    expect(screen.getByRole('textbox', { name: /Title/ })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Title is required')).toBeInTheDocument();
  });

  it('fires onBlur when focus leaves and onKeyDown for key presses', async () => {
    const onBlur = vi.fn();
    const onKeyDown = vi.fn();
    render(
      <TextField label="Message" value="" onChange={vi.fn()} onBlur={onBlur} onKeyDown={onKeyDown} />,
    );

    const input = screen.getByRole('textbox', { name: 'Message' });
    await userEvent.click(input);
    await userEvent.keyboard('{Enter}');
    await userEvent.tab();

    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onKeyDown.mock.calls[0]?.[0]).toMatchObject({ key: 'Enter' });
    expect(onBlur).toHaveBeenCalledTimes(1);
  });

  it('renders a textarea capped by maxRows when multiline', () => {
    render(<TextField label="Body" value="" onChange={vi.fn()} multiline minRows={2} maxRows={6} />);

    expect(screen.getByRole('textbox', { name: 'Body' }).tagName).toBe('TEXTAREA');
  });

  it('marks the input required', () => {
    render(<TextField label="Title" value="" onChange={vi.fn()} required />);

    expect(screen.getByRole('textbox', { name: /Title/ })).toBeRequired();
  });
});
```

  `ConfirmDialog/Component.test.tsx`:

```tsx
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

    expect(screen.getByRole('button', { name: 'Delete' }).className).toContain('MuiButton-containedError');
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

    expect(screen.getByRole('button', { name: 'Publish' }).className).toContain('MuiButton-containedPrimary');
  });
});
```

  `NavList/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { NavList } from '.';

// phase-8 task-04: the shell needs an active-item state and a way to close a temporary drawer
// after navigation (DESIGN.md §C1).
describe('NavList', () => {
  const items = [
    { label: 'Dashboard', href: '/', selected: false },
    { label: 'Content', href: '/content', selected: true },
  ];

  it('marks the selected item as the current page', () => {
    render(<NavList items={items} />);

    expect(screen.getByRole('link', { name: 'Content' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: 'Content' }).className).toContain('Mui-selected');
  });

  it('calls onNavigate when any item is clicked', async () => {
    const onNavigate = vi.fn();
    render(<NavList items={items} onNavigate={onNavigate} />);

    await userEvent.click(screen.getByRole('link', { name: 'Dashboard' }));

    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
```

  `ErrorState/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ErrorState } from '.';

// phase-8 task-04: an error state can offer a way out (DESIGN.md §A3 "ErrorState (+action)").
describe('ErrorState', () => {
  it('renders the message in an assertive live region with no button by default', () => {
    render(<ErrorState message="Could not load content." />);

    expect(screen.getByRole('alert')).toHaveTextContent('Could not load content.');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders an action button inside the alert and calls it on click', async () => {
    const onClick = vi.fn();
    render(<ErrorState message="Could not load content." action={{ label: 'Retry', onClick }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
```

  `Drawer/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';

import { Drawer } from '.';

// phase-8 task-04: the nav drawer must be able to switch to MUI's temporary (modal) variant below
// the md breakpoint, and the agent panel to full width on phones (DESIGN.md §C1).
describe('Drawer', () => {
  it('renders a temporary drawer as a modal dialog when open, with its content reachable', () => {
    render(
      <Drawer variant="temporary" open onClose={vi.fn()}>
        <nav aria-label="Primary">links</nav>
      </Drawer>,
    );

    expect(screen.getByRole('presentation')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
  });

  it('keeps a closed temporary drawer mounted but hidden (keepMounted)', () => {
    render(
      <Drawer variant="temporary" open={false} onClose={vi.fn()}>
        <nav aria-label="Primary">links</nav>
      </Drawer>,
    );

    expect(screen.queryByRole('navigation', { name: 'Primary' })).toBeNull();
    expect(screen.getByRole('navigation', { name: 'Primary', hidden: true })).toBeInTheDocument();
  });

  it('applies a width override to the drawer paper', () => {
    const { container } = render(
      <Drawer anchor="right" variant="persistent" open width="100vw">
        <div>panel</div>
      </Drawer>,
    );

    expect(container.querySelector('.MuiDrawer-paper')).toHaveStyle({ width: '100vw' });
  });
});
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- common/TextField common/ConfirmDialog common/NavList common/ErrorState common/Drawer`
  Expected: FAIL — `error`/`helperText`/`onBlur`/`onKeyDown` not forwarded (type errors at
  render and missing DOM), no `containedError`, no `aria-current`, no button in ErrorState,
  `variant="temporary"` not in the union / no `keepMounted`, no width override.

- [ ] **GREEN — implementer:** the 11 pass-through folders → barrel exports → the six
  extensions per the Interfaces block.

- [ ] **Run GREEN:** same command → PASS. `pnpm -C apps/admin type-check` → clean.

- [ ] **Full suite:** `pnpm -C apps/admin test` → green (existing `ConfirmDialog`/`NavList` call
  sites are untouched by the optional props).

- [ ] **Screenshot:** none required (no screen changed) — the reviewer instead confirms
  `git diff --stat` touches only `src/components/common/**`.

- [ ] **Gates:** `pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/admin/src/components/common`
  `git commit -m "feat(admin): table/skeleton/stack/tooltip/alert/paper primitives; validation, destructive, selected, action, temporary props (p8 t04)"`

## Verify

```bash
pnpm -C apps/admin test -- common/
pnpm gates:admin
git diff --stat main -- apps/admin/src | tail -1
```

## Acceptance

- All five new test files pass; full admin suite green; `type-check` clean.
- Barrel exports every new primitive and type; each folder follows the §3 shape.
- Only `apps/admin/src/components/common/**` changed.
- `Button`'s `color` union includes `'error'`; `ConfirmDialog` uses it only when `destructive`.
- Reviewer (Sonnet) checks the five dimensions with file:line evidence.
