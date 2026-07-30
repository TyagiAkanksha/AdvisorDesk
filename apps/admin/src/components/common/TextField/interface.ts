/** A labeled, generic text input (docs/FRONTEND-CONVENTIONS.md §4). */
export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  size?: 'small' | 'medium';
  fullWidth?: boolean;
  type?: 'text' | 'search';
}
