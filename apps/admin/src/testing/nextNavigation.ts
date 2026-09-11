import { useSyncExternalStore } from 'react';
import { vi } from 'vitest';

// phase-8 task-14: a stateful stand-in for `next/navigation` for tests of screens that keep
// their state in the URL (DESIGN.md §C4). A static `vi.fn()` router cannot re-render the
// component that called `replace()`; this module holds ONE location that the router methods
// write and the two read hooks subscribe to, so tests exercise the real "write URL → re-render
// from URL" loop.
interface Location {
  pathname: string;
  search: string;
}

let location: Location = { pathname: '/', search: '' };
const listeners = new Set<() => void>();

function setLocation(href: string): void {
  const url = new URL(href, 'http://admin.test');
  location = { pathname: url.pathname, search: url.search };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const replace = vi.fn((href: string, _options?: { scroll?: boolean }) => setLocation(href));
const push = vi.fn((href: string, _options?: { scroll?: boolean }) => setLocation(href));

export const navigation = {
  replace,
  push,
  reset(href = '/'): void {
    replace.mockClear();
    push.mockClear();
    setLocation(href);
  },
  get pathname(): string {
    return location.pathname;
  },
  get search(): string {
    return location.search;
  },
};

export function useRouter() {
  return { replace, push, back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() };
}

export function usePathname(): string {
  return useSyncExternalStore(
    subscribe,
    () => location.pathname,
    () => location.pathname,
  );
}

export function useSearchParams(): URLSearchParams {
  const search = useSyncExternalStore(
    subscribe,
    () => location.search,
    () => location.search,
  );
  return new URLSearchParams(search);
}
