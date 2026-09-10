---
id: p8-t06
phase: phase-8-ui-polish
depends_on: [p8-t01]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 06 — Client primitives + extensions (apps/client)

## Goal

Grow `apps/client/src/components/common/` with the wrappers sub-phase B's shell, home grid,
article page, and chat need (AppBar, Toolbar, Stack, Skeleton, Grid, Tooltip, Alert, Paper,
IconButton) and extend four existing primitives (`TextField`, `Button`, `ErrorState`, `EmptyState`)
plus `PageContainer` (`maxWidth`). Same contract as the admin: wrap MUI, keep call sites MUI-free.
No screen changes in this task.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §A3 (client row) and §2.
- `docs/FRONTEND-CONVENTIONS.md` §3, §4, §7, §9.
- `apps/client/src/components/common/index.ts` (barrel).
- `apps/client/src/components/common/Box/` — pass-through template.
- `apps/client/src/components/common/{TextField,Button,ErrorState,EmptyState,PageContainer,Icon}/`
  — read all files of each.
- `apps/admin/src/components/common/Button/Component.tsx` — the `isInternalHref` → `next/link`
  split to copy; `apps/admin/src/components/common/IconButton/{Component.tsx,interface.ts}` —
  the icon-button contract to mirror.
- `apps/client/src/components/common/ErrorState/Component.test.tsx` — test style in this app
  (note the explicit `afterEach(cleanup)`; the client's `vitest.setup.ts` now registers cleanup
  too, so new files may omit it — keep the pragma and barrel import).

## Files

**Create (pass-throughs — three files each, no tests; the composites/screens that use them are
the test):**

| Folder | MUI import | Props alias |
|---|---|---|
| `common/AppBar/` | `@mui/material/AppBar` | `AppBarProps = MuiAppBarProps` |
| `common/Toolbar/` | `@mui/material/Toolbar` | `ToolbarProps = MuiToolbarProps` |
| `common/Stack/` | `@mui/material/Stack` | `StackProps = MuiStackProps` |
| `common/Skeleton/` | `@mui/material/Skeleton` | `SkeletonProps = MuiSkeletonProps` |
| `common/Grid/` | `@mui/material/Grid` | `GridProps = MuiGridProps` (MUI 9 Grid: `container`, `size={{ xs: 12, sm: 6, md: 4 }}`, `spacing`) |
| `common/Tooltip/` | `@mui/material/Tooltip` | `TooltipProps = MuiTooltipProps` |
| `common/Alert/` | `@mui/material/Alert` | `AlertProps = MuiAlertProps` |
| `common/Paper/` | `@mui/material/Paper` | `PaperProps = MuiPaperProps` |

Template (this is `Stack`; every row above is the same three files with the names swapped):

```tsx
// common/Stack/interface.ts
import type { StackProps as MuiStackProps } from '@mui/material/Stack';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — a generic layout
// primitive like Box, not a bespoke contract like Icon. phase-8 task-06.
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

**Create (bespoke, with tests):**
- `common/IconButton/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
- `common/Button/Component.test.tsx`
- `common/TextField/Component.test.tsx`
- `common/EmptyState/Component.test.tsx`
- `common/PageContainer/interface.ts` (new — it gains a prop) + `Component.test.tsx`

**Modify**
- `common/index.ts` — export everything new, alphabetically.
- `common/TextField/{interface.ts, Component.tsx}`
- `common/Button/{interface.ts, Component.tsx}`
- `common/ErrorState/{interface.ts, Component.tsx, Component.test.tsx}`
- `common/EmptyState/{interface.ts, Component.tsx}`
- `common/PageContainer/{Component.tsx, index.ts}`

## Interfaces

**Produces exactly (additions marked `// NEW`):**

```ts
// common/IconButton/interface.ts
import type { IconProps } from '../Icon';
export interface IconButtonProps {
  name: IconProps['name'];
  /** Accessible name — goes on the <button>, not the icon (FRONTEND-CONVENTIONS §9). */
  label: string;
  onClick?: () => void;
  type?: 'button' | 'submit';
  size?: 'small' | 'medium' | 'large';
  color?: 'default' | 'primary';
  disabled?: boolean;
}
// Component.tsx: <MuiIconButton aria-label={label} onClick={onClick} type={type ?? 'button'}
//   size={size ?? 'medium'} color={color ?? 'default'} disabled={disabled}><Icon name={name} size={size ?? 'medium'} /></MuiIconButton>

// common/TextField/interface.ts
import type { KeyboardEvent } from 'react';
export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  fullWidth?: boolean;
  multiline?: boolean;                                                // NEW
  minRows?: number;                                                   // NEW
  maxRows?: number;                                                   // NEW
  /** Raw key events — the chat composer's Enter-to-send lives in its VM hook, not here. */
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void; // NEW
}
// Component.tsx forwards each; `ChangeEvent<HTMLInputElement | HTMLTextAreaElement>` for the handler.

// common/Button/interface.ts
import type { MouseEventHandler, ReactNode } from 'react';
export interface ButtonProps {
  children: ReactNode;
  /** Internal (`/...`) renders via next/link; external renders a plain <a>. */
  href?: string;                                                      // NEW
  onClick?: MouseEventHandler<HTMLElement>;
  type?: 'button' | 'submit' | 'reset';
  variant?: 'text' | 'outlined' | 'contained';
  color?: 'primary' | 'secondary' | 'inherit' | 'error';             // NEW
  size?: 'small' | 'medium' | 'large';                                // NEW
  startIcon?: ReactNode;                                              // NEW
  fullWidth?: boolean;                                                // NEW
  disabled?: boolean;
}
// Component.tsx: copy apps/admin's Button/Component.tsx body (isInternalHref → component={Link}).
// Mark the file 'use client' (next/link is a function passed as `component` — same RSC-boundary
// reason as common/Link/Component.tsx's header comment).

// common/ErrorState/interface.ts
export interface ErrorStateProps {
  message?: string;
  action?: { label: string; onClick: () => void };                    // NEW
}
// Component.tsx: when `action` is set, render <Button variant="outlined" onClick={action.onClick}>
// under the message, inside the role="alert" wrapper; wrapper gets sx textAlign center.

// common/EmptyState/interface.ts
import type { IconProps } from '../Icon';
export interface EmptyStateProps {
  message: string;
  /** Defaults to 'Article' (the existing look). */
  icon?: IconProps['name'];                                           // NEW
  /** A way out of the empty state, rendered as an outlined link-button. */
  action?: { label: string; href: string };                           // NEW
}
// Component.tsx: <Icon name={icon ?? 'Article'} size="large" />, message, then
//   {action ? <Button variant="outlined" href={action.href}>{action.label}</Button> : null}
//   wrapper: <Box role="status" sx={{ textAlign: 'center', py: 6 }}> (import Box from '../Box').

// common/PageContainer/interface.ts (new file)
import type { ReactNode } from 'react';
export interface PageContainerProps {
  children: ReactNode;
  /** Reading width: 'md' (900px) for articles and chat, 'lg' (default) for lists. */
  maxWidth?: 'sm' | 'md' | 'lg';                                      // NEW
}
// Component.tsx: <Container component="main" maxWidth={maxWidth ?? 'lg'} sx={{ py: 4 }}>
// index.ts additionally exports `PageContainerProps`.
```

## Steps (TDD)

- [ ] **RED — test-author.**

  `IconButton/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { IconButton } from '.';

// phase-8 task-06: icon-only actions (send, stop, menu) get their accessible name on the button.
describe('IconButton', () => {
  it('renders a button named by label that calls onClick', async () => {
    const onClick = vi.fn();
    render(<IconButton name="Search" label="Search" onClick={onClick} />);

    await userEvent.click(screen.getByRole('button', { name: 'Search' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('can be a submit button and can be disabled', () => {
    render(<IconButton name="Search" label="Send" type="submit" disabled />);

    const button = screen.getByRole('button', { name: 'Send' });
    expect(button).toHaveAttribute('type', 'submit');
    expect(button).toBeDisabled();
  });
});
```

  `Button/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Button } from '.';

// phase-8 task-06: the client Button gains the admin Button's href mode (DESIGN.md §A3).
describe('Button', () => {
  it('renders an internal href as a link with the href attribute', () => {
    render(<Button href="/chat">Ask a question</Button>);

    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute('href', '/chat');
  });

  it('renders an external href as a plain link', () => {
    render(<Button href="https://example.com">Docs</Button>);

    expect(screen.getByRole('link', { name: 'Docs' })).toHaveAttribute('href', 'https://example.com');
  });

  it('still renders a button that fires onClick when no href is given', async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} color="error" startIcon={<span data-testid="icon" />}>
        Delete
      </Button>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });
});
```

  `TextField/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TextField } from '.';

// phase-8 task-06: the chat composer needs a growing multiline field and raw key events.
describe('TextField', () => {
  it('renders a textarea when multiline', () => {
    render(<TextField label="Message" value="" onChange={vi.fn()} multiline minRows={1} maxRows={6} />);

    expect(screen.getByRole('textbox', { name: 'Message' }).tagName).toBe('TEXTAREA');
  });

  it('forwards key events through onKeyDown', async () => {
    const onKeyDown = vi.fn();
    render(<TextField label="Message" value="" onChange={vi.fn()} onKeyDown={onKeyDown} />);

    await userEvent.click(screen.getByRole('textbox', { name: 'Message' }));
    await userEvent.keyboard('{Enter}');

    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onKeyDown.mock.calls[0]?.[0]).toMatchObject({ key: 'Enter' });
  });
});
```

  Append to `ErrorState/Component.test.tsx`:

```tsx
  it('renders an action button inside the alert and calls it on click', async () => {
    const onClick = vi.fn();
    render(<ErrorState message="Could not load." action={{ label: 'Try again', onClick }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
```

  (add `import userEvent from '@testing-library/user-event';` and `vi` to that file's imports.)

  `EmptyState/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { EmptyState } from '.';

// phase-8 task-06: empty states can name their icon and offer a way out (DESIGN.md §B2).
describe('EmptyState', () => {
  it('renders the message in a polite live region with no link by default', () => {
    render(<EmptyState message="No published content yet." />);

    expect(screen.getByRole('status')).toHaveTextContent('No published content yet.');
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('renders an action link when given', () => {
    render(
      <EmptyState message="No articles tagged 'x'." icon="Search" action={{ label: 'Show all', href: '/' }} />,
    );

    expect(screen.getByRole('link', { name: 'Show all' })).toHaveAttribute('href', '/');
  });
});
```

  `PageContainer/Component.test.tsx`:

```tsx
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
```

- [ ] **Run RED:** `pnpm -C apps/client test -- common/`
  Expected: FAIL — `IconButton` module missing; `href`/`multiline`/`onKeyDown`/`action`/
  `icon`/`maxWidth` unsupported (type errors and missing DOM).

- [ ] **GREEN — implementer:** eight pass-through folders → `IconButton` → the five
  extensions per the Interfaces block → barrel.

- [ ] **Run GREEN:** same command → PASS. `pnpm -C apps/client type-check` → clean.

- [ ] **Full suite:** `pnpm -C apps/client test` → green (all additions are optional props).

- [ ] **Screenshot:** none required — reviewer confirms the diff is limited to `common/**`.

- [ ] **Gates:** `pnpm gates:client` → clean.

- [ ] **Commit:**
  `git add apps/client/src/components/common`
  `git commit -m "feat(client): shell/layout primitives, IconButton, href/multiline/action/maxWidth extensions (p8 t06)"`

## Verify

```bash
pnpm -C apps/client test -- common/
pnpm gates:client
```

## Acceptance

- All new/extended tests pass; full suite green; type-check clean.
- Only `apps/client/src/components/common/**` changed; barrel complete.
- `Button` with an internal `href` renders via `next/link` exactly like the admin's.
- Reviewer (Sonnet) checks the five dimensions with file:line evidence.
