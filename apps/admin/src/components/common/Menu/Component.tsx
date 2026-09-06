import MuiMenu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';

import type { MenuProps } from './interface';

export default function Component({ anchorEl, open, onClose, options, id }: MenuProps) {
  return (
    <MuiMenu id={id} anchorEl={anchorEl} open={open} onClose={onClose}>
      {options.map((option) => (
        <MenuItem
          key={option.label}
          onClick={() => {
            option.onSelect();
            onClose();
          }}
        >
          {option.label}
        </MenuItem>
      ))}
    </MuiMenu>
  );
}
