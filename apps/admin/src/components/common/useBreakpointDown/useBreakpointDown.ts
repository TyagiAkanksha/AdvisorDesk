import type { Breakpoint } from '@mui/material/styles';
import { useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';

// phase-8 task-14 (DESIGN.md §C1/§C5): the one place `useMediaQuery` is imported
// (FRONTEND-CONVENTIONS §4 — MUI stays behind common/). `'md'` → true below 900px.
//
// Deviation from the brief's literal `useMediaQuery((theme) => theme.breakpoints.down(key))`:
// that callback form reads `theme` from `@mui/material/useMediaQuery`'s OWN internal,
// provider-less context lookup (`@mui/system`'s `useThemeWithoutDefault`, default `null`) —
// verified empirically that it throws `Cannot read properties of null (reading 'breakpoints')`
// with no `ThemeProvider` in the tree, which is exactly how
// `useBreakpointDown.test.tsx`'s first two `renderHook`s run (no wrapper — matching the real
// `useAppShell` call site, which also renders under `ThemeProvider` further up but shouldn't
// need one just to unit-test this hook). `@mui/material/styles`' own `useTheme()` DOES fall
// back to MUI's default theme outside a `ThemeProvider`, so resolving the query STRING through
// it first (rather than handing `useMediaQuery` a callback) keeps the hook safe to render
// standalone while still reading the real theme when one is present.
export function useBreakpointDown(key: Extract<Breakpoint, 'sm' | 'md' | 'lg'>): boolean {
  const theme = useTheme();
  return useMediaQuery(theme.breakpoints.down(key));
}
