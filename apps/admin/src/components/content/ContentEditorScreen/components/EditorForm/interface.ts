import type { UseContentEditorResult } from '../../useContentEditor';

// phase-8 task-20 (DESIGN.md §5 C5, plan-time ruling): the form + action row leaf takes the
// hook's full RESULT as its one prop — a type import, not a hook call, so the leaf stays dumb
// (docs/FRONTEND-CONVENTIONS.md §3) — plus the one event this leaf cannot derive from the hook
// result alone (opening the delete confirmation lives in the screen, which also owns the
// dialog).
export interface EditorFormProps {
  editor: UseContentEditorResult;
  onDelete: () => void;
}
