export interface ErrorStateProps {
  /** Friendly, authored copy — never the raw API error envelope (docs/FRONTEND-CONVENTIONS.md §9). */
  message?: string;
  /** Optional recovery action rendered as an outlined button under the message (e.g. "Retry")
   * (phase-8 task-04, DESIGN.md §A3). */
  action?: { label: string; onClick: () => void };
}
