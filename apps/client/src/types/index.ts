// This is the ONLY module allowed to import `./generated/schema` (docs/FRONTEND-CONVENTIONS.md
// §5), and it does so only transitively via `./api/content` below. `schema.d.ts` is `pnpm
// codegen` output — committed, never hand-edited, never imported anywhere else under `src/`.
//
// Everything else imports named types from `@/types`, never `components['schemas'][...]`
// directly — verified by `grep -rn "components\['schemas'\]" src/` matching only `src/types/`.
export type {
  PublicContentDetail,
  PublicContentDetailDto,
  PublicContentSummary,
  PublicContentSummaryDto,
} from './api/content';
// task-05 (phase-4): mirrors the block above's Dto/plain-alias barrel pattern for the chat
// wire types (`./api/chat.ts`).
export type {
  ChatFeedbackRequest,
  ChatFeedbackRequestDto,
  ChatFeedbackValue,
  ChatRequest,
  ChatRequestDto,
  Citation,
  CitationDto,
} from './api/chat';
