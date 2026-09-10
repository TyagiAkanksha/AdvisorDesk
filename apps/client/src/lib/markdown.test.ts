import { describe, expect, it } from 'vitest';

import { stripLeadingHeading } from './markdown';

// phase-8 task-03 (DESIGN.md §A2): every CMS body starts with `# <title>` while the screen
// renders the title itself — `stripLeadingHeading` removes that first heading (case/whitespace
// insensitive, trailing `#`s ignored) and the blank lines after it. Anything else is unchanged.
// `./markdown` does not exist yet — this import fails to resolve, the expected RED (test-author
// brief STOP RULE).
describe('stripLeadingHeading', () => {
  it('removes a first-line `# Title` that matches the title and the blank lines after it', () => {
    expect(stripLeadingHeading('# Medicare Basics\n\nBody text.', 'Medicare Basics')).toBe(
      'Body text.',
    );
  });

  it('matches case- and whitespace-insensitively and ignores closing hashes', () => {
    expect(stripLeadingHeading('#   medicare BASICS  ##\nBody.', ' Medicare Basics ')).toBe(
      'Body.',
    );
  });

  it('leaves the body alone when the first heading is a different title', () => {
    const body = '# Something Else\n\nBody.';
    expect(stripLeadingHeading(body, 'Medicare Basics')).toBe(body);
  });

  it('leaves the body alone when it does not start with an h1', () => {
    expect(stripLeadingHeading('Intro\n\n# Medicare Basics', 'Medicare Basics')).toBe(
      'Intro\n\n# Medicare Basics',
    );
    expect(stripLeadingHeading('## Medicare Basics\nBody.', 'Medicare Basics')).toBe(
      '## Medicare Basics\nBody.',
    );
  });

  it('handles a body that is only the heading, and an empty body', () => {
    expect(stripLeadingHeading('# Medicare Basics', 'Medicare Basics')).toBe('');
    expect(stripLeadingHeading('', 'Medicare Basics')).toBe('');
  });
});
