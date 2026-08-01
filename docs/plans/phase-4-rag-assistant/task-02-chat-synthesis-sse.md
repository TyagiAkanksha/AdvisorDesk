---
id: task-02
phase: phase-4-rag-assistant
depends_on: [task-01]
status: planned
spec: advisordesk-prd.md §5.3, §7.5–§7.7, §4, §7.4
---

# task-02 — `POST /public/chat`: synthesis, SSE streaming, persistence, refusal

## Goal

The client assistant works end-to-end: retrieval → grounded synthesis with numbered citations →
typed SSE stream → persistence with chunk-level citations and retrieval-outcome columns → explicit
refusal when nothing clears the threshold. Produces the SSE utilities `/agent/chat` (phase 5)
reuses and the event contract the chat UI (task-05) parses.

## Context (read ONLY these)

- `advisordesk-prd.md` §5.3 (request/response + the four event shapes, session rules), §7.5
  (system-prompt intent, verbatim), §7.6–§7.7 (stream order, persistence), §7.4 (outcome
  recording), §4 "Citation granularity" (the asymmetry + required code comments).
- `app/rag/retrieval.py` (task-01); `CONVENTIONS.md` §4 (SSE errors use the same envelope).

## Files

- Create: `apps/api/app/rag/synthesis.py`, `apps/api/app/routes/sse.py`,
  `apps/api/app/services/chat.py`, `apps/api/app/models/schemas/chat.py`
- Create: `apps/api/tests/test_public_chat.py`
- Modify: `apps/api/app/routes/public_routes.py` (add the route), `apps/api/app/factory.py`
  (LLM seam wiring), `apps/api/app/config.py` (add
  `chat_model: str = "meta/llama-3.1-8b-instruct"` — the phase-4 pin, `CHAT_MODEL`
  env-overridable per PRD §9), `.env.example` (document `CHAT_MODEL`),
  `apps/api/openapi.json` + both codegens

## Interfaces

- **Consumes:** `RetrievalResult` (task-01); `ChatSession`/`ChatMessage` models; settings.
- **Produces (later tasks rely on — produce exactly):**
  - `app.routes.sse`: `sse_event(name: str, payload: Mapping) -> str` (spec-formatted
    `event:`/`data:` block) + `sse_response(gen) -> StreamingResponse`
    (`text/event-stream`, no-cache headers). **Phase-5 task-03 reuses these.**
  - `app.rag.synthesis`: `SYSTEM_PROMPT` (constant implementing §7.5's four bullets: context-only
    answers; `[n]` citations mapping to provided sources; refusal wording — no published guidance
    covers this, suggest asking the advisory team, never answer from general knowledge; no
    personalized advice — "the firm's published guidance says…") ·
    `class ChatLLM(Protocol): def stream_answer(self, system: str, question: str,
    sources: Sequence[RetrievedChunk]) -> Iterator[str]` · `OpenAICompatibleChatLLM` (v1.5 —
    mirror `OpenAICompatibleEmbedder` exactly: `from_settings` classmethod building an `openai`
    SDK client from `llm_base_url` + `nvidia_api_key` (same empty-key-boot-safe `"unset"`
    fallback), `model=settings.chat_model`, streaming via standard
    `chat.completions.create(stream=True)` — the chat path needs NO NVIDIA-specific
    `extra_body`; provider errors logged, never enveloped, same as phase 3). Factory param
    `chat_llm=None`; `app.state.chat_llm`.
  - `app.services.chat`: `get_or_create_session(session, session_id | None) -> ChatSession` ·
    `record_user_message(session, chat_session_id, text) -> ChatMessage` ·
    `record_assistant_message(session, chat_session_id, text, retrieval: RetrievalResult)
    -> ChatMessage` — stores **chunk-level** `citations` JSONB
    `[{content_id,title,slug,chunk_id}]`, `retrieval_found` (False iff nothing cleared the
    threshold), `top_similarity` (§7.4; carries the §4 asymmetry comment).
    **phase-7 `report_content_gaps` reads exactly these columns.**
  - `dedupe_citations(chunks) -> list[{content_id,title,slug}]` — content-level, ordered by first
    use (§5.3; carries the other half of the §4 comment).
  - Route: `POST /public/chat` `operation_id="public_chat"`, body `{session_id?, message}`;
    events exactly: `token {text}`* → `citations {citations}` → `done {session_id, message_id}`;
    `error {error:{code,message}}` on failure.
- **Implementation note:** rate-limit rejection (task-03) happens before the stream opens.

## Steps (TDD)

- [ ] **Step 1: Failing tests** (`test_public_chat.py`; `FakeEmbedder` + scripted `FakeChatLLM`;
  parse the SSE body into an event list):
  - happy path: event order token+ → citations → done; `done.session_id` present and new when no
    id sent; same id echoed when a known id is sent; unknown id → new session (§5.3);
  - citations deduped to content level and ordered by first use, while the stored assistant row
    has chunk-level citations incl. `chunk_id` (**§4 asymmetry pin — assert both shapes from one
    exchange**);
  - outcome recording: covered question → `retrieval_found=True`, `top_similarity` ≈ fake value;
    uncovered → `retrieval_found=False`, refusal text streamed, `citations` event empty, LLM
    receives zero sources (**refusal pin**);
  - persistence: user + assistant rows exist in order with correct roles;
  - LLM failure mid-stream → `error` event with the §9 envelope, user message still persisted.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** sse.py → synthesis.py → chat.py → route,
  minimal-to-green. **Step 4:** run → PASS.
- [ ] **Step 5: Baseline:** regenerate `openapi.json` + both codegens (same commit).
- [ ] **Step 6: Gates → commit:**
  `feat(api): public chat with SSE, citations, refusal + persistence (phase-4 task-02)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_public_chat.py -q    # all passed
grep -n "chunk-level" app/services/chat.py && grep -n "content level" app/routes/public_routes.py \
  app/rag/synthesis.py app/services/chat.py   # the §4-mandated comments exist at both shapes
git diff --exit-code apps/api/openapi.json 2>/dev/null || true      # regenerated in-commit
```

## Acceptance

- All four §5.3 event types stream in execution order with the exact payload keys.
- Refusal path never calls the LLM with sources and never answers from general knowledge.
- One exchange produces chunk-level rows and content-level wire citations, each site commented
  (§4 requirement).
- `retrieval_found`/`top_similarity` semantics match §7.4 exactly.
