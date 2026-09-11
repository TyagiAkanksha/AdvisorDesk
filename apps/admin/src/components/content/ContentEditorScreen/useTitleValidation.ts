import { useState } from 'react';

import { TITLE_REQUIRED_MESSAGE } from '@/lib/copy';

// hygiene t07 (phase-8 t19 M2): the title field's validation state, lifted out of
// `useContentEditor` so that hook composes state machines instead of owning them
// (docs/FRONTEND-CONVENTIONS.md §3). Takes the ALREADY-TRIMMED title so "blank" is defined
// once, by the caller — `titleError`, `onSubmit`, `isDirty` and `canSubmit` all read the
// same definition.
export interface UseTitleValidationResult {
  titleError: string | null;
  onTitleBlur: () => void;
  markSubmitAttempted: () => void;
}

export function useTitleValidation(trimmedTitle: string): UseTitleValidationResult {
  const [titleBlurred, setTitleBlurred] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);

  return {
    titleError:
      (titleBlurred || submitAttempted) && trimmedTitle.length === 0
        ? TITLE_REQUIRED_MESSAGE
        : null,
    onTitleBlur: () => setTitleBlurred(true),
    markSubmitAttempted: () => setSubmitAttempted(true),
  };
}
