import type { LinkProps as MuiLinkProps } from '@mui/material/Link';

/**
 * Link wraps `@mui/material/Link` behind a stable contract (docs/FRONTEND-CONVENTIONS.md §4).
 * `href` is required — this component always points somewhere, unlike MUI's own optional-href
 * Link. An INTERNAL `href` (starts with `/`, e.g. a content card linking to `/content/{slug}`)
 * renders via `next/link` for client-side navigation; an EXTERNAL `href` (e.g. a markdown link
 * to an outside URL) renders a plain `<a>` — same pattern as `apps/admin/src/components/common/
 * Button/Component.tsx`'s `isInternalHref` split. Either way the rendered element is an `<a>`
 * with the same accessible `link` role, name, and `href` attribute.
 */
export type LinkProps = MuiLinkProps & { href: string };
