// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Autocomplete } from '.';

describe('Autocomplete', () => {
  it('offers the provided options in the popup and commits a picked one', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Autocomplete
        label="Tags"
        value={[]}
        onChange={onChange}
        options={['retirement', 'tax-planning']}
      />,
    );

    await user.click(screen.getByRole('combobox', { name: 'Tags' }));
    await user.click(await screen.findByRole('option', { name: 'retirement' }));

    expect(onChange).toHaveBeenLastCalledWith(['retirement']);
  });

  it('still accepts free text with Enter when options are given', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Autocomplete label="Tags" value={[]} onChange={onChange} options={['retirement']} />);

    await user.type(screen.getByRole('combobox', { name: 'Tags' }), 'estate{Enter}');

    expect(onChange).toHaveBeenLastCalledWith(['estate']);
  });
});
