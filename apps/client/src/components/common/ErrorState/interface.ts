export interface ErrorStateProps {
  /** Friendly, authored copy — never the raw API error envelope (docs/FRONTEND-CONVENTIONS.md §9). */
  message?: string;
  /** A way to retry, rendered as an outlined button under the message (phase-8 task-06). */
  action?: { label: string; onClick: () => void };
}
