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

// p8 final: a11y region labels for Markdown's code-block and table wrappers (both apps —
// identical names keep the Markdown twin byte-identical).
export const MARKDOWN_CODE_BLOCK_LABEL = 'Code block';
export const MARKDOWN_TABLE_LABEL = 'Table';

// p8 final: `ChatSkeleton`'s `role="status"` label; also adopted by the three existing
// skeletons (ContentListSkeleton, ArticleSkeleton) in place of their literal.
export const LOADING_LABEL = 'Loading';
