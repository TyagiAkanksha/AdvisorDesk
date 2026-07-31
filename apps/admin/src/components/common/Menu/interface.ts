export interface MenuOption {
  label: string;
  onSelect: () => void;
}

/** Generic anchored dropdown menu (docs/FRONTEND-CONVENTIONS.md §4) — trigger
 * element + open state are owned by the caller; this wraps only the popup. */
export interface MenuProps {
  anchorEl: HTMLElement | null;
  open: boolean;
  onClose: () => void;
  options: MenuOption[];
}
