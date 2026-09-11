import { describe, expect, it } from 'vitest';

import { SIGN_IN_ERROR_FORBIDDEN, SIGN_IN_ERROR_STATE } from './copy';
import { signInErrorMessage } from './signInError';

describe('signInErrorMessage', () => {
  it('maps the two reasons the API sends', () => {
    expect(signInErrorMessage('forbidden')).toBe(SIGN_IN_ERROR_FORBIDDEN);
    expect(signInErrorMessage('state')).toBe(SIGN_IN_ERROR_STATE);
  });

  it('returns null for anything else', () => {
    expect(signInErrorMessage(undefined)).toBeNull();
    expect(signInErrorMessage('')).toBeNull();
    expect(signInErrorMessage('FORBIDDEN')).toBeNull();
    expect(signInErrorMessage('<script>')).toBeNull();
  });
});
