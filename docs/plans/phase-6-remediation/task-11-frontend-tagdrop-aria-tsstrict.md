# Task 6R-11 — Admin tag-drop data-loss fix + AppShell aria + TS strictness

WR-ids: WR-11, WR-13, TS-strictness (B4 owner decision). Effort S-M. Full three-agent SDD (frontend ⇒
standing rule d: live-server evidence for the interactive fixes). Fully disjoint from all backend
tasks — safe to run in parallel with them.

## WR-11 — tag typed-but-not-Entered silently dropped on Save (DATA LOSS)

`apps/admin/src/components/common/Autocomplete/Component.tsx` (+ its use in the ContentEditor tag
field). Verifier confirmed via MUI 9.2 source: `autoSelect=false` + `clearOnBlur` defaults mean a
typed-but-unconfirmed tag is dropped on blur/save AND stays visible in the field (worse than a visible
loss). Fix: wire `onBlur` to commit the current `inputValue` into `value` (standard freeSolo capture),
so a typed tag is saved. Preserve all pinned Autocomplete/editor test contracts — if a pin blocks the
clean fix, STOP + NEEDS_CONTEXT. Test-author adds (new test): type a tag, blur WITHOUT Enter, Save,
assert the tag is present in the create/update payload (the currently-failing behavior = RED).

## WR-13 — AppShell accessible-name gap (flagged twice, fixed never)

`apps/admin/src/components/shell/AppShell/Component.tsx`: the Agent-panel toggle and account-menu
trigger lack `aria-expanded`/`aria-haspopup`/`aria-controls`. Root cause: `common/Button`'s props
interface is closed (no aria passthrough). Fix: add aria-* passthrough to `common/Button`'s interface
(ButtonProps), wire the three attributes at both call sites. Ride-along WR-66 (Minor, same file): set
the avatar `alt=""`/aria-hidden so the account name isn't announced twice. Test-author pins: the two
triggers expose correct aria-expanded state (closed/open) and haspopup.

## TS strictness (B4 owner: flip + drop)

Both `apps/admin/tsconfig.json` and `apps/client/tsconfig.json`:
- add `"noUncheckedIndexedAccess": true`
- remove `"allowJs": true` (dead — zero .js/.jsx in src)
Then `pnpm -C apps/<app> type-check` BOTH apps. The verifier expected a clean compile (code already
defends array access), but if it surfaces real errors, FIX them minimally at the call sites (that is
the point of the flag) — do not suppress with `!`/`any`. If the error tail is large (>~15 sites),
STOP + report so the owner can decide scope; do not grind through a huge refactor unasked.
Do NOT touch `exactOptionalPropertyTypes` (owner deferred it).

## Constraints & acceptance

Standing frontend rules: prettier/eslint clean, no `any`, tests through the barrel, mock only the
network edge. `pnpm gates:admin` + `pnpm gates:client` green (incl. new tests); `pnpm build` both.
LIVE EVIDENCE (rule d) for WR-11 + WR-13: `next start` admin, exercise the tag field (type+blur+save
path renders) and inspect the toggle/menu aria in the served DOM (curl or a quick DOM assertion) —
capture verbatim. Path-scoped adds: the touched component files + both tsconfig.json + new test files.
Owner-pending files untouchable. Commit
`fix(admin): capture typed tags on blur + AppShell aria + strict index access (6R-11, WR-11/WR-13)`.
