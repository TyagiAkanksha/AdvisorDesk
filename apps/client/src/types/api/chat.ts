import type { components } from '../generated/schema';

// task-05 (phase-4), mirrors `./content.ts`'s Dto/plain-alias idiom (docs/FRONTEND-CONVENTIONS.md
// §5). `ChatRequest` is a real Pydantic schema — `POST /public/chat`'s body
// (`apps/api/app/models/schemas/chat.py::ChatRequest`) — so it's sourced from the generated
// OpenAPI schema like every other wire type.
export type ChatRequestDto = components['schemas']['ChatRequest'];
export type ChatRequest = ChatRequestDto;

// `Citation` is deliberately NOT sourced from the generated schema: `POST /public/chat`'s SSE
// response body is declared in openapi.json as an opaque `text/event-stream` string
// (`apps/api/app/routes/public_routes.py`'s own `responses=` — review round 1, finding M-2:
// `response_class=StreamingResponse` + a manual `content` override, since FastAPI has no way to
// express per-SSE-event payload shapes there). Hand-authored instead, straight from the PRD
// §5.3 wire contract: `citations` event data == `{"citations": [{"content_id","title","slug"}]}`,
// deduped to content level and ordered by first use
// (`apps/api/app/rag/synthesis.py::dedupe_citations`).
export interface CitationDto {
  content_id: string;
  title: string;
  slug: string;
}
export type Citation = CitationDto;

// phase-9 task-17 (DESIGN §A/D2): `POST /public/chat/{message_id}/feedback`'s body — a real
// Pydantic schema, so it comes from the generated OpenAPI types like every other wire type
// (docs/FRONTEND-CONVENTIONS.md §5), not hand-authored like `Citation` above.
export type ChatFeedbackRequestDto = components['schemas']['ChatFeedbackRequest'];
export type ChatFeedbackRequest = ChatFeedbackRequestDto;
/** `-1 | 1` — the endpoint's whole value domain. `0` is deliberately illegal (task 02): a row with
 *  no feedback stays NULL, so "never asked" and "asked, felt neutral" are never conflated. */
export type ChatFeedbackValue = ChatFeedbackRequestDto['value'];
