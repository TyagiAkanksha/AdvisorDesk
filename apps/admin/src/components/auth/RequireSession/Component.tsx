'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { ErrorState, LoadingIndicator } from '@/components/common';
import { useGetMeQuery } from '@/lib/api/authApi';

import type { RequireSessionProps } from './interface';

// Final review, finding F4 (t04 M2 root-fix): a query error here used to
// redirect to /signin unconditionally (`isError` covers a network outage /
// 500 exactly the same as a real 401) — an API outage looked identical to
// being signed out. Only a genuinely 401-shaped `FetchBaseQueryError`
// (`GET /auth/me`'s one documented error status, per the OpenAPI contract)
// means "not authenticated"; anything else renders `ErrorState` instead.
function isUnauthorized(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'status' in error && error.status === 401;
}

// task-04 / PRD §5.1: gates its children on `GET /auth/me`.
export default function Component({ children }: RequireSessionProps) {
  const router = useRouter();
  const { data, isLoading, isError, error } = useGetMeQuery();
  const unauthorized = isError && isUnauthorized(error);

  useEffect(() => {
    if (unauthorized) {
      router.replace('/signin');
    }
  }, [unauthorized, router]);

  // Final review, finding F5 (t04 M1): a visible loading indicator (§9 —
  // never a silent blank region) instead of `null` while the session query
  // is in flight. The pinned test for this state only asserts children are
  // absent and no redirect fired, which a spinner satisfies just as well.
  if (isLoading) {
    return <LoadingIndicator />;
  }

  if (isError) {
    // The 401 case redirects via the effect above. hygiene final B6: never a silent blank
    // region (§9) — now that the shell renders around this gate, a spinner stays visible in
    // <main> while that navigation is in flight, instead of rendering nothing.
    if (unauthorized) {
      return <LoadingIndicator />;
    }
    return <ErrorState message="Couldn't verify your session. Please try again." />;
  }

  if (!data) {
    return <LoadingIndicator />;
  }

  return <>{children}</>;
}
