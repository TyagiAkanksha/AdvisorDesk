import { vi } from 'vitest';

// phase-8 task-14 (DESIGN.md §6): jsdom has no `matchMedia`, so MUI's `useMediaQuery` falls
// back to `false` — every responsive branch reads as desktop. Install a stub that answers
// `matches` for every query; the returned function restores jsdom's original state.
export function stubMatchMedia(matches: boolean): () => void {
  // Cast through `unknown` (not `Window & {...}`): intersecting with `Window` itself — whose
  // own `matchMedia` is REQUIRED — makes the merged property required too, so `delete` below
  // would fail to type-check (TS2790). This narrower type keeps `matchMedia` genuinely optional.
  const target = window as unknown as { matchMedia?: typeof window.matchMedia };
  const original = target.matchMedia;
  target.matchMedia = vi.fn((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(() => false),
  })) as unknown as typeof window.matchMedia;
  return () => {
    if (original === undefined) {
      delete target.matchMedia;
    } else {
      target.matchMedia = original;
    }
  };
}
