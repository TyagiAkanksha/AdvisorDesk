---
id: task-04
phase: phase-4-rag-assistant
depends_on: [phase-3-publish-client-content/task-02]
status: built
spec: advisordesk-prd.md §8, §8.1, §4.1
---

# task-04 — Seed articles, seed script, and the evaluation question set

## Goal

~20 original sample advisory articles exist across the six §8 tags, a seed script loads and
publishes them through the real embed pipeline (3–4 left as drafts for agent demos), and
`seed/eval_questions.yaml` is authored against those articles for the phase-7 groundedness
harness (§8.1). Also yields the §9.1 "seeded documents and chunks" metric inputs.

## Context (read ONLY these)

- `advisordesk-prd.md` §8 (corpus spec: tags, frontmatter, drafts, ORIGINAL content, disclaimer
  footer line verbatim), §8.1 (question-set shape + the YAML example), §4.1 (seeded rows carry
  null actor columns).
- `app/services/content.py` + `app/rag/pipeline.py` — the seed script goes through these, never
  raw SQL.

## Files

- Create: `seed/sample_content/*.md` (~20 files, named by slug, e.g.
  `roth-ira-conversion-basics.md`)
- Create: `seed/eval_questions.yaml`
- Create: `apps/api/app/seed.py` (PRD-pinned path; runnable `python -m app.seed`)
- Create: `apps/api/tests/test_seed.py`
- Modify: `apps/api/pyproject.toml` (runtime dep: `pyyaml`; frontmatter parsed with it)

## Interfaces

- **Consumes:** `create_draft`/`publish_content` + `EmbeddingChunkPipeline` (real embedder in
  prod runs; fake in tests); tags service.
- **Produces (later tasks rely on — produce exactly):**
  - Corpus invariants: every file has YAML frontmatter `title` / `tags` (⊆ the six §8 tags) /
    `status` (`published` | `draft`); body ends with the §8 footer line *"Sample content for
    demonstration purposes — not financial advice."*; 16–17 published, 3–4 drafts; all six tags
    used ≥2 times.
  - `app.seed`: `seed_all(session, pipeline, content_dir=Path("seed/sample_content")) -> SeedReport`
    (`SeedReport{created: int, published: int, skipped: int, chunk_count: int}`) — idempotent by
    slug (existing slug → skipped; implementation note); rows created with `actor_id=None`
    (§4.1). `__main__` block wires real settings/engine/pipeline.
  - `seed/eval_questions.yaml` — list items exactly per §8.1: `question`,
    `expected_slugs: [<slug>, ...]`, `answerable: bool`; ~12 answerable (each expected slug
    exists in the corpus), ~3 uncovered (topics deliberately absent, e.g. crypto staking).
    **Phase-7 task-02 consumes this file verbatim.**

## Steps (TDD)

- [ ] **Step 1: Author the articles** (~20 original pieces, 400–900 words each, spread over
  `retirement`, `tax-planning`, `estate-planning`, `investing-basics`, `college-savings`,
  `insurance`; frontmatter + footer per Interfaces; no real-firm material).
- [ ] **Step 2: Failing seed tests** (`test_seed.py`, fake embedder pipeline): `seed_all` on the
  real `seed/sample_content/` creates one content row per file with correct tags/status; drafts
  have zero chunks; published items have >0 chunks; `author_id IS NULL` on all seeded rows (§4.1
  pin); second run → all `skipped`, row count unchanged (idempotency pin); report numbers add up.
- [ ] **Step 3:** run → FAIL. **Step 4: implement** `app/seed.py`. **Step 5:** run → PASS.
- [ ] **Step 6: Author `eval_questions.yaml`** against the corpus; add a validation test in
  `test_seed.py`: YAML parses; answerable questions' `expected_slugs` all exist among published
  seed slugs; ≥3 entries have `answerable: false` with empty `expected_slugs`.
- [ ] **Step 7:** run → PASS. **Step 8: Real run** against local-db:
  `docker compose -f infra/docker-compose.yml --profile local-db up -d` → migrate →
  `uv run python -m app.seed` → record doc/chunk counts in README Implementation notes (§9.1
  input).
- [ ] **Step 9: Gates → commit:** `feat(seed): sample corpus + seed script + eval set (phase-4 task-04)`

## Verify

```bash
ls seed/sample_content/*.md | wc -l         # ~20
grep -L "not financial advice" seed/sample_content/*.md   # empty (footer everywhere)
cd apps/api && TEST_DATABASE_URL=... uv run pytest tests/test_seed.py -q  # all passed
uv run python -m app.seed                    # against local-db: prints SeedReport; re-run: all skipped
```

## Acceptance

- §8 satisfied: ~20 original articles, six tags, frontmatter, drafts for agent demos, footer
  line verbatim, loaded via the real service + embed path.
- §8.1 satisfied: eval YAML matches the spec shape and cross-references only real slugs.
- Idempotent re-runs; seeded rows carry null actors; doc/chunk counts recorded for §9.1.
