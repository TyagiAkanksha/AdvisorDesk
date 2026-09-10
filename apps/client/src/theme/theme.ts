// AdvisorDesk shared design tokens (docs/FRONTEND-CONVENTIONS.md §2, DESIGN.md §A1).
//
// This file is INTENTIONALLY duplicated: apps/client/src/theme/theme.ts and
// apps/admin/src/theme/theme.ts must stay byte-identical (the two apps deploy independently,
// so each carries its own copy rather than importing a shared package). `theme.twin.test.ts`
// beside each copy fails the suite if they diverge — edit both, or neither.
import { createTheme, responsiveFontSizes } from '@mui/material/styles';

// Font families arrive as CSS variables set on <html> by each app's app/layout.tsx via
// next/font, so this file stays free of Next imports (importable from Server Components and
// node-env tests). Client: heading = Source Serif 4, body = Inter. Admin: both = Inter.
// The fallbacks are what renders if a variable is missing.
const HEADING_FONT = 'var(--font-heading), Georgia, serif';
const BODY_FONT = 'var(--font-body), system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

const baseTheme = createTheme({
  palette: {
    // Deep navy — trust/stability register for an advisory product.
    primary: { main: '#1E3A5F' },
    // Muted gold — calls to action ONLY (DESIGN.md §2); destructive actions use `color="error"`.
    secondary: { main: '#C08A28' },
    // Off-white page ground so white Paper/Card surfaces have visible edges.
    background: { default: '#F6F7F9', paper: '#FFFFFF' },
    text: { primary: '#172033' },
    divider: 'rgba(23, 32, 51, 0.12)',
  },
  typography: {
    fontFamily: BODY_FONT,
    // Desktop sizes; responsiveFontSizes below scales h1–h3 down on phones (factor 2).
    h1: { fontFamily: HEADING_FONT, fontSize: '2.25rem', fontWeight: 600, lineHeight: 1.2 },
    h2: { fontFamily: HEADING_FONT, fontSize: '1.75rem', fontWeight: 600, lineHeight: 1.25 },
    h3: { fontFamily: HEADING_FONT, fontSize: '1.375rem', fontWeight: 600, lineHeight: 1.3 },
    h4: { fontSize: '1.125rem', fontWeight: 600, lineHeight: 1.35 },
    h5: { fontSize: '1rem', fontWeight: 600, lineHeight: 1.4 },
    h6: { fontSize: '0.875rem', fontWeight: 600, lineHeight: 1.4 },
    body1: { fontSize: '1rem', lineHeight: 1.65 },
    body2: { fontSize: '0.875rem', lineHeight: 1.5 },
    // Sentence case everywhere (DESIGN.md §2) — Material's uppercase default reads as shouting.
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiCard: { defaultProps: { variant: 'outlined' } },
    MuiChip: { defaultProps: { size: 'small' } },
    MuiLink: { defaultProps: { underline: 'hover' } },
    MuiTextField: { defaultProps: { size: 'small' } },
  },
  // spacing is intentionally left at the MUI default (theme.spacing(n) = n * 8px).
});

// factor 2: h1 2.25rem → 1.625rem on phones, growing back to 2.25rem at the `lg` breakpoint.
// disableAlign: keep the line heights above instead of snapping them to a 4px grid.
export const theme = responsiveFontSizes(baseTheme, { factor: 2, disableAlign: true });
