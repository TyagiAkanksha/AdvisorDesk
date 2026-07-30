import type { ReactNode } from 'react';

export interface AvatarProps {
  alt?: string;
  /** Nullable to accept `MeDto['avatar_url']` directly — falls back to `children`. */
  src?: string | null;
  children?: ReactNode;
}
