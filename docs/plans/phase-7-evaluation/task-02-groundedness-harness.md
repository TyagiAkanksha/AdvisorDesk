---
id: task-02
phase: phase-7-evaluation
depends_on: [phase-4-rag-assistant/task-04, phase-4-rag-assistant/task-02]
status: built
spec: advisordesk-prd.md §8.1, §10 Phase 7, §9.1
---

# task-02 — Groundedness harness

## Goal

A CLI harness runs every `seed/eval_questions.yaml` question through the real chat path and
reports, as a summary table: % of answers fully supported by their cited chunks, expected-slug
hit rate, and refusal correctness on the uncovered questions (§10 Phase 7). Produces the §9.1
groundedness metric.

## Context (read ONLY these)

- `advisordesk-prd.md` §8.1 (file shape + expected outcomes), §10 Phase 7 (report contents),
  §9.1 (the metric).
- `app/services/chat.py` + `app/rag/{retrieval,synthesis}.py` (p4) — drive the service path
  directly (not HTTP/SSE); chunk-level citations are exactly why the DB stores them (§4).

## Files

- Create: `apps/api/app/eval/__init__.py`, `apps/api/app/eval/groundedness.py` (runnable
  `python -m app.eval.groundedness`)
- Create: `apps/api/tests/test_groundedness.py`

## Interfaces

- **Consumes:** `seed/eval_questions.yaml` (p4-t04); retrieval + synthesis seams; recorded
  chunk-level citations.
- **Produces (later tasks rely on — produce exactly):**
  - `app.eval.groundedness`: `run_eval(session, *, embedder, chat_llm, judge: GroundednessJudge,
    questions_path) -> EvalReport` with
    `EvalReport{rows: list[EvalRow], pct_fully_supported: float, refusal_correct: int,
    refusal_total: int}`;
    `EvalRow{question, answerable, expected_slugs, cited_slugs, slugs_hit: bool,
    fully_supported: bool | None, refused: bool, verdict: str}`.
  - `class GroundednessJudge(Protocol): def is_supported(self, claim_text: str,
    chunk_texts: Sequence[str]) -> bool` · `OpenAIJudge` (gpt-4o-mini, temperature 0 —
    implementation note: judging method is not PRD-prescribed). Answer split into sentences;
    "fully supported" = every sentence supported by the union of its cited chunks.
  - Verdict rules: answerable → PASS iff `expected_slugs ⊆ cited_slugs` AND fully supported;
    uncovered → PASS iff refused AND `retrieval_found=False` AND zero citations (§8.1 expected
    outcome).
  - `__main__` prints the per-question table + summary line
    `groundedness: <pct>% fully supported; refusals <k>/<n> correct` — **the line phase-7
    task-03 records into the README.**

## Steps (TDD)

- [ ] **Step 1: Failing harness tests** (`test_groundedness.py`; fake embedder/LLM/judge, seeded
  mini-corpus — never the real API):
  - answerable question with scripted citations covering the expected slug + all-true judge →
    PASS row, counted in `pct_fully_supported`;
  - expected slug missing from citations → FAIL row even with a true judge (slug check is
    independent);
  - one unsupported sentence (judge false once) → `fully_supported=False`;
  - uncovered question: scripted refusal (no sources) → refusal-correct; scripted hallucinated
    answer → refusal-incorrect;
  - report arithmetic adds up; YAML loading validates the §8.1 shape.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** the module. **Step 4:** run → PASS.
- [ ] **Step 5: Real recorded run** against the seeded local-db stack with the real judge:
  `uv run python -m app.eval.groundedness` → save the table output (input to task-03).
- [ ] **Step 6: Gates → commit:** `feat(api): groundedness harness (phase-7 task-02)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_groundedness.py -q   # all passed (no real API)
uv run python -m app.eval.groundedness    # against seeded local-db + real judge:
                                          # per-question table + summary line prints
```

## Acceptance

- §10 Phase 7's report exists: summary table with % fully supported + refusal correctness,
  driven by `seed/eval_questions.yaml` verbatim.
- Judge is injectable; tests never call OpenAI; the real run is recorded for task-03.
- Uncovered-question expectations match §8.1 exactly (`retrieval_found=false`, refusal, no
  citations).
