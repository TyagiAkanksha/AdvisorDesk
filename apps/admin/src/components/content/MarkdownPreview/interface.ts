export type MarkdownVariant = 'article' | 'chat';

export interface MarkdownProps {
  /** Markdown source. Prop name is the frozen contract from phase-3 task-04 — unchanged. */
  markdown: string;
  /** 'article' (default): reading sizes/margins. 'chat': body2, tighter, headings capped at h4 size. */
  variant?: MarkdownVariant;
  /** 1 → a `#` in the source renders as <h2> because the screen already owns the page h1. */
  headingOffset?: 0 | 1;
}

/** Kept so ContentEditorScreen's existing import compiles; identical to MarkdownProps. */
export type MarkdownPreviewProps = MarkdownProps;
