import MuiTextField from '@mui/material/TextField';
import type { ChangeEvent, KeyboardEvent } from 'react';

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
      disabled={disabled}
      fullWidth={fullWidth}
      multiline={multiline}
      minRows={minRows}
      maxRows={maxRows}
      onKeyDown={onKeyDown ? handleKeyDown : undefined}
      inputRef={inputRef}
      size="small"
    />
  );
}
