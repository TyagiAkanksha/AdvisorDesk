---
id: p9-t09
phase: phase-9-eval-data-loop
depends_on: [p9-t03, p9-t05, p9-t06]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 09 — Baseline: 3 persisted harness runs on the current corpus; retire the 58.8%

## Goal

Prove determinism *before* any content changes, and give every later comparison something to
compare against. Run the harness three times over the **current** (unchanged) 21-file corpus at
`temperature=0` with the `gpt-4o` judge, persist all three under one label, and record the run
ids and the run-to-run spread in a committed verification record. Then retire the README's
committed `58.8%` — it was measured under a `temperature=1.0` answerer (fixed 2026-09-11) with a
`gpt-4o-mini` judge, so it is sampling noise, and the honest replacement is a link to persisted,
reproducible runs rather than a new single number nobody can re-derive.

**This task writes no application code.** It is a measurement run plus two documents. Its
"tests" are the existing suite staying green and the recorded output being reproducible.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §B3 ("Baseline discipline") and
  §"Evaluation approach" (Reporting/stability row).
- `docs/plans/phase-7-evaluation/verification-record.md` §1 — the format this task's record
  mirrors, and the source of the 58.8% figure being retired.
- `README.md` §"Metrics" (lines 265-285 at the time of writing) — the table row and the
  "Groundedness note" paragraph this task rewrites.
- `apps/api/app/eval/groundedness.py` `_run_from_cli` (tasks 03/05/06) — `--label`, `--runs`, the
  stability block, the per-class rollup, the failure-cause distribution.
- `.superpowers/sdd/phase-9-eval-data-loop/` — where the raw capture goes (gitignored).
- Local environment facts: the Postgres container `advisordesk-test-db` listens on
  `127.0.0.1:5433`; the root `.env` holds `DATABASE_URL` and `OPENAI_API_KEY`.

## Files

**Create**
- `docs/plans/phase-9-eval-data-loop/verification-record.md`

**Modify**
- `README.md` (the `## Metrics` table row + the groundedness note)

**No code, no tests, no migration.**

## Interfaces

Nothing this task produces is imported by other code. What it produces for *later tasks* is:

| Artifact | Consumer |
|---|---|
| the three baseline `eval_runs.id` values (label `baseline-2026-09`) | task 16's `accept_proposal` gate, task 18's before/after run ids |
| the measured spread per metric | the talk's "stability" slide; the rule that a metric without a spread is not reported |
| `verification-record.md` | the whole-branch final review |

## Steps

- [ ] **1. Environment — export exactly two variables, never `source .env`.** Run from the repo
  root. `grep`/`cut` only; do not echo the values.

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export OPENAI_API_KEY="$(grep -m1 '^OPENAI_API_KEY=' .env | cut -d= -f2-)"
export BASE_DB_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"
# sanity, without printing secrets:
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY: set"
[ -n "$BASE_DB_URL" ] && echo "DATABASE_URL: set"
```

> The root `.env` has a known trailing-newline/whitespace gotcha. If a command fails with an auth
> or DSN error, re-export with `| cut -d= -f2- | tr -d '\r\n'` and note it in the record.

- [ ] **2. Create a dedicated baseline database** (never the dev or prod database):

```bash
docker exec advisordesk-test-db psql -U postgres -c 'CREATE DATABASE advisordesk_p9baseline;'
docker exec advisordesk-test-db psql -U postgres -d advisordesk_p9baseline \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;'
export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5433/advisordesk_p9baseline"
```

  (Take the user/password from `BASE_DB_URL`'s own shape if they differ; record the exact DSN
  **with the password redacted** in the verification record.)

- [ ] **3. Migrate and seed:**

```bash
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed
```

  Record the seed report line (`created/published/chunk_count`) verbatim. Expected on the
  unchanged corpus: 21 content rows (17 published + 4 drafts), 100 chunks — if it differs, STOP
  and report: the corpus moved, and this is no longer a baseline of "the current corpus".

- [ ] **4. Confirm the settings the run will use** (they must be the committed defaults, not local
  overrides):

```bash
uv run python -c "from app.config import Settings; s=Settings(); print(s.chat_model, s.judge_model, s.embedding_model, s.similarity_threshold)"
```

  Expect `gpt-4o-mini gpt-4o text-embedding-3-small 0.5`. Any deviation goes in the record.

- [ ] **5. The baseline run — three runs, one label:**

```bash
uv run python -m app.eval.groundedness --label baseline-2026-09 --runs 3 \
  | tee ../../.superpowers/sdd/phase-9-eval-data-loop/task-09-baseline-capture.txt
```

  This persists three `eval_runs` rows sharing `label='baseline-2026-09'` and prints three
  tables, three summary lines, the per-class rollup, the failure-cause distribution, and one
  stability block.

- [ ] **6. Collect the run ids and the corpus fingerprint:**

```bash
docker exec advisordesk-test-db psql -U postgres -d advisordesk_p9baseline -c \
  "SELECT id, created_at, pct_fully_supported, refusal_correct, refusal_total, corpus_digest, git_sha
     FROM eval_runs WHERE label = 'baseline-2026-09' ORDER BY created_at;"
docker exec advisordesk-test-db psql -U postgres -d advisordesk_p9baseline -c \
  "SELECT metrics->>'failure_cause' AS cause, count(*)
     FROM eval_results r JOIN eval_runs e ON e.id = r.run_id
    WHERE e.label = 'baseline-2026-09' AND r.verdict = 'FAIL'
    GROUP BY 1 ORDER BY 2 DESC;"
```

- [ ] **7. Prove `compare_runs` works on real data** (run 1 vs run 3 — same corpus, so a clean
  run should show zero regressions and zero improvements):

```bash
uv run python -m app.eval.groundedness --label baseline-2026-09-confirm --runs 1 --compare-to latest
```

  Record the printed `compare … -> …` line. If it shows regressions between two runs over an
  unchanged corpus, that is a **finding**, not a footnote: it means the pipeline is not
  deterministic yet and the whole "validated before acceptance" claim is weaker than DESIGN
  assumes. Report it to the controller before touching the README.

- [ ] **8. Write `docs/plans/phase-9-eval-data-loop/verification-record.md`** with these sections,
  in this order:
  1. **Scope & environment** — date, database name, DSN with the password redacted, provider and
     model ids from step 4, the `SIMILARITY_THRESHOLD`, the git SHA (`git rev-parse HEAD`), and
     the explicit note that only `OPENAI_API_KEY`/`DATABASE_URL` were exported (never `source`).
  2. **Corpus fingerprint** — the seed report line, `corpus_content_count`/`corpus_chunk_count`/
     `corpus_digest` from step 6.
  3. **The three runs** — a table of `run_id | created_at | pct_fully_supported | refusals`.
  4. **Stability** — the harness's own stability block, pasted verbatim, plus one sentence naming
     the spread per metric.
  5. **Failure-cause distribution** — the step-6 query output.
  6. **`compare_runs` confirmation** — the step-7 line.
  7. **Retiring 58.8%** — one short paragraph: what it was, why it is noise (`temperature=1.0`
     answerer until 2026-09-11; `gpt-4o-mini` judging itself; single unpersisted run), and what
     replaces it (three persisted runs under one label, reported with their spread).
  8. **Raw output** — the path to the gitignored capture file from step 5.

- [ ] **9. Update `README.md` §"Metrics".** Replace the Groundedness table row's value with the
  baseline mean **and its spread** (e.g. `76.5% ± 0.0 fully supported over 3 runs (label
  baseline-2026-09); refusals 4/4 correct`), and replace the whole "**Groundedness note:**"
  paragraph with:

```markdown
**Groundedness note (updated 2026-09, phase 9):** the previously published 58.8% was a single,
unpersisted run measured while the answerer still ran at `temperature=1.0` (fixed 2026-09-11) and
was judged by the same `gpt-4o-mini` model that wrote the answers — it was sampling noise, not a
measurement, and it is retired rather than silently overwritten. Evaluation runs are now persisted
(`eval_runs`/`eval_results`) and every metric is reported with its spread over three runs; the
baseline above is the label `baseline-2026-09`, judged by `gpt-4o` (the answerer stays
`gpt-4o-mini`). Full method, run ids and per-class/failure-cause breakdowns:
[`docs/plans/phase-9-eval-data-loop/verification-record.md`](docs/plans/phase-9-eval-data-loop/verification-record.md).
```

  Also update the "Seeded documents/chunks" rows only if step 3's numbers differ from the
  committed ones — otherwise leave them.

- [ ] **10. Gates + commit.** `pnpm gates:api` (nothing should have changed, but the branch must
  stay green), then:
  `git add README.md docs/plans/phase-9-eval-data-loop/verification-record.md`
  `git commit -m "docs: baseline eval runs (baseline-2026-09); retire the 58.8% as sampling noise (p9 t09)"`

- [ ] **11. Clean up** (after the record is written — the DB is disposable, the record is not):

```bash
docker exec advisordesk-test-db psql -U postgres -c 'DROP DATABASE advisordesk_p9baseline;'
```

## Verify

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
grep -n "baseline-2026-09" README.md docs/plans/phase-9-eval-data-loop/verification-record.md
grep -c "58.8" README.md          # the old figure survives only inside the retirement paragraph
pnpm gates:api
```

## Acceptance

- Three `eval_runs` rows exist with `label='baseline-2026-09'`, the same `corpus_digest`, and
  their ids are recorded in `verification-record.md`.
- The record states the measured spread for `pct_fully_supported` and `refusal_correct`, not just
  their means.
- The failure-cause distribution over the baseline's FAIL rows is recorded (this is the
  before-picture the corpus tasks are judged against).
- `compare_runs` was run against real persisted rows and its output is recorded; any regression
  between two runs over an unchanged corpus was escalated to the controller before the README was
  touched.
- `README.md` no longer presents 58.8% as a current metric; the retirement is explained, not
  hidden, and points at the committed record.
- No secrets appear in either document (the DSN is password-redacted), and `.env` was never
  `source`d.

## Report

- Runner: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-09-implementer.md` — include the
  exact commands run, the run ids, and anything that deviated from the expected seed counts or
  model ids. (No test-author for this task: it produces no code. State that explicitly in the
  report so the reviewer does not read it as a missing artifact.)
