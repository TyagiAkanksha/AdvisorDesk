import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import MuiSelect from '@mui/material/Select';
import type { SelectChangeEvent } from '@mui/material/Select';
import { useId } from 'react';

import type { SelectProps } from './interface';

export default function Component({
  label,
  value,
  onChange,
  options,
  size = 'small',
}: SelectProps) {
  const labelId = useId();

  const handleChange = (event: SelectChangeEvent) => {
    onChange(event.target.value);
  };

  return (
    <FormControl size={size} sx={{ minWidth: 160 }}>
      <InputLabel id={labelId}>{label}</InputLabel>
      <MuiSelect labelId={labelId} label={label} value={value} onChange={handleChange}>
        {options.map((option) => (
          <MenuItem key={option.value} value={option.value}>
            {option.label}
          </MenuItem>
        ))}
      </MuiSelect>
    </FormControl>
  );
}
