// phase-8 task-20 (DESIGN.md §5 C5): the sticky live preview beside (or, below `md`, swapped
// with) the form. Dumb per docs/FRONTEND-CONVENTIONS.md §3 — the title/body values in, nothing
// else; stripping the leading `# Title` and demoting headings lives in `MarkdownPreview` /
// `lib/markdown.ts`, not here.
export interface EditorPreviewProps {
  title: string;
  body: string;
}
