---
id: task-02
phase: phase-3-publish-client-content
depends_on: [task-01, phase-2-auth-cms-crud/task-02]
status: planned
spec: advisordesk-prd.md §4, §7.2, §9
---

# task-02 — Embeddings and the real transactional lifecycle

## Goal

The phase-2 `ChunkPipeline` seam is filled with the real thing: publish chunks + embeds + inserts
in one transaction; edit-of-published re-chunks; archive/delete remove chunks; embedding failure
rolls the whole transaction back (§4 atomicity). After this task the §4 guarantee is enforced by
construction, and phase-5's `publish`/`edit_content`/`archive`/`delete_content` tools get real
behavior for free.

## Context (read ONLY these)

- `advisordesk-prd.md` §4 "Lifecycle rule (critical)" + atomicity paragraph (normative), §7.2
  (embedding model, batch per content item), §9 (rollback test is explicit).
- `app/services/lifecycle.py` + `app/services/content.py` (phase-2) — the seam to fill;
  **signatures must not change**.
- `CONVENTIONS.md` §3 (flush-never-commit), §10 (protocol seams).

## Files

- Create: `apps/api/app/rag/{embeddings.py,pipeline.py}`
- Create: `apps/api/tests/test_lifecycle.py`
- Modify: `apps/api/app/main.py` (wire `EmbeddingChunkPipeline` as the app's pipeline),
  `apps/api/pyproject.toml` (runtime dep: `openai`)

## Interfaces

- **Consumes:** `chunk_markdown`/`ChunkData` (task-01); `ChunkPipeline` protocol + content
  services (p2-t02); `Chunk` model (p1-t02).
- **Produces (later tasks rely on — produce exactly):**
  - `app.rag.embeddings`: `class Embedder(Protocol): def embed_texts(self, texts:
    Sequence[str]) -> list[list[float]]` · `class OpenAIEmbedder(Embedder)` (model
    `text-embedding-3-small`, 1536 dims, one batched call per content item §7.2, raises
    `EmbeddingFailedError` on API errors). **Retrieval (phase-4 task-01) reuses `Embedder` for
    query embedding.**
  - `app.rag.pipeline`: `class EmbeddingChunkPipeline(ChunkPipeline)` —
    `__init__(embedder: Embedder)`; `rebuild_chunks(session, content)` deletes old rows for the
    content id, chunks `body_md`, embeds, inserts new `Chunk` rows (flush, no commit) and returns
    the count; `remove_chunks(session, content_id)` deletes and returns count.
  - Factory wiring: `create_app(..., chunk_pipeline=None)` now defaults to Noop only in tests;
    `main.py` passes `EmbeddingChunkPipeline(OpenAIEmbedder(settings))`.

## Steps (TDD)

- [ ] **Step 1: Failing lifecycle tests** (`test_lifecycle.py`; DB fixture + `FakeEmbedder`
  returning deterministic vectors, and `FailingEmbedder` raising on call):
  - publish a draft → chunk rows exist with correct `chunk_index` order and 1536-dim vectors;
    status `published`, `published_at` set — all in one transaction;
  - edit a published item → old chunk rows gone, new rows present, count matches new chunking;
  - edit a draft → embedder never called;
  - archive → chunks removed, status `archived`;
  - delete → chunks removed AND `is_deleted=True`, status/`published_at` untouched (§4);
  - **rollback pin (§9): publish with `FailingEmbedder` → `EmbeddingFailedError` raised, item
    still `draft`, zero chunk rows; edit-of-published with `FailingEmbedder` → previous chunks
    intact, body unchanged in DB** (assert via a fresh session — nothing partial is visible);
  - batch pin: `FakeEmbedder` records exactly one `embed_texts` call per rebuild (§7.2).
- [ ] **Step 2:** run → FAIL. **Step 3: implement** `embeddings.py` + `pipeline.py`, wire
  `main.py`. **Step 4:** run → PASS.
- [ ] **Step 5: Gates → commit:**
  `feat(api): real embedding lifecycle with atomic rollback (phase-3 task-02)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_lifecycle.py -q   # all passed
grep -rn "OpenAIEmbedder" tests/                                  # no hits — seam only in prod wiring
uv run mypy && uv run lint-imports                                # clean
```

## Acceptance

- Every §4 lifecycle bullet has a passing test, including both rollback paths (§9).
- Phase-2 service signatures untouched (`git diff` on `services/content.py` shows wiring-only
  changes at most); the admin editor from phase-2 publishes with real embeddings, zero UI change.
- The real OpenAI client appears only in `main.py` wiring, never in tests.
