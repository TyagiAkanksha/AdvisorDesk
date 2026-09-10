// Shared, friendly UI copy (docs/FRONTEND-CONVENTIONS.md §9: "Placeholder copy... comes from one
// typed module per app, not inline string literals"). task-05 review round 1, M-6:
// `common/ErrorState`'s default message and `useChatStream`'s generic stream-failure message
// were two independently-authored copies of the same sentence — this is their one shared home.
export const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';

// phase-8 task-07: 404 and error-route copy (DESIGN.md §A4).
export const NOT_FOUND_TITLE = 'Page not found';
export const NOT_FOUND_MESSAGE = 'The page you’re looking for doesn’t exist or has been removed.';
export const BACK_TO_ARTICLES_LABEL = 'Back to articles';
export const PAGE_ERROR_MESSAGE = 'Something went wrong loading this page. Please try again.';
export const RETRY_LABEL = 'Try again';
