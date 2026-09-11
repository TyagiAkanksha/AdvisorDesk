---
id: hy-t03
phase: hygiene-2026-09
depends_on: []
status: todo
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: sonnet
---

# Task 03 — `EmptyState`: the action renders outside the `role="status"` live region

## Goal

Close t23 M5 (Opus): "three buttons inside EmptyState's `role=status` live region (t14
primitive)". A polite live region announces its *contents* when they appear; putting
interactive controls inside it makes screen readers announce button/link text as part of the
status message and is discouraged by the ARIA authoring practices (live regions should carry
the announcement, not the controls). Both apps' `EmptyState` render the optional `action` inside
the `role="status"` box. Move the action to a sibling **after** the live region. Visual output
is identical (same wrapper padding, alignment and colour). Every existing call site is
unchanged — only the DOM nesting moves.

## Context (read ONLY these)

- `apps/admin/src/components/common/EmptyState/{Component.tsx, interface.ts, Component.test.tsx}`
- `apps/client/src/components/common/EmptyState/{Component.tsx, interface.ts, Component.test.tsx}`
- Pins that reach *into* the status region for the action (the test-author rewrites these —
  they are the only tests that encode the old nesting):
  - `apps/admin/src/components/content/ContentListScreen/Component.test.tsx` — the two tests
    `renders the "no content yet" empty state with a create link…` and
    `renders the "no match" empty state with a Clear filters button…` (lines ≈ 315–347 at the
    time of writing: `within(status).getByRole('link', …)` and
    `within(status).getByRole('button', { name: 'Clear filters' })`).
  - `apps/client/src/components/content/ContentListScreen/Component.test.tsx` lines ≈ 53–64:
    `within(status).queryByRole('link')).toBeNull()` and
    `within(status).getByRole('link', { name: 'Show all' })`.
- `docs/FRONTEND-CONVENTIONS.md` §4, §7, §9.

## Files

**Modify**
- `apps/admin/src/components/common/EmptyState/Component.tsx`, `Component.test.tsx`
- `apps/client/src/components/common/EmptyState/Component.tsx`, `Component.test.tsx`
- `apps/admin/src/components/content/ContentListScreen/Component.test.tsx` (two pins, named above)
- `apps/client/src/components/content/ContentListScreen/Component.test.tsx` (two pins, named above)

No interface changes.

## Interfaces

Render shape after the task (admin; the client is the same shape with its `Typography` and
`Button` leaves):

```tsx
<Box sx={{ textAlign: 'center', color: 'text.secondary', py: 6 }}>
  <Box role="status">
    <Icon name={icon} size="large" />
    {title ? (<Box component="p" sx={{ mt: 1, fontWeight: 'medium' }}>{title}</Box>) : null}
    {description ? (<Box component="p" sx={{ mt: 0.5 }}>{description}</Box>) : null}
    {message ? (<Box component="p" sx={{ mt: 1 }}>{message}</Box>) : null}
  </Box>
  {action ? <Box sx={{ mt: 2 }}>{action}</Box> : null}
</Box>
```

The outer `Box` carries the styling it always had; the inner `Box role="status"` carries only
the announcement (icon + text). The action sits **after** the live region as its sibling.

## Steps

- [ ] **Step 1 (test-author, RED): rewrite the four primitive pins.**

  `apps/admin/src/components/common/EmptyState/Component.test.tsx` — replace the first test:

  ```tsx
  it('renders title and description inside the status region and the action OUTSIDE it', () => {
    render(
      <EmptyState
        title="No content yet"
        description="Create your first article to get started."
        action={<button type="button">Create your first article</button>}
      />,
    );

    const status = screen.getByRole('status');
    expect(within(status).getByText('No content yet')).toBeInTheDocument();
    expect(
      within(status).getByText('Create your first article to get started.'),
    ).toBeInTheDocument();
    // t23 M5: interactive controls must not live inside a polite live region.
    expect(within(status).queryByRole('button')).toBeNull();
    expect(screen.getByRole('button', { name: 'Create your first article' })).toBeInTheDocument();
  });
  ```

  Keep the other two admin tests verbatim.

  `apps/client/src/components/common/EmptyState/Component.test.tsx` — replace the second test:

  ```tsx
  it('renders an action link when given, outside the status region', () => {
    render(
      <EmptyState
        message="No articles tagged 'x'."
        icon="Search"
        action={{ label: 'Show all', href: '/' }}
      />,
    );

    expect(screen.getByRole('link', { name: 'Show all' })).toHaveAttribute('href', '/');
    // t23 M5: interactive controls must not live inside a polite live region.
    expect(within(screen.getByRole('status')).queryByRole('link')).toBeNull();
  });
  ```

  (add `within` to the RTL import.) Keep the first client test verbatim.

- [ ] **Step 2 (test-author, RED): rewrite the four screen pins** so they query the control at
  document level and assert it is not inside the status region:
  - admin `ContentListScreen/Component.test.tsx` "no content yet": replace the
    `within(status).getByRole('link', …)` assertion with
    `expect(screen.getByRole('link', { name: 'Create your first article' })).toHaveAttribute('href', '/content/new');`
    followed by `expect(within(status).queryByRole('link')).toBeNull();`
  - admin "no match": `await user.click(screen.getByRole('button', { name: 'Clear filters' }));`
    preceded by `expect(within(status).queryByRole('button')).toBeNull();`
  - client `ContentListScreen/Component.test.tsx` ≈ line 55: keep
    `expect(within(status).queryByRole('link')).toBeNull();` (still true) **and** add
    `expect(screen.queryByRole('link', { name: 'Show all' })).toBeNull();` so the "no link by
    default" case still asserts something; ≈ line 64: replace with
    `expect(screen.getByRole('link', { name: 'Show all' })).toHaveAttribute('href', '/');` and
    `expect(within(status).queryByRole('link')).toBeNull();`.
  Touch nothing else in those files.

- [ ] **Step 3: run RED.** `cd apps/admin && npx vitest run EmptyState ContentListScreen` and
  the same in `apps/client` → the rewritten pins fail on `queryByRole(...)` being non-null.
  Paste the failure lines.

- [ ] **Step 4 (implementer, GREEN):** restructure both `Component.tsx` files to the render
  shape in Interfaces. Update each header comment: replace the `role="status"` sentence with
  "`role="status"` (polite live region) wraps only the icon + text; the optional `action` is a
  sibling after it — controls must not live inside a live region (hygiene t03, t23 M5)."
  Client: keep the `Button variant="outlined" href={action.href}` leaf as is.

- [ ] **Step 5: run GREEN + gates in both apps** (full `npx vitest run`, type-check, lint,
  prettier). Any *other* failing test is a stop rule — report, do not edit.

- [ ] **Step 6: commit.** `git commit -m "refactor(common): EmptyState action renders outside the live region (p8 t23 M5)"`

## Acceptance criteria

- In both apps, `within(getByRole('status'))` finds no `button`/`link` for an `EmptyState`
  with an action; the action is still reachable by role at document level with the same
  name/href.
- No call site changed. Both gate sets green.

## Report

Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-03-test-author.md`;
implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-03-implementer.md`.
