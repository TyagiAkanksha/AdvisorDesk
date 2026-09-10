import { describe, expect, it } from 'vitest';

import { theme } from './theme';

// phase-8 task-01, DESIGN.md §A1 — the token values every screen inherits. Pinned here so a
// drift in either twin fails loudly (theme.twin.test.ts pins that the twins match; this file
// pins what they say).
describe('theme tokens', () => {
  it('keeps the navy/gold brand palette and adds the page ground, text, and divider tokens', () => {
    expect(theme.palette.primary.main).toBe('#1E3A5F');
    expect(theme.palette.secondary.main).toBe('#C08A28');
    expect(theme.palette.background.default).toBe('#F6F7F9');
    expect(theme.palette.background.paper).toBe('#FFFFFF');
    expect(theme.palette.text.primary).toBe('#172033');
    expect(theme.palette.divider).toBe('rgba(23, 32, 51, 0.12)');
  });

  it('sets a 36px desktop h1 that scales down on phones (never MUI’s 96px default)', () => {
    expect(theme.typography.h1['@media (min-width:1200px)']).toEqual({ fontSize: '2.25rem' });
    expect(theme.typography.h1.fontSize).toBe('1.625rem');
    expect(theme.typography.h2['@media (min-width:1200px)']).toEqual({ fontSize: '1.75rem' });
    expect(theme.typography.h3['@media (min-width:1200px)']).toEqual({ fontSize: '1.375rem' });
  });

  it('uses the heading font variable for h1–h3 and the body font variable for h4–h6 and body', () => {
    expect(theme.typography.h1.fontFamily).toContain('var(--font-heading)');
    expect(theme.typography.h3.fontFamily).toContain('var(--font-heading)');
    expect(theme.typography.h4.fontFamily).toContain('var(--font-body)');
    expect(theme.typography.body1.fontFamily).toContain('var(--font-body)');
  });

  it('renders buttons in sentence case', () => {
    expect(theme.typography.button.textTransform).toBe('none');
  });

  it('sets the shared 8px corner radius', () => {
    expect(theme.shape.borderRadius).toBe(8);
  });

  it('sets flat, outlined, small, hover-underline component defaults', () => {
    expect(theme.components?.MuiButton?.defaultProps?.disableElevation).toBe(true);
    expect(theme.components?.MuiCard?.defaultProps?.variant).toBe('outlined');
    expect(theme.components?.MuiChip?.defaultProps?.size).toBe('small');
    expect(theme.components?.MuiLink?.defaultProps?.underline).toBe('hover');
    expect(theme.components?.MuiTextField?.defaultProps?.size).toBe('small');
  });
});
