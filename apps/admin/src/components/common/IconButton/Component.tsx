import MuiIconButton from '@mui/material/IconButton';

import { Icon } from '../Icon';
import type { IconButtonProps } from './interface';

export default function Component({
  name,
  label,
  onClick,
  size = 'medium',
  disabled,
}: IconButtonProps) {
  return (
    <MuiIconButton aria-label={label} onClick={onClick} size={size} disabled={disabled}>
      <Icon name={name} size={size} />
    </MuiIconButton>
  );
}
