// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { stubMatchMedia } from '@/testing/matchMedia';

import { useBreakpointDown } from '.';

describe('useBreakpointDown', () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it('is false in jsdom by default (no matchMedia → MUI falls back to false)', () => {
    const { result } = renderHook(() => useBreakpointDown('md'));

    expect(result.current).toBe(false);
  });

  it('is true when matchMedia reports a match', () => {
    restore = stubMatchMedia(true);

    const { result } = renderHook(() => useBreakpointDown('md'));

    expect(result.current).toBe(true);
  });

  it("asks matchMedia for the theme's md down-query", () => {
    restore = stubMatchMedia(false);

    renderHook(() => useBreakpointDown('md'));

    expect(window.matchMedia).toHaveBeenCalledWith('(max-width:899.95px)');
  });
});
