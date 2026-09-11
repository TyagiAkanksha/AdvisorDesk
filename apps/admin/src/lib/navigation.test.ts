import { describe, expect, it } from 'vitest';

import { isActivePath } from './navigation';

describe('isActivePath', () => {
  it.each([
    ['/', '/', true],
    ['/content', '/', false],
    ['/content', '/content', true],
    ['/content/new', '/content', true],
    ['/content/11111111-1111-1111-1111-111111111111', '/content', true],
    ['/content-archive', '/content', false],
    ['/connected-apps', '/connected-apps', true],
    ['/connected-apps', '/content', false],
  ])('isActivePath(%s, %s) → %s', (pathname, href, expected) => {
    expect(isActivePath(pathname, href)).toBe(expected);
  });
});
