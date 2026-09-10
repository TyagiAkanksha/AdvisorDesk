import { describe, expect, it } from 'vitest';

import { DISCLAIMER, NAV_ARTICLES_LABEL, NAV_ASK_LABEL } from './copy';

describe('client copy module', () => {
  it('owns the nav labels and the PRD §8 disclaimer verbatim', () => {
    expect(NAV_ARTICLES_LABEL).toBe('Articles');
    expect(NAV_ASK_LABEL).toBe('Ask a question');
    expect(DISCLAIMER).toBe('Sample content for demonstration purposes — not financial advice.');
  });
});
