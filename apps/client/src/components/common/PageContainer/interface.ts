import type { ReactNode } from 'react';

// phase-8 task-06: `PageContainer` gains a `maxWidth` choice (it previously hardcoded `'lg'`
// with no `interface.ts` — see docs/FRONTEND-CONVENTIONS.md §3, "zero-prop components have no
// interface.ts").
export interface PageContainerProps {
  children: ReactNode;
  /** Reading width: 'md' (900px) for articles and chat, 'lg' (default) for lists. */
  maxWidth?: 'sm' | 'md' | 'lg';
}
