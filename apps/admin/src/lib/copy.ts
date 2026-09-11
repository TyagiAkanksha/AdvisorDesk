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

// p8 final, F14: filter-row field labels/placeholder + "all" option labels (`ContentFilters`,
// `ContentListScreen`'s tag-option list) and the delete-content confirm dialog's copy — extracted
// out of the components' own inline string literals into this one typed module (both apps' own
// `docs/FRONTEND-CONVENTIONS.md §9` rule). Rendered text is unchanged.
export const STATUS_FILTER_LABEL = 'Status';
export const TAG_FILTER_LABEL = 'Tag';
export const SEARCH_FILTER_LABEL = 'Search';
export const SEARCH_PLACEHOLDER = 'Search by title…';
export const ALL_STATUSES_LABEL = 'All statuses';
export const ALL_TAGS_LABEL = 'All tags';
export const DELETE_CONTENT_DIALOG_TITLE = 'Delete content';
export function deleteContentDialogBody(title: string): string {
  return `“${title}” will be permanently deleted — there is no restore.`;
}

// phase-8 task-19 (DESIGN.md §5 C5): editor hook — title validation + mutation feedback copy
// (the four hook-local fallbacks move here too: SAVE_ERROR_FALLBACK, TRANSITION_ERROR_FALLBACK,
// EDITOR_REFRESH_ERROR, EDITOR_LOAD_ERROR). `CONTENT_DELETED_MESSAGE`/`DELETE_ERROR_FALLBACK`
// above (task-18) are reused as-is for the editor's own Delete feedback.
export const TITLE_REQUIRED_MESSAGE = 'Title is required';
export const CONTENT_SAVED_MESSAGE = 'Saved';
export const CONTENT_PUBLISHED_MESSAGE = 'Published';
export const CONTENT_ARCHIVED_MESSAGE = 'Archived';
export const SAVE_ERROR_FALLBACK = "Couldn't save this item. Please try again.";
export const TRANSITION_ERROR_FALLBACK = "Couldn't update this item's status. Please try again.";
export const EDITOR_REFRESH_ERROR = "Couldn't refresh this item — showing the last loaded version.";
export const EDITOR_LOAD_ERROR = "Couldn't load this item.";

// phase-8 task-20 (DESIGN.md §5 C5): editor screen copy — header meta prefixes, form field
// labels, action row labels, and the disabled-Publish tooltip reasons.
export const PREVIEW_LABEL = 'Preview';
// p8 final, F17: shown in place of the Markdown preview once the body (title heading stripped)
// has nothing left to render — an explicit empty state (DESIGN.md §2) instead of a blank panel.
export const PREVIEW_EMPTY_MESSAGE = 'Nothing to preview yet.';
export const TITLE_FIELD_LABEL = 'Title';
export const BODY_FIELD_LABEL = 'Body (Markdown)';
export const TAGS_FIELD_LABEL = 'Tags';
export const PUBLISH_LABEL = 'Publish';
export const ARCHIVE_LABEL = 'Archive';
export const PUBLISH_SAVE_FIRST_TOOLTIP = 'Save first';
export const PUBLISH_ALREADY_TOOLTIP = 'Already published';
export const META_CREATED_PREFIX = 'Created';
export const META_UPDATED_PREFIX = 'Updated';
export const META_PUBLISHED_PREFIX = 'Published';

// phase-8 task-21 (DESIGN.md §2, §5 C6): connected-apps screen copy — header description, table
// label, empty state, and revoke/refresh feedback. `CONNECTED_APPS_TITLE` already exists above
// (task-15 — nav label = page title).
export const CONNECTED_APPS_DESCRIPTION =
  'Apps authorised to use AdvisorDesk over MCP (for example Claude). Revoking removes their access immediately.';
export const CONNECTED_APPS_TABLE_LABEL = 'Connected apps';
export const NO_CONNECTED_APPS_TITLE = 'No connected apps';
export const NO_CONNECTED_APPS_DESCRIPTION =
  'Apps that connect over MCP (like Claude) will appear here after you approve them.';
export const REVOKE_LABEL = 'Revoke';
export const REVOKE_DIALOG_TITLE = 'Revoke access?';
// p8 final, F14: extracted out of ConnectedAppsScreen's own inline template literal.
export function revokeDialogBody(name: string): string {
  return `${name} will lose MCP access immediately. It can reconnect later by authorizing again.`;
}
export const ACCESS_REVOKED_MESSAGE = 'Access revoked';
export const CONNECTED_APPS_LOAD_ERROR = "Couldn't load connected apps.";
export const CONNECTED_APPS_REFRESH_ERROR =
  "Couldn't refresh connected apps — showing the last loaded list.";
export const REVOKE_ERROR_FALLBACK = "Couldn't revoke this app. Please try again.";

// phase-8 task-23 (DESIGN.md §5 C7): agent panel — header, empty-state suggestions, composer
// helper line, and ToolCallCard's collapsed-row copy.
export const AGENT_PANEL_TITLE = 'Agent';
export const AGENT_CLEAR_LABEL = 'Clear';
export const AGENT_CLOSE_LABEL = 'Close agent panel';
export const AGENT_EMPTY_TITLE = 'Ask the agent to work on your content';
export const AGENT_EMPTY_DESCRIPTION =
  'It can draft, tag, publish and search articles. Try one of these:';
export const AGENT_SUGGESTED_COMMANDS = [
  'Draft an article on Roth IRA conversion basics and tag it retirement.',
  'List the drafts tagged estate-planning.',
  'How many published articles do we have on tax planning?',
] as const;
export const AGENT_WORKING_LABEL = 'Working…';
export const AGENT_MESSAGE_LABEL = 'Message';
export const AGENT_SEND_LABEL = 'Send';
export const AGENT_STOP_LABEL = 'Stop';
export const AGENT_HELPER_TEXT = 'Enter to send · Shift+Enter for a new line';
export const TOOL_RUNNING_PREFIX = 'Running';
export const TOOL_RAN_PREFIX = 'Ran';
export const TOOL_ARGUMENTS_LABEL = 'Arguments';
export const TOOL_RESULT_LABEL = 'Result';
