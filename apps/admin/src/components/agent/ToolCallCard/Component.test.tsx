// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ToolCallCard } from '.';

describe('ToolCallCard', () => {
  it('collapsed: "Running <tool>…" while there is no result', () => {
    render(
      <ToolCallCard
        segment={{ kind: 'tool', tool: 'search_content', args: '{"q":"roth"}', result: null }}
      />,
    );

    const toggle = screen.getByRole('button', { name: 'Running search_content…' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Arguments')).not.toBeInTheDocument();
  });

  it('collapsed: "Ran <tool> · <summary>"; expanding shows pretty-printed arguments and the result', async () => {
    const user = userEvent.setup();
    render(
      <ToolCallCard
        segment={{
          kind: 'tool',
          tool: 'create_draft',
          args: '{"title":"Roth IRA Conversion Basics","tags":["retirement"]}',
          result: 'Created draft d-42 (Roth IRA Conversion Basics).',
        }}
      />,
    );

    const toggle = screen.getByRole('button', {
      name: 'Ran create_draft · Created draft d-42 (Roth IRA Conversion Basics).',
    });
    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Arguments')).toBeInTheDocument();
    expect(screen.getByText(/"title": "Roth IRA Conversion Basics"/)).toBeInTheDocument();
    expect(screen.getByText('Result')).toBeInTheDocument();
    expect(
      screen.getByText('Created draft d-42 (Roth IRA Conversion Basics).', { selector: 'pre' }),
    ).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Arguments')).not.toBeInTheDocument();
  });

  it('shows unparsable arguments verbatim', async () => {
    const user = userEvent.setup();
    render(<ToolCallCard segment={{ kind: 'tool', tool: 't', args: 'not json', result: null }} />);

    await user.click(screen.getByRole('button'));

    expect(screen.getByText('not json')).toBeInTheDocument();
  });
});
