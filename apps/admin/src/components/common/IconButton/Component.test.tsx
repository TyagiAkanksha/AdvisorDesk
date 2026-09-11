// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { IconButton } from '.';

describe('IconButton', () => {
  it('with href renders a link carrying the accessible name', () => {
    render(<IconButton name="Edit" label="Edit Roth IRA Conversion Basics" href="/content/1" />);

    const link = screen.getByRole('link', { name: 'Edit Roth IRA Conversion Basics' });
    expect(link).toHaveAttribute('href', '/content/1');
  });

  it('with onClick renders a button that fires the handler', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<IconButton name="Delete" label="Delete Foo" onClick={onClick} />);

    await user.click(screen.getByRole('button', { name: 'Delete Foo' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('color="inherit" and edge="start" reach MUI (AppBar menu-button idiom)', () => {
    render(
      <IconButton
        name="Menu"
        label="Open navigation"
        onClick={() => {}}
        color="inherit"
        edge="start"
      />,
    );

    const button = screen.getByRole('button', { name: 'Open navigation' });
    expect(button).toHaveClass('MuiIconButton-colorInherit');
    expect(button).toHaveClass('MuiIconButton-edgeStart');
  });

  it('tooltip shows on hover while the label stays the accessible name', async () => {
    const user = userEvent.setup();
    render(<IconButton name="Delete" label="Delete Foo" onClick={() => {}} tooltip="Delete" />);

    const button = screen.getByRole('button', { name: 'Delete Foo' });
    await user.hover(button);

    expect(await screen.findByRole('tooltip')).toHaveTextContent('Delete');
    expect(button).toHaveAccessibleName('Delete Foo');
  });
});
