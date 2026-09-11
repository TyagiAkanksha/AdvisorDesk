---
id: p8-t16
phase: phase-8-ui-polish
depends_on: [p8-t13, p8-t15]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 16 — Sign-in card with `?error=` messaging (C2)

## Goal

Replace the bare "Sign in with Google" button with a centred outlined card — wordmark,
one-line subtitle, the Google button, fine print — that reads the `?error=` reason task 13's
API now sends and shows a friendly message for `forbidden` (wrong Google account) and `state`
(expired/tampered flow). The page reads `searchParams` as a Server Component and passes the
value down, so the screen stays a dumb prop-renderer and no Suspense boundary is needed.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2 and §5 C2 (note the plan-time amendment: the
  reason comes in as a prop from the page's `searchParams`, not from `useSearchParams()`).
- `docs/FRONTEND-CONVENTIONS.md` §3 (pages thin; components dumb; logic in `lib/`), §7, §9.
- `apps/admin/src/components/auth/SignInScreen/{Component.tsx, index.ts, Component.test.tsx}`
  — current button + its two pins (kept verbatim; new cases appended, same dynamic-import
  idiom because `API_BASE_URL` is read at module load).
- `apps/admin/src/app/signin/page.tsx`; `apps/client/src/app/page.tsx` (sub-phase B: the
  `searchParams: Promise<…>` page idiom to copy).
- `apps/admin/src/components/common/{Alert,Box,Button,Paper,Stack,Typography}/`,
  `apps/admin/src/lib/{copy.ts, apiBase.ts}`.
- Task 13's wire contract: `Location: {admin_app_url}/signin?error=state|forbidden`.

## Files

**Create**
- `src/lib/signInError.ts`, `src/lib/signInError.test.ts`
- `src/components/auth/SignInScreen/interface.ts`

**Modify**
- `src/components/auth/SignInScreen/{Component.tsx, index.ts, Component.test.tsx}`
- `src/app/signin/page.tsx`
- `src/lib/copy.ts`

## Interfaces

```ts
// src/lib/copy.ts additions
export const SIGN_IN_SUBTITLE = 'Sign in to manage AdvisorDesk content';
export const SIGN_IN_BUTTON_LABEL = 'Sign in with Google';
export const SIGN_IN_FINE_PRINT = 'Access is limited to allowlisted admin accounts.';
export const SIGN_IN_ERROR_FORBIDDEN = "This Google account isn't on the admin allowlist.";
export const SIGN_IN_ERROR_STATE = 'Sign-in expired or was tampered with. Please try again.';

// src/lib/signInError.ts — pure
export function signInErrorMessage(reason: string | undefined): string | null;
// 'forbidden' → SIGN_IN_ERROR_FORBIDDEN; 'state' → SIGN_IN_ERROR_STATE; anything else → null

// src/components/auth/SignInScreen/interface.ts
export interface SignInScreenProps {
  /** The `?error=` reason from the URL, forwarded by the page; unknown values show nothing. */
  error?: string;
}
```

**Screen render (exact):**

```tsx
<Box
  component="main"
  sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}
>
  <Paper variant="outlined" sx={{ p: 4, width: '100%', maxWidth: 400 }}>
    <Stack spacing={2}>
      <Typography variant="h3" component="h1">{APP_NAME}</Typography>
      <Typography variant="body1" color="text.secondary">{SIGN_IN_SUBTITLE}</Typography>
      {message ? <Alert severity="error">{message}</Alert> : null}
      <Button variant="contained" href={`${API_BASE_URL}/api/v1/auth/login`} fullWidth>
        {SIGN_IN_BUTTON_LABEL}
      </Button>
      <Typography variant="caption" color="text.secondary" component="p">{SIGN_IN_FINE_PRINT}</Typography>
    </Stack>
  </Paper>
</Box>
```

where `const message = signInErrorMessage(error)`. The screen has no hooks and stays a Server
Component (the `Button` is a `'use client'` primitive; an external `href` renders a plain
`<a>` — the existing "never a JS fetch" pin still holds).

**Page (exact):**

```tsx
import type { Metadata } from 'next';

import { SignInScreen } from '@/components/auth/SignInScreen';

interface PageProps {
  searchParams: Promise<{ error?: string | string[] }>;
}

export const metadata: Metadata = { title: 'Sign in' };

// phase-8 task-16 (DESIGN.md §C2): the `?error=` reason task 13's API redirect carries is read
// here (a Server Component) and passed down as a prop — `useSearchParams()` in the screen would
// force a Suspense boundary and make the screen a client island for no gain. A repeated
// `?error=` (string[]) is treated as absent.
export default async function Page({ searchParams }: PageProps) {
  const { error } = await searchParams;
  return <SignInScreen error={typeof error === 'string' ? error : undefined} />;
}
```

(`PageContainer` is dropped from this page — the screen owns its own centred `<main>`.)

## Steps (TDD)

- [ ] **RED — test-author.**

**`src/lib/signInError.test.ts`** (node)

```ts
import { describe, expect, it } from 'vitest';

import { SIGN_IN_ERROR_FORBIDDEN, SIGN_IN_ERROR_STATE } from './copy';
import { signInErrorMessage } from './signInError';

describe('signInErrorMessage', () => {
  it('maps the two reasons the API sends', () => {
    expect(signInErrorMessage('forbidden')).toBe(SIGN_IN_ERROR_FORBIDDEN);
    expect(signInErrorMessage('state')).toBe(SIGN_IN_ERROR_STATE);
  });

  it('returns null for anything else', () => {
    expect(signInErrorMessage(undefined)).toBeNull();
    expect(signInErrorMessage('')).toBeNull();
    expect(signInErrorMessage('FORBIDDEN')).toBeNull();
    expect(signInErrorMessage('<script>')).toBeNull();
  });
});
```

**Append to `SignInScreen/Component.test.tsx`** (inside the existing `describe`, same
`await import('.')` idiom; add `SIGN_IN_ERROR_FORBIDDEN`/`SIGN_IN_ERROR_STATE` imports from
`@/lib/copy` at the top — copy is env-independent, a static import is fine):

```tsx
  it('renders the card: main landmark, wordmark h1, subtitle, fine print, no alert', async () => {
    const { SignInScreen } = await import('.');
    render(<SignInScreen />);

    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'AdvisorDesk Admin' })).toBeInTheDocument();
    expect(screen.getByText('Sign in to manage AdvisorDesk content')).toBeInTheDocument();
    expect(screen.getByText('Access is limited to allowlisted admin accounts.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('error="forbidden" shows the allowlist message as an alert', async () => {
    const { SignInScreen } = await import('.');
    render(<SignInScreen error="forbidden" />);

    expect(screen.getByRole('alert')).toHaveTextContent(SIGN_IN_ERROR_FORBIDDEN);
  });

  it('error="state" shows the expired/tampered message as an alert', async () => {
    const { SignInScreen } = await import('.');
    render(<SignInScreen error="state" />);

    expect(screen.getByRole('alert')).toHaveTextContent(SIGN_IN_ERROR_STATE);
  });

  it('an unknown error value shows no alert (and never echoes the value)', async () => {
    const { SignInScreen } = await import('.');
    render(<SignInScreen error="something-else" />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText(/something-else/)).not.toBeInTheDocument();
  });
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- SignInScreen signInError` → `lib/signInError`
  unresolved; the four appended cases fail (no main/heading/alert; `error` prop is a TS
  error); the two existing pins stay green.

- [ ] **GREEN — implementer:** copy → `signInError.ts` → `interface.ts` + screen → page.

- [ ] **Run GREEN:** `pnpm -C apps/admin test -- SignInScreen signInError`; full suite;
  `pnpm -C apps/admin type-check`.

- [ ] **Screenshots** (iframe technique, 1440 + 390): `/signin` and `/signin?error=forbidden`
  from `pnpm -C apps/admin dev` (no session needed). Store under
  `.superpowers/sdd/phase-8-ui-polish/screenshots/t16-*.jpg`.

- [ ] **Gates:** `pnpm gates:admin` → clean; `pnpm -C apps/admin build` → exit 0 (the page is
  now dynamic — confirm `/signin` is listed as `ƒ` (dynamic) in the build output, not `○`).

- [ ] **Commit:**
  `git add apps/admin/src/components/auth/SignInScreen apps/admin/src/app/signin/page.tsx apps/admin/src/lib/signInError.ts apps/admin/src/lib/signInError.test.ts apps/admin/src/lib/copy.ts`
  `git commit -m "feat(admin): sign-in card with ?error= messaging (p8 t16)"`

## Verify

```bash
pnpm -C apps/admin test -- SignInScreen signInError
pnpm gates:admin && pnpm -C apps/admin build
```

## Acceptance

- Card centred at both widths (≤400px wide, full width on phones); h1 wordmark; Google button
  still a real `<a>` to `${API_BASE_URL}/api/v1/auth/login`.
- `?error=forbidden` / `?error=state` render the exact copy strings as `role="alert"`; any
  other value renders nothing and is never echoed.
- End-to-end check in the report: with the local API running, sign in with a non-allowlisted
  Google account is NOT required — instead `curl -i "$API/api/v1/auth/callback?code=x&state=bad"`
  shows `Location: …/signin?error=state`, and loading that URL in the dev admin shows the
  state message.
