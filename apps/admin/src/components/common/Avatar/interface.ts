import type { ReactNode } from 'react';

export interface AvatarProps {
  alt?: string;
  /** Nullable to accept `MeDto['avatar_url']` directly — falls back to `children`. */
  src?: string | null;
  children?: ReactNode;
  // WR-66 (6R task-11, Minor): lets a caller hide a purely-decorative avatar (e.g. one already
  // paired with adjacent visible name text) from the accessibility tree, so screen readers don't
  // announce the name twice.
  'aria-hidden'?: boolean;
}
