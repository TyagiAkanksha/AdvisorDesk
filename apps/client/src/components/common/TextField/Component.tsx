import MuiTextField from '@mui/material/TextField';
import type { ChangeEvent } from 'react';

import type { TextFieldProps } from './interface';

export default function Component({
  label,
  value,
  onChange,
  placeholder,
  disabled,
  fullWidth,
}: TextFieldProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    onChange(event.target.value);
  };

  return (
    <MuiTextField
      label={label}
      value={value}
      onChange={handleChange}
      placeholder={placeholder}
      disabled={disabled}
      fullWidth={fullWidth}
      size="small"
    />
  );
}
