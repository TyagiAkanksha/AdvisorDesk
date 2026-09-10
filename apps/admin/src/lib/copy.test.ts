import { describe, expect, it } from 'vitest';

import { GENERIC_ERROR_MESSAGE, NOT_FOUND_TITLE, PLACEHOLDER_DASH } from './copy';

describe('admin copy module', () => {
  it('owns the shared placeholder and error strings', () => {
    expect(PLACEHOLDER_DASH).toBe('—');
    expect(GENERIC_ERROR_MESSAGE).toBe('Something went wrong. Please try again.');
    expect(NOT_FOUND_TITLE).toBe('Page not found');
  });
});
