'use client';

import MuiIconButton from '@mui/material/IconButton';
import MuiTooltip from '@mui/material/Tooltip';
import Link from 'next/link';

import { isInternalHref } from '@/lib/href';

import { Icon } from '../Icon';
import type { IconButtonProps } from './interface';

// The internal/external split is `isInternalHref` (src/lib/href.ts, hygiene t02). `'use client'`
// is required the moment a Server Component call site passes `Link` (a function) as `component`
// into MUI's `'use client'` IconButton — same reasoning as `common/Button`'s `'use client'`.
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
  // phase-8 task-14 fix round 1 (Minor): the six props every branch shares, spread into each —
  // keeps the three-way structure below (still needed for TS narrowing, see its comment) from
  // repeating them.
  const commonProps = {
    'aria-label': label,
    onClick,
    size,
    disabled,
    color,
    edge,
  };

  // Three-way branch (not `href ? (internal ? A : B) : ...` collapsed into two) so TypeScript
  // narrows `href` to a plain `string` inside the two href branches — `IconButton`, unlike
  // `common/Button`, doesn't declare its own optional `href` prop, so MUI's typings only accept
  // `href` as either a REQUIRED string (no `component`) or alongside a required `component`;
  // passing `href={href}` while its type is still `string | undefined` fails both overloads.
  const button = !href ? (
    <MuiIconButton {...commonProps}>
      <Icon name={name} size={size} />
    </MuiIconButton>
  ) : isInternalHref(href) ? (
    <MuiIconButton component={Link} href={href} {...commonProps}>
      <Icon name={name} size={size} />
    </MuiIconButton>
  ) : (
    <MuiIconButton href={href} {...commonProps}>
      <Icon name={name} size={size} />
    </MuiIconButton>
  );

  return tooltip ? <MuiTooltip title={tooltip}>{button}</MuiTooltip> : button;
}
