import MuiSkeleton from '@mui/material/Skeleton';

import type { SkeletonProps } from './interface';

export default function Component(props: SkeletonProps) {
  return <MuiSkeleton {...props} />;
}
