---
id: hy-t04
phase: hygiene-2026-09
depends_on: []
status: todo
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: sonnet
---

# Task 04 — Drop `vite-tsconfig-paths`; use Vite's native `resolve.tsconfigPaths`

## Goal

Close t22 M2: "the vite-tsconfig-paths deprecation banner is pre-existing project-wide noise".
Every `vitest run` in both apps starts with a yellow banner: *The plugin "vite-tsconfig-paths"
is detected. Vite now supports tsconfig paths resolution natively via the
`resolve.tsconfigPaths` option…*. The workspace is on Vite 8.1.5 (vitest 4.1.10), which has
the native option. Remove the plugin from both `vitest.config.ts`, set
`resolve: { tsconfigPaths: true }`, and drop the dev dependency from both apps (and thus the
root `pnpm-lock.yaml`). `@/…` imports must keep resolving in every test file.

**Plan-time ruling:** this task has no meaningful RED step — the behaviour under test is
"every existing test still resolves its imports", and the proof is the two full suites plus
the absence of the banner. The reviewer still reviews.

## Context (read ONLY these)

- `apps/admin/vitest.config.ts`, `apps/client/vitest.config.ts`
- `apps/admin/package.json`, `apps/client/package.json` (`devDependencies`), root
  `pnpm-workspace.yaml`, root `pnpm-lock.yaml` (do not hand-edit the lockfile — `pnpm` does it).
- `apps/admin/tsconfig.json` / `apps/client/tsconfig.json` — confirm `paths: { "@/*": ["./src/*"] }`.

## Files

**Modify**
- `apps/admin/vitest.config.ts`, `apps/client/vitest.config.ts`
- `apps/admin/package.json`, `apps/client/package.json`, root `pnpm-lock.yaml` (via `pnpm remove`)

## Interfaces

```ts
// apps/admin/vitest.config.ts — the diff (the client file gets the identical change)
-import tsconfigPaths from 'vite-tsconfig-paths';
 …
 export default defineConfig({
-  plugins: [react(), tsconfigPaths()],
+  plugins: [react()],
+  // hygiene t04: `@/*` from tsconfig `paths`, resolved natively by Vite 8 (replaces the
+  // deprecated vite-tsconfig-paths plugin and its start-up banner).
+  resolve: { tsconfigPaths: true },
   test: { …unchanged… },
 });
```

## Steps

- [ ] **Step 1 (test-author): record the baseline.** Run `cd apps/admin && npx vitest run
  src/lib/format.test.ts 2>&1 | head -3` and the client equivalent
  (`cd apps/client && npx vitest run src/lib/formatDate.test.ts 2>&1 | head -3` — pick any
  tiny test file that exists) and paste the banner line in the report as the RED evidence
  ("banner present"). No test files are written for this task; say so in the report.
- [ ] **Step 2 (implementer):** apply the `vitest.config.ts` diff to both apps. Then from the
  repo root: `pnpm -C apps/admin remove vite-tsconfig-paths && pnpm -C apps/client remove
  vite-tsconfig-paths`. Confirm `grep -n vite-tsconfig-paths pnpm-lock.yaml apps/*/package.json`
  prints nothing.
- [ ] **Step 3: prove resolution.** In each app: `npx vitest run` (full suite) — same pass
  counts as before (admin ≈ 300 tests / 76 files, client ≈ 174 / 46 at the time of writing; the
  exact numbers may have grown from tasks 01–03 — compare against a run on the branch *before*
  your change, which you record in Step 1). The banner must be gone from the first lines of
  output. Paste the first three lines and the summary lines of each run.
- [ ] **Step 4: gates.** `pnpm -C apps/admin type-check && pnpm -C apps/admin lint` and the
  client equivalents; `pnpm install --frozen-lockfile` from the root must succeed (the lockfile
  is consistent).
- [ ] **Step 5: commit.** `git commit -m "chore(frontend): drop vite-tsconfig-paths for Vite's native resolve.tsconfigPaths (p8 t22 M2)"`

## Acceptance criteria

- No `vite-tsconfig-paths` anywhere in `apps/*/package.json` or `pnpm-lock.yaml`.
- Both suites pass with the same counts as before; no banner in the output.
- `pnpm install --frozen-lockfile` succeeds.

## Report

Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-04-test-author.md` (baseline
banner + pre-change suite counts); implementer →
`.superpowers/sdd/hygiene-2026-09/reports/task-04-implementer.md`.
