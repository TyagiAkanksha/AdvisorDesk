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

// phase-8 task-15 (DESIGN.md §C1): AppShell nav + chrome copy. One constant per nav item — the
// nav label IS the page title (tasks 17/18/21 reuse these as their PageHeader titles).
export const DASHBOARD_TITLE = 'Dashboard';
export const CONTENT_TITLE = 'Content';
export const CONNECTED_APPS_TITLE = 'Connected apps';
export const MAIN_NAV_LABEL = 'Main';
export const OPEN_NAVIGATION_LABEL = 'Open navigation';
export const AGENT_BUTTON_LABEL = 'Agent';
export const SIGN_OUT_LABEL = 'Sign out';

// phase-8 task-16 (DESIGN.md §C2): sign-in card copy, incl. the two `?error=` reasons task 13's
// API redirect can carry (see src/lib/signInError.ts).
export const SIGN_IN_SUBTITLE = 'Sign in to manage AdvisorDesk content';
export const SIGN_IN_BUTTON_LABEL = 'Sign in with Google';
export const SIGN_IN_FINE_PRINT = 'Access is limited to allowlisted admin accounts.';
export const SIGN_IN_ERROR_FORBIDDEN = "This Google account isn't on the admin allowlist.";
export const SIGN_IN_ERROR_STATE = 'Sign-in expired or was tampered with. Please try again.';
