import type { ICONS } from './Component';

/**
 * Icon wraps `@mui/icons-material` behind a stable contract
 * (docs/FRONTEND-CONVENTIONS.md §4).
 *
 * `name` is typed against `ICONS`, an explicit registry defined in `Component.tsx` —
 * deliberately NOT `keyof typeof import('@mui/icons-material')`. That package barrel-exports
 * ~2000 icon modules; `import * as icons from '@mui/icons-material'` would pull all of them
 * into the bundle graph and slow the TS language server. Add a named import + a registry
 * entry in `Component.tsx` when a screen needs an icon that isn't listed yet.
 */
export interface IconProps {
  /** Key into the Icon registry (see `ICONS` in `Component.tsx`), e.g. "Search", "Menu". */
  name: keyof typeof ICONS;
  /** Accessible name. Present -> `role="img"` + `aria-label`. Absent -> `aria-hidden="true"`. */
  label?: string;
  size?: 'small' | 'medium' | 'large';
  color?: string;
}
