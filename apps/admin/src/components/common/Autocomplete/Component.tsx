'use client';

import MuiAutocomplete from '@mui/material/Autocomplete';
import MuiTextField from '@mui/material/TextField';
import { useState } from 'react';

import type { AutocompleteProps } from './interface';

// WR-11 (6R task-11, DATA LOSS): MUI's `useAutocomplete` only commits a freeSolo entry on blur
// when `autoSelect` is true (never passed here, library default `false`) — with `clearOnBlur`
// also `false` (its default is `!freeSolo`, and this field passes `freeSolo`), NEITHER of
// `handleBlur`'s branches fire, so text typed but never confirmed with Enter is silently absent
// from `value` (and therefore the caller's payload) while still visibly sitting in the field.
// Fix: track the live `inputValue` ourselves (controlled) and commit it into `value` on blur —
// the standard freeSolo "capture on blur" pattern.
export default function Component({ label, value, onChange, size = 'small' }: AutocompleteProps) {
  const [inputValue, setInputValue] = useState('');

  const commitPendingInput = () => {
    const trimmed = inputValue.trim();
    if (trimmed) {
      onChange([...value, trimmed]);
    }
    setInputValue('');
  };

  return (
    <MuiAutocomplete<string, true, false, true>
      multiple
      freeSolo
      options={[]}
      value={value}
      inputValue={inputValue}
      size={size}
      onChange={(_event, newValue) => {
        onChange(newValue);
        setInputValue('');
      }}
      onInputChange={(_event, newInputValue) => setInputValue(newInputValue)}
      onBlur={commitPendingInput}
      renderInput={(params) => <MuiTextField {...params} label={label} />}
      sx={{ minWidth: 240 }}
    />
  );
}
