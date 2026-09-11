'use client';

import MuiIconButton from '@mui/material/IconButton';
import MuiTooltip from '@mui/material/Tooltip';
import Link from 'next/link';

import { Icon } from '../Icon';
import type { IconButtonProps } from './interface';

// phase-8 task-14: same `isInternalHref` precedent as `common/Button` — an internal `href`
// (starts with `/`, e.g. a row's "Edit" action) renders via next/link's `Link` for client-side
// navigation; an external `href` falls through to MUI's own plain `<a>` (href without
// `component`). `'use client'` is required the moment a Server Component call site passes
// `Link` (a function) as `component` into MUI's `'use client'` IconButton — same reasoning as
// `common/Button`'s `'use client'`.
function isInternalHref(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//');
}

export default function Component({
  name,
  label,
  onClick,
  size = 'medium',
  disabled,
  href,
  color = 'default',
  edge,
  tooltip,
}: IconButtonProps) {
  // Three-way branch (not `href ? (internal ? A : B) : ...` collapsed into two) so TypeScript
  // narrows `href` to a plain `string` inside the two href branches — `IconButton`, unlike
  // `common/Button`, doesn't declare its own optional `href` prop, so MUI's typings only accept
  // `href` as either a REQUIRED string (no `component`) or alongside a required `component`;
  // passing `href={href}` while its type is still `string | undefined` fails both overloads.
  const button = !href ? (
    <MuiIconButton
      aria-label={label}
      onClick={onClick}
      size={size}
      disabled={disabled}
      color={color}
      edge={edge}
    >
      <Icon name={name} size={size} />
    </MuiIconButton>
  ) : isInternalHref(href) ? (
    <MuiIconButton
      component={Link}
      href={href}
      aria-label={label}
      onClick={onClick}
      size={size}
      disabled={disabled}
      color={color}
      edge={edge}
    >
      <Icon name={name} size={size} />
    </MuiIconButton>
  ) : (
    <MuiIconButton
      href={href}
      aria-label={label}
      onClick={onClick}
      size={size}
      disabled={disabled}
      color={color}
      edge={edge}
    >
      <Icon name={name} size={size} />
    </MuiIconButton>
  );

  return tooltip ? <MuiTooltip title={tooltip}>{button}</MuiTooltip> : button;
}
