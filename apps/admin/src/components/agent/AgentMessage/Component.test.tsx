// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { AgentMessage } from '.';

describe('AgentMessage', () => {
  it('renders a user turn as an article named "You" preserving newlines', () => {
    render(<AgentMessage turn={{ role: 'user', text: 'line one\nline two', events: [] }} />);

    const article = screen.getByRole('article', { name: 'You' });
    expect(article).toHaveTextContent('line one line two');
    expect(within(article).getByText(/line one/)).toHaveStyle({ whiteSpace: 'pre-wrap' });
  });

  it('renders an assistant turn as markdown with tool cards between the text segments', () => {
    render(
      <AgentMessage
        turn={{
          role: 'assistant',
          text: 'Creating the **draft**. Done.',
          events: [
            { kind: 'call', tool: 'create_draft', detail: '{"title":"X"}', textOffset: 24 },
            { kind: 'result', tool: 'create_draft', detail: 'Created d-42.', textOffset: 24 },
          ],
        }}
      />,
    );

    const article = screen.getByRole('article', { name: 'Assistant' });
    expect(within(article).getByText('draft').tagName).toBe('STRONG');
    const text = article.textContent ?? '';
    expect(text.indexOf('Creating the draft.')).toBeGreaterThanOrEqual(0);
    expect(text.indexOf('Ran create_draft')).toBeGreaterThan(text.indexOf('Creating the draft.'));
    expect(text.indexOf('Done.')).toBeGreaterThan(text.indexOf('Ran create_draft'));
  });
});
