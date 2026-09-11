// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation } from '@/testing/nextNavigation';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

function useLocationUnderTest() {
  return { pathname: usePathname(), params: useSearchParams(), router: useRouter() };
}

describe('testing/nextNavigation seam', () => {
  beforeEach(() => {
    navigation.reset('/content?status=draft');
  });

  it('reads pathname and search params from the mocked location', () => {
    const { result } = renderHook(() => useLocationUnderTest());

    expect(result.current.pathname).toBe('/content');
    expect(result.current.params.get('status')).toBe('draft');
  });

  it('router.replace() updates the location AND re-renders subscribers', () => {
    const { result } = renderHook(() => useLocationUnderTest());

    act(() => {
      result.current.router.replace('/content?status=published&page=2', { scroll: false });
    });

    expect(result.current.params.get('status')).toBe('published');
    expect(result.current.params.get('page')).toBe('2');
    expect(navigation.replace).toHaveBeenCalledWith('/content?status=published&page=2', {
      scroll: false,
    });
    expect(navigation.search).toBe('?status=published&page=2');
  });

  it('router.push() changes the pathname', () => {
    const { result } = renderHook(() => useLocationUnderTest());

    act(() => {
      result.current.router.push('/connected-apps');
    });

    expect(result.current.pathname).toBe('/connected-apps');
    expect(navigation.push).toHaveBeenCalledWith('/connected-apps');
  });

  it('reset() clears the spies and the location', () => {
    const { result } = renderHook(() => useLocationUnderTest());
    act(() => {
      result.current.router.push('/x');
    });

    navigation.reset();

    expect(navigation.push).not.toHaveBeenCalled();
    expect(navigation.pathname).toBe('/');
    expect(navigation.search).toBe('');
  });
});
