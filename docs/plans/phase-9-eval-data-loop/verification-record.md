# Phase-9 task-09 — Baseline verification record

Three persisted harness runs (label `baseline-2026-09`) over the current, unchanged 21-file
corpus at `temperature=0`, judged by `gpt-4o` — proving determinism *before* any content changes
and giving every later comparison (task 16's `accept_proposal` gate, task 18's before/after
diffs) something reproducible to compare against. Also retires the phase-7 `58.8%` figure (§7)
and records a one-run agent-suite baseline (§9).

---

> **SUPERSEDED (2026-09-13) — see the `rebaseline-2026-09` section at the end of this file.**
> This section's numbers (72.5% ± 5.9 fully supported, `gpt-4o-mini` answerer / `gpt-4o` judge,
> the 21-question set) are retired as the comparison baseline for the 2026-09-24 talk and the
> README, for four reasons — all shipped since this record was written:
>
> 1. **Task 05b** — the judge no longer scores markdown list markers or `[n]` citation markers as
>    unsupported claims.
> 2. **Task 05c** — a model-level decline now counts as a correct refusal, and every FAIL row
>    records its own unsupported sentences.
> 3. **Task 05d** — sentence splitting survives abbreviations, the answerer no longer appends an
>    ungrounded "consult the advisory team" closer sentence, and the answerer/judge pair moved to
>    `gpt-5.4-mini`/`gpt-5.4`.
> 4. **Wave 1** — the corpus grew from 21 files (17 published/100 chunks) to 37 files (33
>    published/228 chunks), and the golden question set grew from 21 to 80 questions across six
>    classes (`answerable`, `multi_source`, `near_miss`, `off_domain`, `threshold`,
>    `stale_number`), replacing the old flat answerable/off_domain split.
>
> The measurement method below remains historically accurate for what it measured at the time —
> it is superseded, not wrong, and is kept intact rather than deleted.

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

---

# Phase-9 rebaseline verification record (`rebaseline-2026-09`)

Three persisted harness runs (label `rebaseline-2026-09`) over the current corpus (37 files / 33
published / 228 chunks) and the 80-question golden set, at `temperature=0`, answered by
`gpt-5.4-mini` and judged by `gpt-5.4` — produced 2026-09-13 to replace the superseded
`baseline-2026-09` record above for the 2026-09-24 talk and the README. Also records a one-run
agent-suite re-baseline (§9) and two judge scorecards (§10).

## 1. Scope & environment

- **Date:** 2026-09-13.
- **Database:** dedicated, throwaway database `advisordesk_p9rebaseline` on the Postgres
  container `advisordesk-test-db` (`127.0.0.1:5433`) — never the dev or prod database. DSN
  (password redacted): `postgresql://postgres:***@127.0.0.1:5433/advisordesk_p9rebaseline`.
  Derived from `TEST_DATABASE_URL` by database-name substitution (never hard-coded); the shape
  was verified with a `case` pattern before use, and the derivation itself was never echoed.
- **Provider/models** (`Settings()`, confirmed live):

  ```
  gpt-5.4-mini gpt-5.4 0.0 text-embedding-3-small 0.5
  ```

  i.e. `chat_model=gpt-5.4-mini`, `judge_model=gpt-5.4`, `judge_temperature=0.0`,
  `embedding_model=text-embedding-3-small`, `similarity_threshold=0.5` — the gpt-5.4 pair at
  temperature 0, as expected.
  - **`.env`'s `CHAT_MODEL` note:** the root `.env` sets `CHAT_MODEL=gpt-5.4-mini` and
    `EMBEDDING_MODEL=text-embedding-3-small`, but this session's exported environment (following
    global-constraints.md's exact-extraction discipline) never exported either name —
    `Settings()` has no `env_file` configured, so it resolved both purely from the `app/config.py`
    class defaults (`chat_model: str = "gpt-5.4-mini"`, `embedding_model: str =
    "text-embedding-3-small"`), which happen to be byte-identical to the `.env` values. The
    harness's actual resolved value is confirmed correct either way; the equality with `.env` is
    coincidental, not causal.
  - **`retrieval_k` correction:** `s.retrieval_k` is not a `Settings` field — `Settings()` raises
    `AttributeError: 'Settings' object has no attribute 'retrieval_k'`. Retrieval `k` is the
    module constant `_RETRIEVAL_K = 6` in `app/eval/groundedness.py` (confirmed via direct import
    and via every persisted `eval_runs.retrieval_k` value below, all `6`). Noted here as a
    correction to the runner brief's literal `Settings()` probe command, not a runtime deviation.
- **Git SHA:** `a89fddafc3c1c0adae928da64c215d901f2f5fff` — captured once by the harness's
  `_git_sha()` before the 3-run loop, identical across all three persisted runs. This is commit
  `fix(api): registry count is pinned once, in the proposal-tools test (p9 t16)`.
  - **Concurrency note:** another agent was actively landing commits on this same branch during
    this measurement window — two more commits (`9fed9f4`, `2eee60c`, both `test(api): ... (p9
    t18)`) landed while runs 2 and 3 were executing. `git diff --stat a89fdda..HEAD` at the time
    showed the only file touched by those two commits was `apps/api/tests/test_replay.py` — zero
    overlap with `app/eval/`, `app/config.py`, `app/seed.py`, or any `seed/*` corpus file, so this
    measurement's validity is unaffected. HEAD had advanced further still by the time this record
    was committed; see the commit this record ships in for that SHA.
- **Environment discipline:** only `OPENAI_API_KEY`, `LLM_PROVIDER`, `TEST_DATABASE_URL`/
  `DATABASE_URL` (derived by database-name substitution, never hard-coded) and
  `EMBEDDING_MAX_RETRIES=12` were exported, via the exact global-constraints.md extraction pattern
  (`grep`/`cut`/`tr -d` stripping `"`, `'`, and the extraction artifacts — never `source .env`).
  **One disclosed incident:** while polling a background process's liveness with
  `ps -p <pid> -o cmd`, the full command line of the `app.eval.agent_suite` invocation — including
  its `--database-url` argument, i.e. the rebaseline DSN with its password — was printed once into
  this session's own tool transcript. The password is the local `advisordesk-test-db` container's
  own throwaway credential (not committed, not internet-reachable, not reused outside this
  container); it is disclosed here rather than omitted. Corrective note for future runs:
  `ps -o cmd`/`-o args` must never be used on a PID whose argv carries a DSN — check liveness with
  `kill -0` or `-o pid,etime` only.

## 2. Corpus fingerprint

Seed report line (verbatim), matching the runner brief's expected `created=37 published=33`
exactly:

```
seed_all: created=37 published=33 skipped=0 chunk_count=228
```

From `eval_runs` (identical across all three rebaseline rows):

| Field | Value |
|---|---|
| `corpus_content_count` | 33 |
| `corpus_chunk_count` | 228 |
| `corpus_max_updated_at` | 2026-09-13 08:48:15.925389+00 |
| `corpus_digest` | `39ca625e5c2d4222` |

## 3. The three runs

| run_id | created_at | pct_fully_supported | refusals |
|---|---|---|---|
| `73fcda8f-1e4b-4b66-a829-22d48b7047b7` | 2026-09-13 08:57:42.241626+00 | 93.5% | 18/18 |
| `d7f67633-10c9-4e0c-93cf-c77ad18f9f38` | 2026-09-13 09:05:05.443574+00 | 93.5% | 18/18 |
| `514f2636-7a27-4c0c-8f29-ca614aac5e04` | 2026-09-13 09:12:16.170741+00 | 91.9% | 18/18 |

All three share `label='rebaseline-2026-09'`, `corpus_digest='39ca625e5c2d4222'`,
`git_sha='a89fddafc3c1c0adae928da64c215d901f2f5fff'`, `chat_model='gpt-5.4-mini'`,
`judge_model='gpt-5.4'`, `embedding_model='text-embedding-3-small'`,
`similarity_threshold=0.5`, `retrieval_k=6`.

## 4. Stability

Harness stability block, pasted verbatim:

```
stability over 3 runs (label=rebaseline-2026-09):
  pct_fully_supported  mean 93.0  spread 1.6  [93.5, 93.5, 91.9]
  refusal_correct      mean 18.0  spread 0  [18, 18, 18]
```

Spread (max − min): `pct_fully_supported` = 93.5 − 91.9 = **1.6 points**; `refusal_correct` =
18 − 18 = **0** (fully deterministic over the 18 off-domain + near-miss questions in every run).
The entire 1.6-point spread traces to the `threshold` class: 4/5 pass in runs 1 and 2, 3/5 pass in
run 3 — the question "I sold company shares for less than I paid and my broker's form says the
loss was not allowed. Why?" flips PASS→FAIL in run 3 only. Every other class (`answerable`,
`off_domain`, `stale_number`, `multi_source`, `near_miss`) scores identically across all three
runs.

## 5. Per-class rollup (over all three runs, queried from the DB)

```
 question_class | verdict |  n
----------------+---------+-----
 answerable     | FAIL    |   9
 answerable     | PASS    | 126
 multi_source   | FAIL    |   6
 multi_source   | PASS    |  18
 near_miss      | PASS    |  30
 off_domain     | PASS    |  24
 stale_number   | PASS    |  12
 threshold      | FAIL    |   4
 threshold      | PASS    |  11
```

Per-run class sizes are 45/8/4/8/10/5 (answerable/off_domain/stale_number/multi_source/near_miss/
threshold); × 3 runs gives the totals above (e.g. 126+9=135=45×3). `off_domain` + `near_miss`
together are the 18 refusal-expected questions per run, 100% correct in all three runs —
consistent with §4's `refusal_correct` spread of 0.

## 6. Failure-cause distribution (over all three runs' FAIL rows, queried from the DB)

```
         cause         | count
------------------------+-------
 retrieval_miss        |     9
 threshold_refusal     |     6
 generation_unfaithful |     4
```

19 FAIL rows total across 3 runs (6 + 6 + 7, matching each run's own `n − pass`). Unlike
`baseline-2026-09` (100% of failures were `generation_unfaithful`), this corpus/question set's
failures are dominated by `retrieval_miss` and `threshold_refusal` — a direct consequence of the
wave-1 corpus expansion and the new `threshold`/`near_miss`/`multi_source` question classes, none
of which existed in the 21-question baseline set.

## 7. `compare_runs` confirmation

A fourth run (`rebaseline-2026-09-confirm`, one run) compared against the latest rebaseline run
(run 3, `514f2636-7a27-4c0c-8f29-ca614aac5e04`):

```
compare 514f2636-7a27-4c0c-8f29-ca614aac5e04 -> 9f65e048-9bde-43c1-838c-01a00861b50f: pct 91.9 -> 93.5 (+1.6); regressions 0; improvements 1; added 0; removed 0
```

**Zero regressions** — the same "threshold" question flipping back to PASS accounts for the one
reported improvement, consistent with §4, not a new finding. Per the runner brief's escalation
rule, only a regression would have blocked the README edit below; there was none, so no
escalation to the controller was required for this check.

## 8. Retiring 58.8% and superseding 72.5% ± 5.9 (`baseline-2026-09`)

The phase-7 `58.8%` figure remains retired as single-run sampling noise (unchanged from the
historical section above). The `baseline-2026-09` figure (72.5% ± 5.9 over 3 runs,
`gpt-4o-mini`/`gpt-4o`, the 21-question set) is now itself superseded, for four reasons, all
shipped since that baseline was captured — see the SUPERSEDED banner at the top of this file for
the full list (task 05b, 05c, 05d, wave 1). Any one of the four would make a direct numeric
comparison between 72.5% and today's 93.0% meaningless; together, the honest statement is that
`baseline-2026-09` measured a different judge, a different answerer, and a different (smaller,
less adversarial) question set against a smaller corpus. It is superseded, not "improved upon."

## 9. Agent suite re-baseline

One agent-suite run (`--label agent-rebaseline-2026-09`) against the same database, run **last**
(after every answer-run measurement above), per the same content-mutation ordering rule the
original baseline recorded. One `users` row was inserted first (all other columns are nullable or
carry a server default):

```sql
INSERT INTO users (id, email, name) VALUES (gen_random_uuid(), 'eval-runner@example.com', 'Eval Runner');
```

Per-task lines:

```
draft-and-tag                PASS  steps=1 precision=1.00 recall=1.00 looped=False
count-published-by-tag       PASS  steps=1 precision=1.00 recall=1.00 looped=False
publish-drafts-with-tag      PASS  steps=2 precision=1.00 recall=1.00 looped=False
archive-by-title             PASS  steps=2 precision=1.00 recall=1.00 looped=False
edit-a-body                  PASS  steps=2 precision=1.00 recall=1.00 looped=False
add-and-remove-tags          PASS  steps=2 precision=1.00 recall=1.00 looped=False
report-weak-queries          PASS  steps=1 precision=1.00 recall=1.00 looped=False
propose-a-fix-from-a-gap     FAIL  steps=2 precision=0.50 recall=0.50 looped=False
draft-publish-verify         FAIL  steps=1 precision=1.00 recall=0.50 looped=False
ambiguous-cleanup-should-ask PASS  steps=0 precision=1.00 recall=1.00 looped=False
agent suite: 80.0% tasks passed (8/10)
recorded eval_runs id=fce67383-2b9e-48a9-a859-3a2af3cb4ec5
```

Run id: `fce67383-2b9e-48a9-a859-3a2af3cb4ec5` (`label='agent-rebaseline-2026-09'`,
`kind='agent'`, `git_sha='a89fddafc3c1c0adae928da64c215d901f2f5fff'`) — **8/10 tasks passed
(80.0%), down from `agent-baseline-2026-09`'s 10/10 (100.0%). This is a regression, reported as a
finding, not smoothed over.** The DB's own `metrics` column for each FAIL row gives the exact
trajectory:

- **`propose-a-fix-from-a-gap`** (steps=2, precision=0.50, recall=0.50): the agent called
  `report_weak_queries` then `report_content_gaps` — both read-only "check the gap" tools — then
  stopped without ever calling `create_draft`. `end_state_failures`:
  `["content_title_contains: no content titled like 'crypto' exists"]`. The task asks the agent to
  check the gap report AND THEN draft something; it completed only the first half.
- **`draft-publish-verify`** (steps=1, precision=1.00, recall=0.50): the agent called
  `create_draft` with a complete, well-formed "Mega Backdoor Roth Basics" article (the one tool
  call it made was entirely correct — precision 1.00) but never called the publish tool.
  `end_state_failures`: `["expected status 'published' for 'Mega Backdoor Roth Basics', found
  'draft'"]`.

Both failures are **recall failures** — the agent stopped one tool call short of a multi-step
task — not precision failures; every tool call it actually made was the correct one. Both task
IDs, and the `create_draft`/publish tools they exercise, already existed unchanged at the
`agent-baseline-2026-09` measurement, so this is not "a new, harder task appeared." The same tasks
that passed 10/10 under the `gpt-4o-mini` agent LLM now pass 8/10 under `gpt-5.4-mini`. The most
parsimonious explanation is the answerer/agent model swap itself (`gpt-4o-mini` → `gpt-5.4-mini`,
the same swap noted in §8/task 05d), not a corpus or tool change — **this is a finding for the
controller, not something this measurement-only task is positioned to fix.**

### 9a. Task-07b: `any_of` credit fix + three-run stability (supersedes §9's single 80.0% number)

`.superpowers/sdd/phase-9-eval-data-loop/reports/agent-suite-regression.md` diagnosed the §9 8/10
as **noise, not a stable regression**: three identical-code probe runs scored 8/10, 10/10, 9/10, and
one of the two recurring failures — `propose-a-fix-from-a-gap` — was partly **our own scoring bug**:
its reference trajectory demanded a literal `create_draft`, but `propose_content_fix` (registered by
task 16, after task 07 froze that reference) now creates the draft itself and is what the system
prompt teaches the agent to call — so a run that correctly used `propose_content_fix` was scored
`tool_recall = 0.5` regardless of model. Task-07b (commit `d5ac13c34273fa8a219d0a72dcd40d610dcb725c`,
`fix(api): agent suite credits propose_content_fix; prompt completes a draft+publish request (p9
t07b)`) fixed this: `ReferenceStep` gained an optional `any_of: list[str]` so a step matches either
its primary `tool` or any listed alternative (`create_draft`'s step for this task now lists
`any_of: [propose_content_fix]`; both tools take the same `title` argument, so the existing
`args_contains: {title: "crypto"}` needed no relaxation). It also added one sentence to
`SYSTEM_PROMPT` making explicit that a single message asking for both a draft and a publish is
itself the explicit request to do both, targeting the `draft-publish-verify` stall.

Per our own rule (task-07b Ruling 3 — a metric without a spread is not reported), the suite was run
**three times, each against its own freshly built scratch DB** (`advisordesk_p9agentstab1`,
`…stab2`, `…stab3` — drop/create, `CREATE EXTENSION vector`, `alembic upgrade head`, `python -m
app.seed`, one `users` row inserted, then `python -m app.eval.agent_suite --label
agent-stability-N`), never reusing a DB the suite had already mutated. All three runs recorded
`chat_model='gpt-5.4-mini'` and the identical `git_sha` above — so all variance below is pure
model/sampling variance, not a code or corpus difference:

```
run 1 (agent-stability-1, eval_runs id c8dc7644-2d44-4ca1-8a20-8275c9bf454a): 90.0% (9/10)
run 2 (agent-stability-2, eval_runs id 351f225b-e558-4790-ac9b-1f87babf3383): 80.0% (8/10)
run 3 (agent-stability-3, eval_runs id d4e5472b-8493-4c4c-8674-35872f67c3ba): 80.0% (8/10)

pct_fully_supported  mean 83.3  spread 10.0  [90.0, 80.0, 80.0]
```

**mean 83.3% ± 10.0 (min 80.0%, max 90.0%)** over the three runs (raw scores 9/10, 8/10, 8/10).
§9's single `agent-rebaseline-2026-09` measurement (80.0%) sits inside this same spread — it was one
draw from this distribution, not a separately-real number.

**Per-task pass pattern across the three runs:**

```
draft-and-tag                PASS  PASS  PASS   (1.00/1.00 every run)
count-published-by-tag       PASS  PASS  PASS   (1.00/1.00 every run)
publish-drafts-with-tag      PASS  PASS  PASS   (1.00/1.00 every run)
archive-by-title             PASS  PASS  PASS   (1.00/1.00 every run)
edit-a-body                  PASS  PASS  PASS   (recall 0.50 in run 1 only; end-state held anyway)
add-and-remove-tags          PASS  PASS  PASS   (1.00/1.00 every run)
report-weak-queries          PASS  PASS  PASS   (1.00/1.00 every run)
propose-a-fix-from-a-gap     FAIL  FAIL  FAIL   (steps=2, recall=0.50 every run)
draft-publish-verify         PASS  FAIL  FAIL   (run1 1.00/1.00; runs 2-3 steps=1, recall=0.50)
ambiguous-cleanup-should-ask PASS  PASS  PASS   (1.00/1.00 every run)
```

**The `propose-a-fix-from-a-gap` recall=0.50 figures recorded before this commit (§9 and the
regression report's probes) were partly an artefact of the stale reference trajectory** — a run
that correctly called `propose_content_fix` was wrongly scored 0.5. That scoring bug is fixed and
directly proven by unit test (`test_propose_content_fix_trajectory_scores_full_recall_against_
create_draft_any_of`), but it is reported honestly, not oversold: in **all three** of these fresh
runs the agent called only `report_weak_queries` then `report_content_gaps` (confirmed from each
run's persisted `metrics.trajectory`) and stopped without calling `create_draft` or
`propose_content_fix` at all — the same "asks/offers instead of acting" behavior the regression
report already catalogued and deliberately left unfixed (task-07b Ruling 2's "rejected,
deliberately" note: steering the agent to act on an unverified premise is a real behavior
trade-off, not a bug this task closes). So this batch's 0.50s are **genuine** partial trajectories,
not the stale-reference miscount — the fix's benefit here is proven by the unit tests, not by a live
draw in this particular batch of three.

**`draft-publish-verify` still stalled in 2 of these 3 runs, after Ruling 2's added sentence.** The
model's own stated reasoning shows it engaging with the new sentence without complying with it —
run 2: *"I drafted the article, but I did not publish it because your request included both
drafting and publishing, and I need to complete the publish step explicitly after the draft is
created."* Run 3: *"I created the draft article, but I did not publish it because your request
included both drafting and publishing, and I need to complete the publish step separately only when
explicitly instructed to do so in the same turn."* Both responses now name the "both drafting and
publishing" premise the new sentence introduced — the model reads it — and then reach the opposite
conclusion, requiring a second turn anyway. One added sentence changed the model's stated reasoning
without reliably changing its tool-calling behavior.

**`temperature=0` does not make `gpt-5.4-mini`'s tool calling deterministic — this is a finding, not
a footnote.** Six measurements now exist across two adjacent code states, same corpus/temperature
throughout: pre-this-fix, the regression report's three runs (its `agent-rebaseline-2026-09` probe
*is* §9's own run, not a fourth one) scored 80/100/90 (percent); post-this-fix, this task's three
runs scored 90/80/80 (percent). No prompt wording tried so far — neither §9's original prompt nor
this task's one added sentence — has produced three identical runs. Any future single-run number
for this suite should be read as one draw from a real spread, not a stable measurement, until proven
otherwise by repeated runs.

The three scratch databases (`advisordesk_p9agentstab1/2/3`) are left in place, local-only, not
committed — same convention as the regression report's own probe databases. No DSN or API key
appears above; database names and the one non-secret confirmation line each script printed are the
only db-identifying values shown.

## 10. Judge scorecards

Two scorecards, run back to back (only one judge-calling harness at a time, per
global-constraints.md), both scored against the 4 rows currently committed to
`seed/judge_labels.yaml` — **not** the full ~40-row set the owner and Abhishek are still
labelling, so the `agreement`/`kappa` figures below are a small-sample (n=4) result, not yet the
target-n confirmation DESIGN calls for. (The runner brief anticipated these cards would report
self-consistency only, on the assumption zero human labels existed yet; in fact 4 already do, so
both `agreement` and `kappa` ARE reported below. This is a deviation from the brief's stated
expectation, not from the module's documented behavior — `judge_scorecard.py` reports
self-consistency-only precisely when `labelled == 0`, and `labelled == 4` here.)

**Default judge** (`gpt-5.4`, `temperature=0.0`, the `Settings()` defaults):

```
judge scorecard (model=gpt-5.4, temperature=0.0, labels=4 labelled / 4 total)
  agreement              100.0%
  cohen's kappa          1.00   (target >= 0.80)
  self-consistency x3    100.0%
  position consistency   n/a (no eligible rows)
  verbosity consistency  100.0% (n=4)
```

**Cross-check judge** (`gpt-5.6-terra`, `--judge-temperature none`): this model family cannot be
pinned to `temperature=0` — the runner brief called this out explicitly, and confirming it was
part of this step's purpose. `--judge-temperature none` omits the `temperature` request parameter
entirely rather than sending `0`, so the provider's own default sampling temperature applies:

```
judge scorecard (model=gpt-5.6-terra, temperature=default (omitted), labels=4 labelled / 4 total)
  agreement              100.0%
  cohen's kappa          1.00   (target >= 0.80)
  self-consistency x3    100.0%
  position consistency   n/a (no eligible rows)
  verbosity consistency  100.0% (n=4)
```

Both judge generations agree perfectly with each other and with all 4 human labels at this sample
size — the "judge generation and determinism are a measurement choice" point for the talk: a
newer, non-temperature-pinnable judge model (`gpt-5.6-terra`) produces an identical scorecard to
the pinned `gpt-5.4` judge on the same 4 rows, though n=4 is too small to treat this as a strong
claim either way pending the owner's full label set. `position consistency` is `n/a` in both cards
because none of the 4 sampled rows has >= 2 retrieved chunks (the spot-check's eligibility
condition).

## 11. Raw output

- Full raw stdout of the three-run `--label rebaseline-2026-09 --runs 3` invocation (all three
  per-question tables, per-class rollups, judge-metrics-by-class tables, failure causes, and the
  stability block) — captured via output redirection (byte-identical in content to `tee`, since
  the process ran fully detached/backgrounded) at:
  `.superpowers/sdd/phase-9-eval-data-loop/rebaseline-capture.txt` (gitignored).
- The `--label rebaseline-2026-09-confirm --runs 1 --compare-to latest` invocation's raw stdout is
  additionally captured at:
  `.superpowers/sdd/phase-9-eval-data-loop/rebaseline-confirm-capture.txt` (gitignored).

## No secrets (rebaseline-2026-09 section)

No API key or DSN password appears in this section in plaintext; every DSN shown has its password
redacted (`***`). The one process-listing incident (§1) is disclosed in full rather than
concealed; the exposed value was a local, non-production, throwaway test-container password, and
it appears only in this session's own tool transcript, never in this file or any other committed
file.
