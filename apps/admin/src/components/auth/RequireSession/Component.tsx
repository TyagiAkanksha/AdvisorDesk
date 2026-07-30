'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { useGetMeQuery } from '@/lib/api/authApi';

import type { RequireSessionProps } from './interface';

// task-04 / PRD §5.1: gates its children on `GET /auth/me`. That endpoint
// only ever answers 200 (MeResponse) or 401 (ErrorEnvelope) per the OpenAPI
// contract, so any query error here is the unauthenticated case.
export default function Component({ children }: RequireSessionProps) {
  const router = useRouter();
  const { data, isLoading, isError } = useGetMeQuery();

  useEffect(() => {
    if (isError) {
      router.replace('/signin');
    }
  }, [isError, router]);

  if (isLoading || !data) {
    return null;
  }

  return <>{children}</>;
}
