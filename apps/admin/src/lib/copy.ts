// Shared, friendly UI copy (docs/FRONTEND-CONVENTIONS.md §9: placeholder and user-facing strings
// come from one typed module per app). Mirrors apps/client/src/lib/copy.ts. phase-8 task-07.
// phase-8 task-14: APP_NAME owns the wordmark text used by AppShell and SignInScreen.
export const APP_NAME = 'AdvisorDesk Admin';
export const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';
export const NOT_FOUND_TITLE = 'Page not found';
export const NOT_FOUND_MESSAGE = 'The page you’re looking for doesn’t exist or has been removed.';
export const BACK_TO_DASHBOARD_LABEL = 'Back to dashboard';
export const PLACEHOLDER_DASH = '—';

// p8 final: a11y region labels for MarkdownPreview's code-block and table wrappers (both apps —
// identical names keep the Markdown twin byte-identical).
export const MARKDOWN_CODE_BLOCK_LABEL = 'Code block';
export const MARKDOWN_TABLE_LABEL = 'Table';

// p8 final: `PageSkeleton`'s `role="status"` label (mirrors apps/client's ChatSkeleton and
// existing skeletons).
export const LOADING_LABEL = 'Loading';
