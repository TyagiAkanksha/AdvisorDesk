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
//
// Fix round 1 (review finding #1, Important): the `onChange` wrapper below only clears
// `inputValue` for `reason === 'selectOption' | 'createOption'` — the two reasons where a value
// was actually just committed from what was typed (verified against MUI 9.2's own
// `useAutocomplete.js`: `resetInputValue` — which MUI calls internally for exactly these two
// reasons via `selectNewValue` — computes `newInputValue = ''` in multiple mode and fires our
// `onInputChange` with it BEFORE `onChange` runs, so this clear is a no-op in practice and exists
// only to make the intent explicit/robust to that internal ordering). Every other reason is left
// alone on purpose:
// - `'removeOption'` (chip delete via the × icon, or Backspace) never touches `inputValue` in
//   MUI itself (`handleValue` is called directly, bypassing `resetInputValue` entirely) —
//   clearing it here unconditionally (the pre-fix-round-1 bug) silently discarded whatever the
//   user was still mid-typing, the moment they deleted an unrelated, already-committed chip.
// - `'clear'` (the field's clear-all icon) already gets its own explicit
//   `onInputChange(event, '', 'clear')` from MUI's `handleClear`, so our `onInputChange` handler
//   below already clears it — no need to duplicate that here.
// - `'blur'` only reaches `onChange` at all when `autoSelect` is true (never set here); the
//   field's own blur-driven commit is `commitPendingInput` below — excluding `'blur'` here keeps
//   the two clear paths from fighting over the same state update.
export default function Component({
  label,
  value,
  onChange,
  size = 'small',
  options = [],
}: AutocompleteProps) {
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
      options={options}
      value={value}
      inputValue={inputValue}
      size={size}
      onChange={(_event, newValue, reason) => {
        onChange(newValue);
        if (reason === 'selectOption' || reason === 'createOption') {
          setInputValue('');
        }
      }}
      onInputChange={(_event, newInputValue) => setInputValue(newInputValue)}
      onBlur={commitPendingInput}
      renderInput={(params) => <MuiTextField {...params} label={label} />}
      sx={{ minWidth: 240 }}
    />
  );
}
