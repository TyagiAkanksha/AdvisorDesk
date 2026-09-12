# Phase-9 task-09 — Baseline verification record

Three persisted harness runs (label `baseline-2026-09`) over the current, unchanged 21-file
corpus at `temperature=0`, judged by `gpt-4o` — proving determinism *before* any content changes
and giving every later comparison (task 16's `accept_proposal` gate, task 18's before/after
diffs) something reproducible to compare against. Also retires the phase-7 `58.8%` figure (§7)
and records a one-run agent-suite baseline (§9).

---

## 1. Scope & environment

- **Date:** 2026-09-12.
- **Database:** dedicated, throwaway database `advisordesk_p9baseline` on the Postgres container
  `advisordesk-test-db` (`127.0.0.1:5433`) — never the dev or prod database. DSN (password
  redacted): `postgresql://postgres:***@127.0.0.1:5433/advisordesk_p9baseline`.
- **Provider/models (the committed defaults, confirmed via `Settings()`, not local overrides):**
  `chat_model=gpt-4o-mini`, `judge_model=gpt-4o`, `embedding_model=text-embedding-3-small`,
  `similarity_threshold=0.5`.
- **Git SHA:** `d368cf4646581e0bf1b680c5becb876b2eacbe00` (`git rev-parse HEAD` at run time;
  matches every `eval_runs.git_sha` value recorded below).
- **Environment discipline:** only `LLM_PROVIDER`, `OPENAI_API_KEY`, `CHAT_MODEL`,
  `EMBEDDING_MODEL` (by name, via `grep`/`cut`/`tr` against the root `.env`) and `DATABASE_URL`
  (the baseline DSN above, derived from `TEST_DATABASE_URL` by substituting the database name,
  never hard-coded) were exported for every command in this record. `.env` was never `source`d;
  no secret value was ever printed. (Note: the extraction pattern must strip **both** quote
  characters — `tr -d '"'"'"'\r'`, i.e. the character set `"'\r` — not only double quotes; the
  root `.env`'s `OPENAI_API_KEY` line is single-quoted, and a pattern that strips only `"` and
  `\r` leaves the literal quote characters in the value, which OpenAI correctly rejects as an
  invalid key. Confirmed with the corrected pattern before any run: key length 164, prefix `sk-`.)
- **Cleanup (step 11): skipped on purpose.** Per controller ruling, `advisordesk_p9baseline` is
  kept until the whole-branch final review rather than dropped immediately, so this record's
  numbers remain independently re-checkable against the live rows for as long as that review
  needs them.

## 2. Corpus fingerprint

Seed report line (verbatim), matching the expected unchanged-corpus counts exactly:

```
seed_all: created=21 published=17 skipped=0 chunk_count=100
```

From `eval_runs` (identical across all three baseline rows):

| Field | Value |
|---|---|
| `corpus_content_count` | 17 |
| `corpus_chunk_count` | 100 |
| `corpus_max_updated_at` | 2026-09-12 22:40:31.889339+00 |
| `corpus_digest` | `63517ca0ba3ccbd1` |

## 3. The three runs

| run_id | created_at | pct_fully_supported | refusals |
|---|---|---|---|
| `e3d78165-7f75-4c90-aa13-368afa096cd6` | 2026-09-12 22:42:33.241755+00 | 70.6% | 4/4 |
| `592d9be6-8c78-47ff-b685-2963b4f77bb5` | 2026-09-12 22:44:32.727579+00 | 76.5% | 4/4 |
| `2d1543b5-3da0-4cf3-b1f0-d868351da910` | 2026-09-12 22:46:51.138782+00 | 70.6% | 4/4 |

All three share `label='baseline-2026-09'`, `corpus_digest='63517ca0ba3ccbd1'`, and
`git_sha='d368cf4646581e0bf1b680c5becb876b2eacbe00'`.

## 4. Stability

Harness stability block, pasted verbatim:

```
stability over 3 runs (label=baseline-2026-09):
  pct_fully_supported  mean 72.5  spread 5.9  [70.6, 76.5, 70.6]
  refusal_correct      mean 4.0  spread 0  [4, 4, 4]
```

`pct_fully_supported` has a 5.9-point spread across three identical-corpus, `temperature=0` runs
— the judge's sentence-level faithfulness calls are not perfectly deterministic even at
temperature 0 (the one question that flips PASS/FAIL between runs is
"What is an index fund and how does it differ from an actively managed fund?", judged
`generation_unfaithful` in runs 1 and 3 but supported in run 2). `refusal_correct` has zero
spread — refusal behavior over the 4 off-domain questions is fully deterministic.

## 5. Failure-cause distribution

Query output over all three baseline runs' `FAIL` rows:

```
         cause         | count
------------------------+-------
 generation_unfaithful  |    14
```

Every failure across all three runs is `generation_unfaithful` (the judge scoring some answer
sentence as unsupported by its cited chunk) — there are zero `retrieval_miss` failures; every
answerable question's `slugs_hit` is `True` in every run. This is the before-picture the corpus
tasks (waves 1/2) are judged against.

## 6. `compare_runs` confirmation

A fourth run (`baseline-2026-09-confirm`, one run) compared against the latest baseline run
(run 3, `2d1543b5-3da0-4cf3-b1f0-d868351da910`) over the same unchanged corpus:

```
compare 2d1543b5-3da0-4cf3-b1f0-d868351da910 -> 63700014-61b6-4aab-9668-cc1081a668f2: pct 70.6 -> 76.5 (+5.9); regressions 0; improvements 1; added 0; removed 0
```

**Zero regressions** — `compare_runs` correctly reports no question moving from PASS to FAIL
between two runs of the same corpus. It does report one improvement (the same
index-fund question flipping FAIL→PASS noted in §4), consistent with the non-zero
`pct_fully_supported` spread already recorded above, not a new finding. Per the task's
escalation rule ("any regression... is a finding, not a footnote"), only a **regression** would
have blocked the README edit below; there was none, so no escalation to the controller was
required.

## 7. Retiring 58.8%

The phase-7 `58.8%` groundedness figure (`docs/plans/phase-7-evaluation/verification-record.md`
§1) was a **single, unpersisted** run captured while the answerer (`chat_model`) still ran at
`temperature=1.0` (fixed 2026-09-11 — the answerer now runs at `temperature=0`, per DESIGN and
the phase-9 global constraints) and was judged by `gpt-4o-mini` — the **same model that wrote the
answers**, judging its own output. Combined, a non-deterministic answerer plus a same-family
judge plus a sample size of one run makes 58.8% sampling noise, not a measurement: this task's
own three `temperature=0` runs on the identical corpus already range from 70.6% to 76.5% (a
5.9-point spread) despite deliberately holding temperature at zero. 58.8% is retired rather than
silently overwritten; it is replaced by the three persisted runs above (label
`baseline-2026-09`), judged by the stronger `gpt-4o` model, reported with their spread — not a
single new number nobody can re-derive.

## 8. Raw output

Full raw stdout of the three-run `--label baseline-2026-09 --runs 3` invocation (all three
per-question tables, class rollups, and the stability block) is captured verbatim (gitignored) at
`.superpowers/sdd/phase-9-eval-data-loop/task-09-baseline-capture.txt`.

## 9. Agent suite baseline

One agent-suite run (`--label agent-baseline-2026-09`) against the **same** fresh baseline
database, run **last** — after every answer-run measurement above — because the agent suite
mutates real content rows (drafts/publishes/tags/archives) and would otherwise change the corpus
out from under the read-only groundedness runs. The suite needs one `users` row to stamp as
`actor_id`; inserted directly (all other `users` columns are nullable or carry a server default):

```sql
INSERT INTO users (id, email, name) VALUES (gen_random_uuid(), 'eval-runner@example.com', 'Eval Runner');
```

Per-task lines (10 tasks from `seed/agent_tasks.yaml`, run through the real agent loop):

```
draft-and-tag                PASS  steps=1 precision=1.00 recall=1.00 looped=False
count-published-by-tag       PASS  steps=1 precision=1.00 recall=1.00 looped=False
publish-drafts-with-tag      PASS  steps=2 precision=1.00 recall=1.00 looped=False
archive-by-title             PASS  steps=2 precision=1.00 recall=1.00 looped=False
edit-a-body                  PASS  steps=2 precision=1.00 recall=1.00 looped=False
add-and-remove-tags          PASS  steps=3 precision=0.67 recall=1.00 looped=False
report-weak-queries          PASS  steps=1 precision=1.00 recall=1.00 looped=False
propose-a-fix-from-a-gap     PASS  steps=2 precision=1.00 recall=1.00 looped=False
draft-publish-verify         PASS  steps=2 precision=1.00 recall=1.00 looped=False
ambiguous-cleanup-should-ask PASS  steps=1 precision=0.00 recall=1.00 looped=False
agent suite: 100.0% tasks passed (10/10)
recorded eval_runs id=af58f287-eaa6-49c1-82e1-44096f74193d
```

Run id: `af58f287-eaa6-49c1-82e1-44096f74193d` (`label='agent-baseline-2026-09'`,
`kind='agent'`, `git_sha='d368cf4646581e0bf1b680c5becb876b2eacbe00'`) — **10/10 tasks passed
(100.0%)**. Two tasks show `precision < 1.0` despite passing (`add-and-remove-tags` at 0.67,
`ambiguous-cleanup-should-ask` at 0.00 — the latter by design: the reference trajectory for that
task is to ask a clarifying question rather than call a tool, so a `PASS` with zero tool-call
precision is the correct/expected outcome, not a defect); every task's `recall=1.00` and no task
looped.

**Ordering note for future runs:** the agent suite must always run **last** on a fresh,
disposable database — never before or interleaved with answer-run measurements — because it
mutates content (drafts, publishes, tag edits, archives) that would otherwise change the corpus
fingerprint the groundedness runs are supposed to be measuring against.

## No secrets

No API key, password, or DSN password appears anywhere in this record. Every DSN shown has its
password redacted (`***`).
