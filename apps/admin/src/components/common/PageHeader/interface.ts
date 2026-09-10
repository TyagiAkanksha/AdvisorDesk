import type { ReactNode } from 'react';
export interface PageHeaderProps {
  title: string;
  description?: string;
  /** Right-aligned actions (buttons); they wrap under the title below the sm breakpoint. */
  actions?: ReactNode;
  /** Secondary line under the title — e.g. a status chip and dates (editor, DESIGN.md §C5). */
  meta?: ReactNode;
}
