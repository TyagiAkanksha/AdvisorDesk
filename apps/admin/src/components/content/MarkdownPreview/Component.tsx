import type { MarkdownPreviewProps } from './interface';

// task-06 Interfaces: placeholder rendering for THIS phase only — phase-3 task-04 replaces
// this `<pre>` with the shared markdown renderer; `{markdown: string}` in / visible text out
// is the frozen contract that survives that swap unmodified (MarkdownPreview/Component.test.tsx
// pins the contract, not this tag).
export default function Component({ markdown }: MarkdownPreviewProps) {
  return <pre>{markdown}</pre>;
}
