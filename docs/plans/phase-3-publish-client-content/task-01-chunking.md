---
id: task-01
phase: phase-3-publish-client-content
depends_on: []
status: planned
spec: advisordesk-prd.md §7.1, §9
---

# task-01 — Markdown chunking module

## Goal

`chunk_markdown(body_md)` deterministically splits article markdown by headings into ~500-token
chunks with 50-token overlap (§7.1), preserving order via `chunk_index`. Pure function — the
lifecycle pipeline (task-02) and the groundedness harness (phase 7) both call it.

## Context (read ONLY these)

- `advisordesk-prd.md` §7.1 (the algorithm, normative) and §9 (chunking unit tests are an
  explicit test requirement).
- `CONVENTIONS.md` §1, §9 (style/tooling only — this module has no other deps).

## Files

- Create: `apps/api/app/rag/chunking.py`
- Create: `apps/api/tests/test_chunking.py`
- Modify: `apps/api/pyproject.toml` (runtime dep: `tiktoken`)

## Interfaces

- **Consumes:** nothing internal (pure module).
- **Produces (later tasks rely on — produce exactly):**
  - `@dataclass(frozen=True) ChunkData: text: str; chunk_index: int; token_count: int`
  - `chunk_markdown(body_md: str, *, target_tokens: int = 500, overlap_tokens: int = 50)
    -> list[ChunkData]`
  - `count_tokens(text: str) -> int` (tiktoken `cl100k_base` — implementation note: PRD says
    "tokens" without naming a tokenizer).
- **Algorithm (pin in tests, not just prose):** split on markdown headings (`^#{1,6} `) into
  sections; pack whole sections up to `target_tokens`; a section longer than `target_tokens`
  splits on paragraph boundaries with `overlap_tokens` of trailing overlap between adjacent
  chunks; `chunk_index` is 0-based document order; empty/whitespace body → `[]`.

## Steps (TDD)

- [ ] **Step 1: Write the failing tests** (`test_chunking.py`, no DB — plain unit tests):
  - heading split: two `## `-headed sections under 500 tokens each → 2 chunks, boundaries at the
    headings, indices `[0, 1]`;
  - long-section split: a single section of ~1200 synthetic tokens → chunks each ≤ ~550 tokens,
    and the first `overlap_tokens` tokens of chunk N+1 appear at the tail of chunk N (assert on
    token lists, not chars);
  - order + indices: shuffled input headings come back in document order with contiguous indices;
  - short doc: one paragraph → exactly one chunk, index 0;
  - empty body: `chunk_markdown("") == []`;
  - determinism: two calls give equal results.
- [ ] **Step 2:** `uv run pytest tests/test_chunking.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement** `chunking.py` minimal-to-green (pure; no I/O; no imports from other
  `app.*` packages except none — keep it leaf-clean).
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Gates → commit:** `feat(api): markdown chunking module (phase-3 task-01)`

## Verify

```bash
cd apps/api
uv run pytest tests/test_chunking.py -q     # all passed, no DB, fast
uv run mypy && uv run ruff check .          # clean
```

## Acceptance

- §9's "chunking unit tests" exist and pass: heading split, overlap continuity, ordering,
  single-chunk, empty-body, determinism.
- Function is pure and dependency-light; tokenizer choice recorded as an implementation note in
  the README.
