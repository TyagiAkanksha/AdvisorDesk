// phase-8 task-15 (DESIGN.md §C1): shared active-route logic for the AppShell nav — pure so it
// can be unit-tested without rendering anything. '/' matches only the exact root path; every
// other href matches itself or a real path-segment boundary below it (`${href}/…`), not a bare
// string prefix — `/content-archive` must NOT activate `/content` (closes the task-08 minor
// carried from sub-phase B).
export function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}
