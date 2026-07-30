// This is the ONLY module allowed to import `./generated/schema` (docs/FRONTEND-CONVENTIONS.md
// §5). `schema.d.ts` is `pnpm codegen` output — committed, never hand-edited, never imported
// anywhere else under `src/`. Phase-3 adds DTO aliases here, e.g.:
//
//   import type { components } from './generated/schema';
//   export type ContentDto = components['schemas']['ContentResponse'];
//
// Everything else imports named types from `@/types`, never `components['schemas'][...]`
// directly — verified by `grep -rn "components\['schemas'\]" src/` matching only this file.
export {};
