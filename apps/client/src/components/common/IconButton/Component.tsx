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
}: IconButtonProps) {
  return (
    <MuiIconButton
      aria-label={label}
      onClick={onClick}
      type={type}
      size={size}
      color={color}
      disabled={disabled}
    >
      <Icon name={name} size={size} />
    </MuiIconButton>
  );
}
