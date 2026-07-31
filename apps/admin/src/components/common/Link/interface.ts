import type { LinkProps as MuiLinkProps } from '@mui/material/Link';

/**
 * Link wraps `@mui/material/Link` behind a stable contract (docs/FRONTEND-CONVENTIONS.md §4).
 * `href` is required — this component always points somewhere, unlike MUI's own optional-href
 * Link. An INTERNAL `href` (starts with `/`) renders via `next/link` for client-side
 * navigation; an EXTERNAL `href` renders a plain `<a>` — same `isInternalHref` split as this
 * app's own `common/Button/Component.tsx`. Either way the rendered element is an `<a>` with the
 * same accessible `link` role, name, and `href` attribute.
 *
 * Twin copy: apps/client/src/components/common/Link/interface.ts (task-04 — the two apps
 * deploy independently, so this primitive is duplicated rather than shared, same as theme.ts).
 */
export type LinkProps = MuiLinkProps & { href: string };
