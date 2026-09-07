---
id: task-01
phase: phase-4-rag-assistant
depends_on: [phase-3-publish-client-content/task-02]
status: built
spec: advisordesk-prd.md §7.3, §7.4, §9
---

# task-01 — Retrieval with the similarity convention

## Goal

`retrieve()` embeds a query, runs HNSW nearest-neighbor over `chunks`, converts distance to
similarity **once**, applies the threshold, and returns typed results plus `top_similarity`. The
§7.3 implementation trap is neutralized by a pin test. Task-02 (chat) is this module's only
consumer.

## Context (read ONLY these)

- `advisordesk-prd.md` §7.3 (read the "implementation trap" paragraph twice — `<=>` is
  DISTANCE), §7.4 (what must be recorded), §9 (the pin test is an explicit requirement).
- `app/rag/embeddings.py` (phase-3) — the `Embedder` protocol for query embedding. **v1.5: the
  model is asymmetric; `retrieve()` MUST call `embedder.embed_texts([query],
  input_type="query")` — never the `"passage"` default (that side is publish-time only).**
- `CONVENTIONS.md` §3 (session-first), §10 (seams).

## Files

- Create: `apps/api/app/rag/retrieval.py`
- Create: `apps/api/tests/test_retrieval.py`

## Interfaces

- **Consumes:** `Embedder` (p3-t02); `Chunk`/`Content` models.
- **Produces (later tasks rely on — produce exactly):**
  - `@dataclass(frozen=True) RetrievedChunk: chunk_id: uuid.UUID; content_id: uuid.UUID;
    title: str; slug: str; text: str; similarity: float`
  - `@dataclass(frozen=True) RetrievalResult: chunks: list[RetrievedChunk];
    top_similarity: float | None` — `chunks` only those clearing the threshold, ordered by
    similarity desc; `top_similarity` = best similarity observed even when below threshold; None
    iff the index returned nothing (§7.4 semantics).
  - `retrieve(session, embedder, query: str, *, k: int = 6, threshold: float)
    -> RetrievalResult` — joins `chunks → content` (published, non-deleted — belt-and-braces on
    top of the lifecycle guarantee). `threshold` is passed explicitly by the caller; the runtime
    value is `Settings.similarity_threshold` (already exists, default 0.35 per §7.3 — task-02
    wires it; this module never reads `Settings` itself).
  - `def similarity_from_distance(distance: float) -> float: return 1.0 - distance` — **the one
    place the conversion exists.**

## Steps (TDD)

- [ ] **Step 1: Write the pin test first** (`test_retrieval.py`, pure — no DB):
  ```python
  def test_similarity_conversion_pin():
      """PRD §7.3: pgvector <=> is cosine DISTANCE; similarity = 1 - distance.

      identical vectors: distance 0.0 -> similarity 1.0
      orthogonal:        distance 1.0 -> similarity 0.0
      """
      assert similarity_from_distance(0.0) == 1.0
      assert similarity_from_distance(1.0) == 0.0
  ```
- [ ] **Step 2: Failing integration tests** (DB fixture, `FakeEmbedder` with hand-built vectors
  so cosine distances are known): top-k ordering by similarity desc; threshold drops chunks below
  `threshold` but `top_similarity` still reports the best raw value; empty index →
  `RetrievalResult([], None)`; a chunk whose content was archived after embedding is excluded by
  the join (belt-and-braces); k defaults to 6; **v1.5 query-side pin: the fake embedder records
  its `input_type` kwarg and the test asserts `retrieve()` called it with `"query"`.**
- [ ] **Step 3:** `uv run pytest tests/test_retrieval.py -q` → FAIL.
- [ ] **Step 4: Implement** `retrieval.py` — the SQL orders by `embedding <=> :qvec` and converts
  via `similarity_from_distance` only; carries the §7.3 comment.
- [ ] **Step 5:** run → PASS.
- [ ] **Step 6: Gates → commit:** `feat(api): retrieval with similarity convention (phase-4 task-01)`

## Verify

```bash
cd apps/api
uv run pytest tests/test_retrieval.py -q                       # pin test passes without DB
TEST_DATABASE_URL=... uv run pytest tests/test_retrieval.py -q # integration too
grep -rn "1 - \|1.0 - " app/ --include='*.py' | grep -i simil  # exactly one hit: retrieval.py
```

## Acceptance

- The §9 similarity-conversion pin test exists and passes; the conversion lives in exactly one
  function.
- Threshold semantics match §7.4: below-threshold chunks dropped, `top_similarity` still real,
  `None` only when the index is empty.
- Only published, non-deleted content can surface (join-enforced).
