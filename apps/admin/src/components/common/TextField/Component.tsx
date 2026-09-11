import MuiTextField from '@mui/material/TextField';
import type { ChangeEvent, KeyboardEvent } from 'react';

import type { TextFieldProps } from './interface';

export default function Component({
  label,
  value,
  onChange,
  placeholder,
  size = 'small',
  fullWidth,
  type = 'text',
  multiline,
  minRows,
  maxRows,
  disabled,
  required,
  error,
  helperText,
  onBlur,
  onKeyDown,
  monospace,
}: TextFieldProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    onChange(event.target.value);
  };

  // MuiTextField's own onKeyDown type is bound to its root element (`KeyboardEventHandler
  // <HTMLDivElement>`) even though the event genuinely originates on the inner
  // input/textarea; narrow it back to the public contract's declared target types.
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    onKeyDown?.(event as unknown as KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>);
  };

  return (
    <MuiTextField
      label={label}
      value={value}
      onChange={handleChange}
      placeholder={placeholder}
      size={size}
      fullWidth={fullWidth}
      type={type}
      multiline={multiline}
      minRows={minRows}
      maxRows={maxRows}
      disabled={disabled}
      required={required}
      error={error}
      helperText={helperText}
      onBlur={onBlur}
      onKeyDown={onKeyDown ? handleKeyDown : undefined}
      sx={monospace ? { '& .MuiInputBase-input': { fontFamily: 'monospace' } } : undefined}
    />
  );
}
