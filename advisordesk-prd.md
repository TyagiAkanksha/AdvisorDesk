# AdvisorDesk — Product Requirements Document (PRD)

**AI-Powered Advisory Content Platform**
Version 1.5 · Owner: Akanksha Tyagi
Status: Approved for implementation · Scope: full production-quality build

> **Purpose:** a complete, self-contained spec that an implementing agent can execute end-to-end with zero outside context. All decisions from the pre-implementation review are merged inline — no companion documents are required.

> **Implementer contract:**
> 1. Follow this document as written; implement the phases in §10 in order.
> 2. Where something is genuinely ambiguous, resolve it using the defaults philosophy of §11 — pick the simplest behavior consistent with §1.3, note the choice in the README's "Implementation notes," and continue. Do not silently guess on anything schema- or protocol-affecting; those must be raised.
> 3. Findings that are enhancements (better UX, performance, tooling) are welcome as suggestions in a `SUGGESTIONS.md` — do not expand scope unilaterally.

---

## 1. Product overview

### 1.1 One-liner
A content hub for financial advisory firms: advisors publish guidance through a CMS, and their clients get instant, cited answers from an AI assistant grounded **only** in that published content.

### 1.2 Problem
Financial advisory firms produce a steady stream of written guidance, but clients cannot easily get answers from it. Guidance lives in documents and portals; a client with a question has to search or wait for an advisor. A generic chatbot doesn't solve this: in a regulated space, an answer that cannot be traced back to the firm's own published guidance creates risk instead of value.

### 1.3 Solution principles
1. **Published content is the single source of truth.** The assistant can only answer from content with status `published`. Drafts are invisible to it.
2. **Every answer is grounded and cited.** Responses include citations pointing to the source content items. If retrieval finds nothing relevant, the assistant says so instead of guessing.
3. **The editorial workflow is agentic.** CMS operations are exposed as MCP tools so a content manager can run multi-step editorial tasks in natural language.

### 1.4 Explicitly a portfolio/demo build
Seeded with realistic **sample** advisory content. No real customer or financial data. No claims of regulatory compliance — the design *gestures at* compliance needs (traceability, citations) as motivation.

---

## 2. Users & core stories

### 2.1 Personas
- **Content Manager / Advisor (internal):** creates and manages guidance in the CMS admin. Authenticated via Google OAuth, restricted to an email allowlist.
- **Client (external):** visits the client app, asks questions, gets cited answers. No login required.

### 2.2 User stories

**CMS admin**
- As a content manager, I can sign in with Google (allowlisted email) and see a dashboard of all content with status, tags, and updated date.
- I can create, edit, and delete a content item (title, body in markdown, tags, status). Deletion is permanent from the admin's point of view — there is no restore (§4.1, §12).
- I can move an item through statuses: `draft → published → archived`.
- Publishing an item makes it retrievable by the client assistant (embeds it into the vector store); archiving/deleting removes it from retrieval.
- I can filter/search content by title, tag, and status.
- I can open an **agent panel** (chat sidebar) and issue natural-language commands like:
  - "Draft an article on Roth IRA conversion basics and tag it retirement."
  - "How many published pieces do we have on tax planning?"
  - "Find everything tagged estate-planning and publish the drafts."
  The agent executes these by calling MCP tools (§6) and reports what it did. The panel renders each tool call live as it happens (§5.4 events).

**Client app**
- As a client, I can browse published content (list + detail page rendering markdown).
- I can ask the assistant a question in a chat UI and get a streamed answer with numbered citations linking to the source content items.
- If my question isn't covered by published content, the assistant tells me no published guidance covers it (and does not answer from general knowledge).

---

## 3. System architecture

```
┌──────────────────┐         ┌──────────────────┐
│  CMS Admin        │         │  Client App       │
│  Next.js (TS)     │         │  Next.js (TS)     │
│  /apps/admin      │         │  /apps/client     │
│  CRUD + agent UI  │         │  content + chat   │
└─────────┬────────┘         └─────────┬────────┘
          │  REST (JSON) + SSE          │  REST (JSON) + SSE
          └───────────┬────────────────┘
                      ▼
          ┌───────────────────────────┐
          │  FastAPI Backend (Python)  │
          │  /apps/api                 │
          │  • REST endpoints (§5)     │
          │  • Google OAuth + allowlist│
          │  • Agent orchestration     │
          │  • MCP server (§6)         │
          │  • Embedding pipeline (§7) │
          └───────────┬───────────────┘
                      ▼
          ┌───────────────────────────┐
          │  Postgres + pgvector       │
          │  Supabase (default) or     │
          │  local container (§9)      │
          └───────────────────────────┘
```

- **Two frontends, one backend, one database.** Do not create a second backend.
- The MCP server runs **inside the FastAPI app process** and its tools call the same service functions as the REST endpoints — no duplicated business logic.
- **MCP exposure rule:** tools are invoked in-process by the agent loop. Exposing the MCP server over HTTP (for external MCP clients) is OFF by default (`MCP_HTTP_ENABLED=false`); if enabled, the MCP route requires the same admin session auth as §5.2. CMS write tools must never be reachable unauthenticated.
- LLM provider (v1.5): **NVIDIA-hosted models over the OpenAI-compatible API**
  (`https://integrate.api.nvidia.com/v1`, key `NVIDIA_API_KEY`) — chat completions for the RAG
  assistant and the agent loop; embeddings API for vectors. The code talks the OpenAI wire
  protocol via a configurable base URL, so the provider is a config swap, not a code change.

### 3.1 Repository layout (monorepo)
```
advisordesk/
├── apps/
│   ├── admin/          # Next.js 14+ (App Router, TypeScript, Material UI)
│   ├── client/         # Next.js 14+ (App Router, TypeScript, Material UI)
│   └── api/            # FastAPI (Python 3.11+)
│       ├── app/
│       │   ├── main.py
│       │   ├── routes/          # REST endpoints
│       │   ├── services/        # shared business logic (used by routes AND mcp tools)
│       │   ├── mcp/             # MCP server + tool definitions
│       │   ├── rag/             # chunking, embedding, retrieval, answer synthesis
│       │   ├── agent/           # agent loop calling MCP tools
│       │   ├── auth/            # Google OAuth + session + allowlist
│       │   └── models/          # SQLAlchemy models + Pydantic schemas
│       └── tests/
├── infra/
│   ├── docker-compose.yml       # api + admin + client; optional local-db profile (§9)
│   ├── Dockerfile.api
│   ├── Dockerfile.web           # shared for both Next.js apps (build arg selects app)
│   └── deploy/                  # AWS deployment notes/scripts
├── seed/
│   ├── sample_content/          # ~20 markdown advisory articles (§8)
│   └── eval_questions.yaml      # fixed question set for the groundedness harness (§8.1)
└── README.md
```

---

## 4. Data model (Postgres + pgvector)

Enable the `vector` extension. All tables in schema `public`. The conventions in §4.1 apply to every table; the SQL below is normative.

```sql
-- users: content managers (populated on first allowlisted Google OAuth login)
users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  name text,
  avatar_url text,
  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)

-- content: the core CMS entity
content (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  slug text unique not null,
  body_md text not null default '',
  status text not null default 'draft'
    check (status in ('draft','published','archived')),
  author_id uuid references users(id),   -- doubles as created_by (§4.1); null for seeded rows
  updated_by uuid references users(id),  -- last writer (§4.1); null for seeded rows
  published_at timestamptz,
  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)

-- tags + join table
tags (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,             -- lowercase, hyphenated, e.g. 'tax-planning'
  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)
content_tags (
  content_id uuid references content(id) on delete cascade,
  tag_id uuid references tags(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (content_id, tag_id)
)
create index on content_tags (tag_id);

-- chunks: RAG units derived from published content (hard-delete only — §4.1)
chunks (
  id uuid primary key default gen_random_uuid(),
  content_id uuid not null references content(id) on delete cascade,
  chunk_index int not null,
  text text not null,
  embedding vector(1024),            -- nvidia/nv-embedqa-e5-v5 (v1.5; was 1536/text-embedding-3-small)
  created_at timestamptz not null default now()
)
create index on chunks using hnsw (embedding vector_cosine_ops);
create index on chunks (content_id);

-- chat_sessions / messages (client app; anonymous sessions, id held client-side; append-only)
chat_sessions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now()
)
chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references chat_sessions(id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  citations jsonb,                   -- assistant rows: [{content_id, title, slug, chunk_id}]
  retrieval_found boolean,           -- assistant rows: false when no chunk cleared the threshold
  top_similarity real,               -- assistant rows: best similarity for the query (null if no chunks)
  created_at timestamptz not null default now()
)
create index on chat_messages (session_id, created_at);
```

### 4.1 Schema conventions

- **Primary keys:** `uuid` via `gen_random_uuid()` on every table.
- **Timestamps:** `timestamptz` only. Every table carries `created_at not null default now()`. Every mutable table (`users`, `content`, `tags`) also carries `updated_at not null default now()`, maintained by the application layer on every write (no DB triggers). Append-only/derived tables (`chunks`, `content_tags`, `chat_sessions`, `chat_messages`) carry `created_at` only — their rows are never updated in place.
- **Actor columns:** where a write is performed by an authenticated admin, the row records who. On `content`, `author_id` doubles as the created-by column (set once at creation, never changed) and `updated_by` records the last writer; both are nullable because the seed script (§8) writes outside any session. Writes made through MCP tools record the admin whose session drives `/agent/chat`. `tags` carry no actor columns (created as a side effect of tagging — the audit trail lives on the content row). `users` rows are written only by the OAuth upsert, where the actor is the user themself. Client-side tables are anonymous by design.
- **Soft delete:** `users`, `content`, and `tags` carry `is_deleted boolean not null default false`. Deleted rows are DB-level tombstones: there is no restore endpoint, UI, or MCP tool (§12), and no API response ever includes them — lists and counts exclude them; reads by id or slug return 404. All other tables hard-delete: `chunks` are derived data whose physical removal is what guarantees retrieval never sees non-published or deleted content (lifecycle rule below); `chat_sessions`/`chat_messages` are append-only. No API surface deletes `tags` or `users` — their flags exist for the uniform convention and manual operator cleanup only.
- **Active-row filter (define once):** exactly like the similarity convention (§7.3), define the `is_deleted = false` filter once in the data-access layer — a base query/helper per soft-deletable model — and route every read through it. Do not scatter ad-hoc `where` clauses; a missed filter is a data-leak bug, and a test pins the behavior (§9).
- **Uniqueness vs. soft delete:** unique constraints deliberately span deleted rows.
  - `content.slug` — never reused: a deleted item's slug stays taken forever, so a published URL can never resurrect pointing at different content; a colliding title receives the next `-N` suffix per the slug rules below.
  - `tags.name` — creating a tag that exists soft-deleted **reactivates** the existing row (flip `is_deleted` back to `false`, same `id`) instead of inserting.
  - `users.email` — the OAuth upsert (§5.1) reactivates a soft-deleted user whose email is still in `ADMIN_EMAILS`. Session validation treats a soft-deleted user as unauthenticated (401).
- **Foreign keys:** `not null` wherever a child row is meaningless without its parent (`chunks.content_id`, `chat_messages.session_id`). Postgres does not index FK columns automatically; the three FK indexes above cover the lookups the app actually performs (chunk removal by `content_id`, tag filters/usage counts by `tag_id`, session-ordered message reads for chat history and `report_content_gaps`). No `status` or partial `is_deleted` indexes — unnecessary at this data scale.

**Slug rules:** auto-generated from title on create. On collision, append an incrementing suffix: `roth-ira-basics`, `roth-ira-basics-2`, `roth-ira-basics-3`. **Slugs are immutable after creation** — title edits do not change the slug, so published URLs never break. Slug uniqueness is global and includes soft-deleted rows (§4.1): a deleted item's slug is never reused.

**Citation granularity (deliberate asymmetry):** the DB stores **chunk-level** citations (`chunk_id` included) because the groundedness harness (§10 Phase 7) must know exactly which chunks supported each answer. The public API returns citations **deduped to content level** (§5.3) because the client UI links to articles, not chunks. Document this in code comments where both shapes appear. Citations are a historical record: links to since-deleted content simply 404.

**Lifecycle rule (critical):**
- On `publish`: chunk `body_md`, embed chunks, insert into `chunks`, set status + `published_at`.
- On `edit` of a published item: re-chunk and re-embed (delete old chunks for that content_id, insert new).
- On `archive`: status → `archived`; remove that content's rows from `chunks`.
- On `delete`: set `is_deleted = true` **and** remove that content's rows from `chunks`, in the same transaction. `status` and `published_at` are left untouched — `is_deleted` alone governs visibility, and the tombstone keeps its history. There is no restore path (§4.1, §12).
- **Atomicity:** each of the above runs in a single DB transaction. If the embedding API call fails, the transaction rolls back — a publish leaves the item in `draft`, an edit leaves the previous chunks intact — and the API returns the standard error envelope. Partial chunk sets must never be visible to retrieval. Archive and delete involve no embedding call but still run as one transaction, so the visibility flip and the chunk removal are never observed separately.
- With soft delete, no code path hard-deletes `content` or `tags`, so the `on delete cascade` clauses on `content_tags` and `chunks` never fire in normal operation. Keep them — they are harmless and act as a safety net for manual DB cleanup.

This guarantees the assistant only ever retrieves currently-published, non-deleted, fully-embedded content — deletion physically removes chunks, so retrieval safety never depends on the `is_deleted` filter.

---

## 5. Backend REST API (FastAPI)

All routes prefixed `/api/v1`. JSON in/out; streaming endpoints use SSE with the typed events defined below. Admin routes require an authenticated session; client routes are public. Soft-deleted rows (§4.1) are invisible to every endpoint: excluded from all lists and counts; reads, updates, and status transitions addressing a soft-deleted row return 404. No endpoint restores them.

### 5.1 Auth (admin)
- `GET  /auth/login` → redirect to Google OAuth consent
- `GET  /auth/callback` → exchange code; reject emails not in `ADMIN_EMAILS`; upsert user (reactivating a soft-deleted row, §4.1); set signed HttpOnly session cookie
- `POST /auth/logout`
- `GET  /auth/me` → current user or 401

### 5.2 Content (admin, authenticated)
- `GET    /content` — list; query params: `status`, `tag`, `q` (title search), `page`, `page_size`
- `POST   /content` — create draft `{title, body_md, tags[]}` (slug per §4 rules)
- `GET    /content/{id}`
- `PATCH  /content/{id}` — update title/body/tags (slug unchanged); if item is published, triggers the re-embed transaction
- `POST   /content/{id}/publish` — publish transaction (§4)
- `POST   /content/{id}/archive` — status→archived + remove chunks
- `DELETE /content/{id}` — soft delete: sets `is_deleted = true` and removes chunks in one transaction (§4); `status` untouched; the item disappears from every list, count, and by-id read. No restore.
- `GET    /tags` — list non-deleted tags with usage counts; counts include non-deleted content only
- `GET    /stats` — counts by status, by tag, excluding soft-deleted content (powers dashboard + `count_content` tool)

### 5.3 Public (client app)
- `GET  /public/content` — published and non-deleted only; list with tags
- `GET  /public/content/{slug}` — published and non-deleted only; detail (a deleted item's slug 404s and is never reassigned, §4.1)
- `POST /public/chat` — body `{session_id?, message}`. If `session_id` is absent or unknown, the server creates a session (subject to the per-IP creation cap, §9) and returns its id in the `done` event; the client stores it in `localStorage` and sends it on subsequent requests. No cookies are used for client sessions. SSE response:

```
event: token       data: {"text": "..."}                                  (repeated)
event: citations   data: {"citations": [{"content_id","title","slug"}]}   (deduped by content item, ordered by first use)
event: done        data: {"session_id": "...", "message_id": "..."}
event: error       data: {"error": {"code","message"}}
```

### 5.4 Agent (admin, authenticated)
- `POST /agent/chat` — **stateless.** Body `{messages: [{role: "user"|"assistant", content}]}` where the last element is the new user turn; the admin frontend holds conversation history in component state and resends it each request. The server persists nothing for agent chats. SSE response, tool events interleaved with tokens in execution order:

```
event: token        data: {"text": "..."}
event: tool_call    data: {"tool": "...", "arguments": {...}}
event: tool_result  data: {"tool": "...", "result_summary": "..."}
event: done         data: {"tool_calls": [{"tool","arguments","result_summary"}]}
event: error        data: {"error": {"code","message"}}
```

---

## 6. MCP server & tools

Implemented with the official Python MCP SDK, mounted in the FastAPI app (exposure rule in §3). Tools wrap the same service functions as the REST routes. **Every tool validates inputs with Pydantic and returns structured JSON.**

| Tool | Arguments | Behavior |
|---|---|---|
| `create_draft` | `title: str`, `body_md: str = ""`, `tags: list[str] = []` | Creates a draft content item. Creates missing tags (reactivating soft-deleted names, §4.1). Returns `{id, slug}`. |
| `edit_content` | `content_id: str`, `title?`, `body_md?`, `tags?` | Partial update. Re-embeds if published. Slug unchanged. |
| `delete_content` | `content_id: str` | Soft-deletes the item (`is_deleted = true`, tombstone — not restorable) and removes its chunks in one transaction (§4). |
| `tag_content` | `content_id: str`, `add: list[str] = []`, `remove: list[str] = []` | Adjusts tags. Tags in `add` are created if missing (reactivating soft-deleted names, §4.1). |
| `search_content` | `q?: str`, `status?: str`, `tag?: str`, `limit: int = 10` | Metadata search over CMS (title/tag/status — not vector search). |
| `count_content` | `status?: str`, `tag?: str` | Returns counts, e.g. `{count: 12}`. |
| `publish` | `content_id: str` | Runs the publish transaction (§4). |
| `archive` | `content_id: str` | Status→archived, removes chunks. |
| `report_content_gaps` | `days: int = 30`, `limit: int = 20` | Client questions from the last `days` days where retrieval found nothing above threshold: selects user messages whose following assistant message (same session, next by `created_at`) has `retrieval_found = false`. Returns `{count, gaps: [{question, asked_at, session_id}]}`, newest first. |

All tools read and write non-deleted rows only (§4.1) — a `content_id` addressing a soft-deleted item is a not-found error — and writes record the admin whose session drives `/agent/chat` in the actor columns.

**Agent loop (in `/agent/chat`):** system prompt describes the assistant as a CMS operations agent; the OpenAI model is given the MCP tool schemas; the loop executes tool calls until the model returns a final message.
- **Cap: 8 tool calls per request.** At the cap, the agent stops, reports exactly which operations completed and which remain, and tells the user to re-run for the remainder. It never fails silently mid-task.
- On a tool error, surface the error to the model once for self-correction, then fail gracefully with an explanation.
- When the agent drafts article content (e.g. "draft an article on X"), the body is generated within the same model interaction and passed to `create_draft`. Agent-created drafts are ALWAYS status `draft` — never auto-published unless the user explicitly instructs publishing.

---

## 7. RAG pipeline (client assistant)

1. **Chunking:** split `body_md` by markdown headings, then to ~400-token chunks with 50-token overlap (v1.5: lowered from 500 — the embedding model's input window is 512 of *its* tokens, and tokenizers differ; 400 keeps a safe margin). Store `chunk_index`.
2. **Embedding:** `nvidia/nv-embedqa-e5-v5` (1024 dims) via the OpenAI-compatible `/v1/embeddings` endpoint (v1.5). The model is **asymmetric**: pass `input_type="passage"` when embedding chunks at publish time and `input_type="query"` when embedding user questions at retrieval time; send `truncate="END"` as a defense against over-length input. Batch per content item. Model/dims/base-URL are env-configurable (`EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `LLM_BASE_URL`) so a provider swap never touches code.
3. **Retrieval:** embed the user query → nearest neighbors over `chunks` via the HNSW index → top 6 → threshold filter.
   **Similarity convention (implementation trap — read carefully):** pgvector's `<=>` operator returns cosine **distance**. Define once in the retrieval module: `similarity = 1 - (embedding <=> query_embedding)`. Apply `SIMILARITY_THRESHOLD` (default `0.35`, env-configurable) to that **similarity** value — chunks below it are dropped. A unit test pins this conversion (§9).
4. **Retrieval outcome recording:** when persisting the assistant message, set `top_similarity` to the best similarity observed (null if the index returned nothing) and `retrieval_found = false` iff no chunk cleared the threshold.
5. **Answer synthesis:** NVIDIA-hosted instruct model over the OpenAI-compatible chat-completions API (exact model pinned in the phase-4 plan; `CHAT_MODEL` env-configurable). System prompt (verbatim intent, wording adjustable):
   - Answer ONLY from the provided context chunks.
   - Cite with bracketed numbers [1], [2] mapping to the provided sources.
   - If the context does not contain the answer: reply that no published guidance covers this, suggest asking the advisory team, and DO NOT answer from general knowledge.
   - Never give personalized financial advice; frame answers as "the firm's published guidance says…".
6. **Streaming:** stream tokens per §5.3; after the stream, emit the deduped content-level citations array.
7. **Persistence:** store user + assistant messages in `chat_messages` — assistant rows carry chunk-level citations, `retrieval_found`, and `top_similarity` (§4).

---

## 8. Seed data

`seed/sample_content/` contains ~20 markdown files of realistic sample advisory articles across tags: `retirement`, `tax-planning`, `estate-planning`, `investing-basics`, `college-savings`, `insurance`. Each file has YAML frontmatter (`title`, `tags`, `status`). A seed script (`apps/api/app/seed.py`) loads them, publishes the ones marked published (running the real embed pipeline), and leaves 3–4 as drafts so the agent has content to find/publish in demos. Write original sample content — do not copy real firms' material. Include a footer line in each article: *"Sample content for demonstration purposes — not financial advice."* Seeded rows carry `author_id = null` / `updated_by = null` (created outside any session, §4.1).

### 8.1 Evaluation question set
`seed/eval_questions.yaml` is authored together with the seed articles (Phase 4) and consumed by the groundedness harness (Phase 7). ~15 questions:
- ~12 **answerable** questions, each mapped to the slug(s) of the article(s) expected to ground the answer;
- ~3 **deliberately uncovered** questions to verify the refusal path (expected outcome: `retrieval_found = false`, refusal response, no citations).

```yaml
- question: "What is a Roth IRA conversion?"
  expected_slugs: ["roth-ira-conversion-basics"]
  answerable: true
- question: "What does the firm recommend about cryptocurrency staking?"
  expected_slugs: []
  answerable: false
```

---

## 9. Non-functional requirements

- **Auth security:** signed HttpOnly session cookies for admin; admin routes 401 without a session or when the session's user row is soft-deleted (§4.1); Google logins rejected unless the email is in `ADMIN_EMAILS`.
- **CORS:** allowed origins come from `CORS_ORIGINS` (comma-separated env var listing the two frontend origins). No wildcard in deployed environments.
- **Rate limiting (public chat):** in-app middleware (in-memory store is acceptable for a single container):
  - `RATE_LIMIT_PER_MIN` (default 10) messages per minute per IP
  - `RATE_LIMIT_PER_DAY` (default 50) messages per day per session
  - `SESSION_CREATE_PER_DAY` (default 20) new sessions per day per IP — prevents resetting the per-session cap by minting fresh sessions
  - Violations return `429` with the standard error envelope.
- **Config:** all secrets and tunables via env vars: `NVIDIA_API_KEY` (v1.5; was
  `OPENAI_API_KEY`), `LLM_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `CHAT_MODEL`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, `ADMIN_EMAILS`, `CORS_ORIGINS`, `SIMILARITY_THRESHOLD`, `RATE_LIMIT_PER_MIN`, `RATE_LIMIT_PER_DAY`, `SESSION_CREATE_PER_DAY`, `MCP_HTTP_ENABLED`. `.env.example` provided. Never commit secrets.
- **Streaming latency:** first token < ~2s on typical questions; a simple middleware logs p50/p95.
- **Error handling:** consistent JSON error envelope `{error: {code, message}}` (also used inside SSE `error` events); frontends surface friendly messages.
- **Type safety:** TypeScript strict mode in both frontends; Pydantic everywhere on the API boundary.
- **Tests (minimum):**
  - chunking unit tests
  - the publish / re-embed / remove lifecycle, including the rollback-on-embedding-failure path (§4 atomicity) and delete-as-soft-delete (tombstone + chunk removal in one transaction)
  - soft-delete visibility: a deleted published item disappears from the admin list, the public list, and retrieval, and by-id/by-slug reads return 404 (REST and MCP) — pins the define-once active-row filter (§4.1)
  - tag reactivation: creating a tag whose name matches a soft-deleted tag reactivates the same row (same `id`); usage counts ignore soft-deleted content
  - slug permanence: new content colliding with a deleted item's slug receives the `-2` suffix
  - the similarity conversion pin test (§7.3)
  - each MCP tool: happy path + one failure path (including `report_content_gaps` against seeded `retrieval_found` rows)
  - a smoke test that boots the API and hits `/api/v1/stats`
- **Local development:** `docker compose up` runs api + both frontends. An optional `db` service (image `pgvector/pgvector:pg16`) sits behind a compose profile: `docker compose --profile local-db up` for fully offline dev. `DATABASE_URL` points at either the local container or Supabase. README documents both paths; **Supabase remains the default and the deployed target.**
- **Deployment:** AWS. Default: API container on App Runner (or ECS Fargate); frontends per §11. *(Amended 2026-08-09, phase-6 execution: App Runner closed to new AWS customers 2026-04-30 — deployed as single-host EC2 + Caddy running all three containers; see `infra/deploy/ec2-single-host.md`.)*

## 9.1 Metrics to capture (for resume/interview)
- Number of seeded documents and chunks; number of MCP tools (9: 8 core + `report_content_gaps`).
- Groundedness: % of answers fully supported by cited chunks, produced by the Phase 7 harness over `seed/eval_questions.yaml`.
- p50/p95 first-token latency on `/public/chat`.

---

## 10. Implementation phases (implement in order)

**Phase 1 — Skeleton:** monorepo scaffold, FastAPI app boots, schema migrated, `docker compose up` runs (including the `local-db` profile), health endpoint.
**Phase 2 — Auth + CMS CRUD:** Google OAuth with `ADMIN_EMAILS` allowlist, admin frontend with content list/editor/status transitions (delete = soft delete, §4.1), tags, stats dashboard, slug generation + collision handling.
**Phase 3 — Publish pipeline + client content:** the transactional publish/re-embed/remove lifecycle (§4), client app content list/detail.
**Phase 4 — RAG assistant:** retrieval with the similarity convention (§7.3), synthesis, SSE streaming with typed events, citations, refusal path, retrieval-outcome recording; seed articles AND `seed/eval_questions.yaml` authored and loaded.
**Phase 5 — MCP + agent:** MCP server with all 8 core tools, stateless agent endpoint + loop with cap behavior, admin agent panel rendering live `tool_call`/`tool_result` events.
**Phase 6 — Deployment:** AWS deployment, rate limiting verified in deployed env, metrics middleware, README (both DB paths), demo script (publish → ask → agent command walkthrough).
**Phase 7 — Evaluation & analytics:** groundedness harness consuming `seed/eval_questions.yaml` (reports % of answers fully supported by cited chunks + refusal correctness, as a summary table); `report_content_gaps` MCP tool.

Definition of done: a stranger can follow the README, run the demo script end to end, and every capability described in this document works as specified.

---

## 11. Open decisions & defaults (owner may override)

| # | Decision | Default chosen | Alternatives |
|---|---|---|---|
| 1 | LLM/embedding models (v1.5) | NVIDIA-hosted via OpenAI-compatible API: `nvidia/nv-embedqa-e5-v5` embeddings (1024d); chat model pinned in phase 4 | OpenAI `gpt-4o-mini` + `text-embedding-3-small` (original v1.4 default — config swap away) |
| 2 | Repo structure | Single monorepo | Split repos per app |
| 3 | Client app auth | Public, anonymous sessions | Add optional Google login for clients |
| 4 | Admin access control | Email allowlist via env var (`ADMIN_EMAILS`) | Open login for local development only |
| 5 | Frontend deploy | Containers on AWS with the API | Vercel for the two Next.js apps, API on AWS |
| 6 | Styling | Material UI (`@mui/material` + `@mui/icons-material` + `@mui/material-nextjs` App Router integration, Emotion, `createTheme()` as the design-token system); minimal clean UI; no Tailwind | Tailwind (+ shadcn/ui) — original default, superseded 2026-07-27 |
| 7 | Agent chat framework | Hand-rolled OpenAI tool-loop | LangChain/LlamaIndex (avoid unless it saves real time) |

*(Resolved and no longer open: streaming protocol = SSE with typed events (§5); client session transport = body param + localStorage (§5.3); agent chat = stateless (§5.4); tool-call cap behavior (§6); slug rules (§4); rate limiting (§9); local DB option (§9); similarity convention (§7); soft-delete conventions (§4.1).)*

---

## 12. Out of scope

- Real user/client accounts, roles, or permissions beyond the single admin tier
- Payments, multi-tenancy, or firm onboarding
- Server-side persistence of admin agent conversations (deliberately stateless, §5.4)
- Mobile apps; SEO work; email notifications
- Restore/undelete of soft-deleted rows — deletion is a permanent DB-level tombstone (§4.1); hard-delete/purge tooling likewise out of scope

---

## 13. Glossary

- **RAG** — retrieval-augmented generation: retrieve relevant chunks, generate an answer grounded in them.
- **MCP** — Model Context Protocol: a standard interface for exposing tools to AI agents; model-agnostic, schema-validated.
- **Groundedness** — the degree to which an answer's claims are supported by its cited sources.
- **Content gap** — a client question for which retrieval found no published guidance above the similarity threshold.

---

## 14. Changelog

- **v1.4** — Styling stack switched from Tailwind to Material UI (owner decision, 2026-07-27): `@mui/material` + `@mui/icons-material` + `@mui/material-nextjs` (App Router SSR), Emotion styling, MUI `createTheme()` as the design-token system; no Tailwind. Updates §11 row 6 and the §3.1 layout comments. No behavioral or API change.
- **v1.3** — Schema standardization pass (§4.1): uuid PKs; `timestamptz` audit columns (`created_at` everywhere, `updated_at` on mutable tables, `not null default now()`, app-maintained); actor columns on `content` (`author_id` doubles as created-by; new `updated_by`); soft delete via `is_deleted` on `users`/`content`/`tags` only (`chunks` stay hard-delete; chat tables append-only); define-once active-row filter; uniqueness-vs-soft-delete semantics (slugs never reused; tag/user reactivation-on-recreate); minimal FK index set. Lifecycle: delete = tombstone + chunk removal in one transaction, `status` untouched; no restore surface (§12). Ripples through §2.2, §5 (public filters now published **and** non-deleted), §6, §8, §9 tests. Retrieval behavior unchanged — deletion still physically removes chunks.
- **v1.2** — Merged all 12 pre-implementation review resolutions inline (stateless agent endpoint; retrieval-outcome columns; `report_content_gaps` spec; body-param sessions; citation-granularity asymmetry; tool-cap behavior; slug rules; SSE event shapes; rate limiting; local-db compose profile; similarity-vs-distance convention; eval question set). Added from the follow-up consistency pass: publish/edit atomicity + rollback, MCP HTTP exposure rule, per-IP session-creation cap, `CORS_ORIGINS` as config. Added implementer contract.
- **v1.1** — Removed MVP framing and dates; full-build scope; Phase 7 (evaluation & analytics) added; allowlist made default.
- **v1.0** — Initial spec.
