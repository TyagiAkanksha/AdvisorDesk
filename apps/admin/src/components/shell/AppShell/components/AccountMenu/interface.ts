/** The avatar button + "Sign out" menu, moved out of `AppShell` verbatim (phase-8 task-15,
 * DESIGN.md §C1) — the anchor element state stays inside this leaf: it is presentational. */
export interface AccountMenuProps {
  /** `me.name ?? me.email` */
  name: string;
  avatarUrl: string | null;
  onSignOut: () => void;
}
