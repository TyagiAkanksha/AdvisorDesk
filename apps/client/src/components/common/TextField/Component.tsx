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
  multiline,
  minRows,
  maxRows,
  onKeyDown,
  inputRef,
}: TextFieldProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
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
      multiline={multiline}
      minRows={minRows}
      maxRows={maxRows}
      onKeyDown={onKeyDown}
      inputRef={inputRef}
      size="small"
    />
  );
}
