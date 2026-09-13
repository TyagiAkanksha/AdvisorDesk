import MuiIconButton from '@mui/material/IconButton';

import { Icon } from '../Icon';
import type { IconButtonProps } from './interface';

export default function Component({
  name,
  label,
  onClick,
  type = 'button',
  size = 'medium',
  color = 'default',
  disabled,
  pressed,
}: IconButtonProps) {
  return (
    <MuiIconButton
      aria-label={label}
      aria-pressed={pressed}
      onClick={onClick}
      type={type}
      size={size}
      color={color}
      disabled={disabled}
      // phase-9 task-17: `ButtonBase` sets `pointer-events: none` on `.Mui-disabled`. A real
      // browser never dispatches `click` on a disabled native `<button>` regardless of this CSS
      // (that's native `disabled` semantics, not `pointer-events`), so restoring `auto` changes no
      // real click-through behavior — it only keeps a disabled *toggle* button (e.g.
      // `FeedbackButtons` mid-request) a valid `@testing-library/user-event` target, so a simulated
      // click on it resolves to the library's own "disabled form control swallows the click" no-op
      // instead of its unrelated pointer-events guard throwing first.
      sx={{ '&.Mui-disabled': { pointerEvents: 'auto' } }}
    >
      <Icon name={name} size={size} />
    </MuiIconButton>
  );
}
