export interface SelectOption {
  value: string;
  label: string;
}

/** A labeled, generic single-select dropdown (docs/FRONTEND-CONVENTIONS.md §4). */
export interface SelectProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  size?: 'small' | 'medium';
}
