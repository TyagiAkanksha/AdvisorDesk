import { describe, expect, it } from 'vitest';

import { isInternalHref } from './href';

describe('isInternalHref', () => {
  it.each(['/', '/content', '/content/abc?x=1#y'])('routes %s through next/link', (href) => {
    expect(isInternalHref(href)).toBe(true);
  });

  it.each([
    '//cdn.example.com/x',
    'https://example.com/',
    'http://localhost:8000/api/v1/auth/login',
    'mailto:hi@example.com',
    '#top',
    'relative/path',
    '',
  ])('renders %s as a plain anchor', (href) => {
    expect(isInternalHref(href)).toBe(false);
  });
});
