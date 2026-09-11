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

// phase-8 task-17 (DESIGN.md §2, §5 C3): dashboard panel titles, empty/error copy.
// `DASHBOARD_TITLE` already exists above (task-15 — nav label = page title).
export const CONTENT_BY_TAG_TITLE = 'Content by tag';
export const RECENT_CONTENT_TITLE = 'Recent content';
export const NO_TAGS_MESSAGE = 'No tags yet.';
export const NO_RECENT_CONTENT_MESSAGE = 'No content yet.';
export const DASHBOARD_LOAD_ERROR = "Couldn't load the dashboard stats.";
export const DASHBOARD_REFRESH_ERROR =
  "Couldn't refresh the dashboard — showing the last loaded data.";
export const RECENT_CONTENT_LOAD_ERROR = "Couldn't load recent content.";

// phase-8 task-18 (DESIGN.md §2, §5 C4): content-list screen copy — URL-synced filters, empty
// states, delete feedback. `CONTENT_TITLE` (task-15) is reused as this screen's PageHeader title.
export const NEW_CONTENT_LABEL = 'New content';
export const CLEAR_FILTERS_LABEL = 'Clear filters';
export const CONTENT_TABLE_LABEL = 'Content';
export const NO_CONTENT_TITLE = 'No content yet';
export const NO_CONTENT_DESCRIPTION = 'Articles you create will show up here.';
export const CREATE_FIRST_ARTICLE_LABEL = 'Create your first article';
export const NO_MATCH_TITLE = 'No content matches these filters';
export const NO_MATCH_DESCRIPTION = 'Try a different status, tag or search term.';
export const CONTENT_LOAD_ERROR = "Couldn't load content.";
export const CONTENT_REFRESH_ERROR = "Couldn't refresh this list — showing the last loaded page.";
export const CONTENT_DELETED_MESSAGE = 'Deleted';
export const DELETE_ERROR_FALLBACK = "Couldn't delete this item. Please try again.";
// tooltip here; the editor's phone toggle + Delete button reuse these (task 20)
export const EDIT_LABEL = 'Edit';
export const DELETE_LABEL = 'Delete';
