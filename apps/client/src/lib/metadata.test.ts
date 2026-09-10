import { describe, expect, it } from 'vitest';

import { rootMetadata, SITE_NAME } from './metadata';

describe('root metadata', () => {
  it('gives every page a "<page> · AdvisorDesk" title through one template', () => {
    expect(SITE_NAME).toBe('AdvisorDesk');
    expect(rootMetadata.title).toEqual({ default: 'AdvisorDesk', template: '%s · AdvisorDesk' });
  });
});
