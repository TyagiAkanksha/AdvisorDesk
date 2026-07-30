import type { components } from '../generated/schema';

// src/types/ is the only layer allowed to touch `components['schemas']`
// (docs/FRONTEND-CONVENTIONS.md §5) — everything else imports `MeDto`.
export type MeDto = components['schemas']['MeResponse'];
