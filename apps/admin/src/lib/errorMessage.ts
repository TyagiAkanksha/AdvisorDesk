const DEFAULT_FALLBACK = "Couldn't complete this action. Please try again.";

interface EnvelopeError {
  data: {
    error: {
      message: string;
    };
  };
}

// Narrows an RTK Query mutation rejection down to the PRD §9 envelope shape
// (`{status,data:{error:{code,message}}}` for `FetchBaseQueryError`) without `any` —
// `SerializedError` (network failures, thrown-before-response errors) has no `data` field and
// falls through to the fallback.
function hasEnvelopeMessage(error: unknown): error is EnvelopeError {
  if (typeof error !== 'object' || error === null || !('data' in error)) {
    return false;
  }
  const { data } = error as { data: unknown };
  if (typeof data !== 'object' || data === null || !('error' in data)) {
    return false;
  }
  const { error: detail } = data as { error: unknown };
  if (typeof detail !== 'object' || detail === null || !('message' in detail)) {
    return false;
  }
  return typeof (detail as { message: unknown }).message === 'string';
}

/**
 * Maps a caught RTK Query mutation error (`FetchBaseQueryError | SerializedError`, from
 * `.unwrap()`'s rejection) to the PRD §9 envelope's `error.message` when the server sent one,
 * else a caller-supplied friendly fallback. Never surfaces a raw error body
 * (docs/FRONTEND-CONVENTIONS.md §9) — fix round 1, F2.
 */
export function extractErrorMessage(error: unknown, fallback: string = DEFAULT_FALLBACK): string {
  return hasEnvelopeMessage(error) ? error.data.error.message : fallback;
}
