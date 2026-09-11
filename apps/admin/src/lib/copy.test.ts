import { describe, expect, it } from 'vitest';

import { APP_NAME, GENERIC_ERROR_MESSAGE, NOT_FOUND_TITLE, PLACEHOLDER_DASH } from './copy';

describe('admin copy module', () => {
  it('owns the shared placeholder and error strings', () => {
    expect(PLACEHOLDER_DASH).toBe('—');
    expect(GENERIC_ERROR_MESSAGE).toBe('Something went wrong. Please try again.');
    expect(NOT_FOUND_TITLE).toBe('Page not found');
  });

  it('owns the app name used by the shell wordmark and the sign-in card', () => {
    expect(APP_NAME).toBe('AdvisorDesk Admin');
  });
});
