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

// phase-8 task-08 (DESIGN.md §B1): site shell copy — nav labels and the PRD §8 disclaimer.
export const NAV_ARTICLES_LABEL = 'Articles';
export const NAV_ASK_LABEL = 'Ask a question';
/** PRD §8 verbatim — the seed-content disclaimer, shown in the footer and on every article. */
export const DISCLAIMER = 'Sample content for demonstration purposes — not financial advice.';

// phase-8 task-09 (DESIGN.md §B2): home page header, tag filter, and empty-state copy.
export const HOME_TITLE = 'Articles';
export const HOME_DESCRIPTION =
  'Plain-English explainers on retirement, insurance, taxes and college savings.';
export const HOME_CTA_LABEL = 'Ask a question';
export const ALL_TAGS_LABEL = 'All';
export const NO_CONTENT_MESSAGE = 'No published content yet.';
export const SHOW_ALL_LABEL = 'Show all';
export function noArticlesTaggedMessage(tag: string): string {
  return `No articles tagged '${tag}'.`;
}

// phase-8 task-10 (DESIGN.md §B3): article reading layout — related-articles section heading
// and the chat CTA label.
export const RELATED_ARTICLES_TITLE = 'Related articles';
export const ASK_ABOUT_TOPIC_LABEL = 'Ask a question about this topic';

// phase-8 task-12 (DESIGN.md §B4): chat screen — welcome state, Sources list, and composer copy.
export const CHAT_TITLE = 'Ask a question';
export const CHAT_DESCRIPTION = 'Answers come from the published articles and cite their sources.';
export const SUGGESTED_QUESTIONS = [
  'When can I withdraw from a Roth IRA without penalty?',
  'How does Medicare enrollment work if I am still employed at 65?',
  'What is the difference between a 529 plan and a UTMA account?',
  'Do I need umbrella insurance?',
] as const;
export const THINKING_LABEL = 'Thinking…';
export const SOURCES_LABEL = 'Sources';
export const MESSAGE_FIELD_LABEL = 'Message';
export const SEND_LABEL = 'Send';
export const STOP_LABEL = 'Stop';
export const NEW_CONVERSATION_LABEL = 'New conversation';
export const CHAT_HELPER_TEXT =
  'Educational answers grounded in the published articles — not financial advice.';
