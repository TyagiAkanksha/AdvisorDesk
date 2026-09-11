// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { stubMatchMedia } from '@/testing/matchMedia';
import { navigation } from '@/testing/nextNavigation';

import { useAppShell } from './useAppShell';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

describe('useAppShell', () => {
  let restore: (() => void) | null = null;

  beforeEach(() => {
    navigation.reset('/content/11111111-1111-1111-1111-111111111111');
  });

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it('selects the nav item whose route contains the pathname, and gives every item an icon', () => {
    const { result } = renderHook(() => useAppShell());

    expect(result.current.navItems.map((item) => [item.href, item.selected])).toEqual([
      ['/', false],
      ['/content', true],
      ['/connected-apps', false],
    ]);
    expect(result.current.navItems.every((item) => item.icon !== undefined)).toBe(true);
  });

  it('selects Dashboard only on the exact root path', () => {
    navigation.reset('/');

    const { result } = renderHook(() => useAppShell());

    expect(result.current.navItems.map((item) => item.selected)).toEqual([true, false, false]);
  });

  it('starts desktop-wide with both drawers closed', () => {
    const { result } = renderHook(() => useAppShell());

    expect(result.current.isNarrow).toBe(false);
    expect(result.current.navOpen).toBe(false);
    expect(result.current.agentOpen).toBe(false);
  });

  it('below md, openNav/closeNav toggle the temporary nav drawer', () => {
    restore = stubMatchMedia(true);
    const { result } = renderHook(() => useAppShell());

    expect(result.current.isNarrow).toBe(true);
    act(() => result.current.openNav());
    expect(result.current.navOpen).toBe(true);
    act(() => result.current.closeNav());
    expect(result.current.navOpen).toBe(false);
  });

  it('toggleAgent flips the agent panel; closeAgent forces it closed', () => {
    const { result } = renderHook(() => useAppShell());

    act(() => result.current.toggleAgent());
    expect(result.current.agentOpen).toBe(true);
    act(() => result.current.toggleAgent());
    expect(result.current.agentOpen).toBe(false);
    act(() => result.current.toggleAgent());
    act(() => result.current.closeAgent());
    expect(result.current.agentOpen).toBe(false);
  });
});
