/**
 * A labeled, generic freeSolo multi-value text input (docs/FRONTEND-CONVENTIONS.md §4).
 * task-06: backs the editor's Tags field — entry normalization (lowercase-hyphen) is a
 * caller/VM-hook concern, not this primitive's (components stay dumb, §3).
 */
export interface AutocompleteProps {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  size?: 'small' | 'medium';
  /** phase-8 task-14 (DESIGN.md §C5): suggestions shown in the popup; freeSolo stays on. */
  options?: string[];
}
