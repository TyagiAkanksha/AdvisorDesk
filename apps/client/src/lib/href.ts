/**
 * Whether an `href` should be routed through `next/link` (client-side navigation).
 *
 * Internal = an absolute path on this app (`/content`, `/`), which is exactly what next/link
 * accepts. Everything else — an absolute URL (`https://…`), a protocol-relative URL
 * (`//host/x`, which also starts with `/`), `mailto:`, a bare fragment or a relative path —
 * renders as a plain `<a>` so the browser does a real navigation.
 *
 * Twin: apps/{admin,client}/src/lib/href.ts must stay byte-identical (`href.twin.test.ts`).
 */
export function isInternalHref(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//');
}
