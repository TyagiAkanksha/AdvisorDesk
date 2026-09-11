import type { Metadata } from 'next';

import { SignInScreen } from '@/components/auth/SignInScreen';

interface PageProps {
  searchParams: Promise<{ error?: string | string[] }>;
}

export const metadata: Metadata = { title: 'Sign in' };

// phase-8 task-16 (DESIGN.md §C2): the `?error=` reason task 13's API redirect carries is read
// here (a Server Component) and passed down as a prop — `useSearchParams()` in the screen would
// force a Suspense boundary and make the screen a client island for no gain. A repeated
// `?error=` (string[]) is treated as absent.
export default async function Page({ searchParams }: PageProps) {
  const { error } = await searchParams;
  return <SignInScreen error={typeof error === 'string' ? error : undefined} />;
}
