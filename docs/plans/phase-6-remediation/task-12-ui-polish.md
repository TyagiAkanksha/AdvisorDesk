# Task 6R-12 — UI polish batch (BACKLOG — not scheduled)

Owner decision 2026-09-06: schedule as ONE dedicated task later, not opportunistically. This is a
backlog stub, not an active brief — expand into a full brief when the owner schedules it.

## Scope (the ~15-item parked polish batch, from the review + ledger)

Consolidated from p2-t04/t05/t06 minors, p3-t04, p5-t04 residuals (ledger lines 35/39-41/45; review
Minors WR-55/56/57/59/60/61/62/63/64/67). Representative items:
- success-feedback snackbars on save/publish/archive (AppSnackbar severity=success unused)
- unsaved-changes guard on navigate-away from the editor
- title trimmed for validation but sent untrimmed
- logout-failure redirects unconditionally (confusing, not dangerous)
- admin fallback-copy constants → one typed `lib/copy.ts` (mirror client's)
- dead `onClose` on non-temporary Drawer; anchor/width coupling
- AgentPanel hand-rolled empty state → `common/EmptyState`
- dashboard test query scoping (status vs tag count phrasing)
- Markdown-renderer twin anti-drift (pairs with WR-12 SSE-extraction pattern if that lands)

## Why one task

These repeatedly reopen the same admin screens (AppShell, ContentEditorScreen, dashboard). One pass
touching each screen once is cheaper and lower-risk than N separate reopens. Size M-L once scoped.
Excludes anything already done in 6R-11 (WR-13 aria, WR-66 avatar). Full three-agent SDD, frontend
live-evidence rule applies. Does not block Batch 5 minor triage.
