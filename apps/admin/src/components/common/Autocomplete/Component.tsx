import MuiAutocomplete from '@mui/material/Autocomplete';
import MuiTextField from '@mui/material/TextField';

import type { AutocompleteProps } from './interface';

export default function Component({ label, value, onChange, size = 'small' }: AutocompleteProps) {
  return (
    <MuiAutocomplete<string, true, false, true>
      multiple
      freeSolo
      options={[]}
      value={value}
      size={size}
      onChange={(_event, newValue) => onChange(newValue)}
      renderInput={(params) => <MuiTextField {...params} label={label} />}
      sx={{ minWidth: 240 }}
    />
  );
}
