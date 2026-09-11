import MuiTextField from '@mui/material/TextField';
import type { ChangeEvent } from 'react';

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
      onKeyDown={onKeyDown}
      // Inline style (not `sx`'s nested-selector rule) because it's deterministic under both
      // jsdom's cross-stylesheet cascade — AppRouterCacheProvider emits one `<style>` per rule,
      // which jsdom's getComputedStyle doesn't resolve for nested selectors — and real browsers.
      // Visually identical either way.
      slotProps={monospace ? { htmlInput: { style: { fontFamily: 'monospace' } } } : undefined}
    />
  );
}
