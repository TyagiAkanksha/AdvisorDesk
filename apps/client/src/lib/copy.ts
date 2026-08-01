// Shared, friendly UI copy (docs/FRONTEND-CONVENTIONS.md §9: "Placeholder copy... comes from one
// typed module per app, not inline string literals"). task-05 review round 1, M-6:
// `common/ErrorState`'s default message and `useChatStream`'s generic stream-failure message
// were two independently-authored copies of the same sentence — this is their one shared home.
export const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';
