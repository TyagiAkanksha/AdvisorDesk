import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { useSnackbar } from '@/components/common';
import { useDeleteContentMutation } from '@/lib/api/contentApi';
import { CONTENT_DELETED_MESSAGE, DELETE_ERROR_FALLBACK } from '@/lib/copy';
import { extractErrorMessage } from '@/lib/errorMessage';

// hygiene t07: the editor's delete confirmation (dialog state, in-dialog error, the DELETE,
// the "Deleted" notice and the redirect) is one self-contained state machine, moved out of
// `useContentEditor` UNCHANGED. It is deliberately not a `withFeedback` caller: a delete
// failure stays inside the open dialog (`deleteError`), it never becomes a snackbar.
export interface UseDeleteDialogResult {
  isDeleting: boolean;
  deleteDialogOpen: boolean;
  deleteError: string | null;
  openDeleteDialog: () => void;
  closeDeleteDialog: () => void;
  confirmDelete: () => void;
}

export function useDeleteDialog(contentId?: string): UseDeleteDialogResult {
  const router = useRouter();
  const { success: notifySuccess } = useSnackbar();
  const [deleteContentMutation, { isLoading: isDeleting }] = useDeleteContentMutation();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const openDeleteDialog = () => {
    setDeleteError(null);
    setDeleteDialogOpen(true);
  };

  const closeDeleteDialog = () => {
    setDeleteDialogOpen(false);
    setDeleteError(null);
  };

  const confirmDelete = () => {
    if (!contentId) {
      return;
    }
    setDeleteError(null);
    void deleteContentMutation(contentId)
      .unwrap()
      .then(() => {
        setDeleteDialogOpen(false);
        notifySuccess(CONTENT_DELETED_MESSAGE);
        router.push('/content');
      })
      .catch((error: unknown) => {
        setDeleteError(extractErrorMessage(error, DELETE_ERROR_FALLBACK));
      });
  };

  return {
    isDeleting,
    deleteDialogOpen,
    deleteError,
    openDeleteDialog,
    closeDeleteDialog,
    confirmDelete,
  };
}
