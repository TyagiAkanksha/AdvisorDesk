import { useState } from 'react';

import type { ContentDto } from '@/types/api/content';

// hygiene t06 M6 (phase-8 t18 review): the delete-confirmation state machine, lifted out of
// ContentListScreen/Component.tsx so that file is composition only
// (docs/FRONTEND-CONVENTIONS.md §3). The mutation itself, the "Deleted" notice and
// `deleteError` stay in `useContentList` — this hook only decides WHICH row is pending and
// WHEN the dialog is open, and it is handed the two callbacks it drives.
export interface UseDeleteConfirmationArgs {
  /** `useContentList().deleteContent` — owns the mutation, the "Deleted" notice and `deleteError`. */
  deleteContent: (id: string) => Promise<void>;
  /** `useContentList().clearDeleteError`. */
  clearDeleteError: () => void;
}

export interface UseDeleteConfirmationResult {
  /** The row awaiting confirmation, or `null` when the dialog is closed. */
  target: ContentDto | null;
  isOpen: boolean;
  open: (item: ContentDto) => void;
  close: () => void;
  /** Resolves either way: a failure is swallowed here and surfaced by `deleteError` inside the
   *  still-open dialog (unchanged from today's `Component.tsx` catch). */
  confirm: () => Promise<void>;
}

export function useDeleteConfirmation({
  deleteContent,
  clearDeleteError,
}: UseDeleteConfirmationArgs): UseDeleteConfirmationResult {
  const [target, setTarget] = useState<ContentDto | null>(null);

  const open = (item: ContentDto) => {
    clearDeleteError();
    setTarget(item);
  };

  const close = () => {
    setTarget(null);
    clearDeleteError();
  };

  const confirm = async () => {
    if (!target) {
      return;
    }
    try {
      await deleteContent(target.id);
      setTarget(null);
    } catch {
      // `deleteError` (from useContentList) surfaces the failure inside the still-open
      // ConfirmDialog — the admin can retry immediately or cancel.
    }
  };

  return { target, isOpen: target !== null, open, close, confirm };
}
