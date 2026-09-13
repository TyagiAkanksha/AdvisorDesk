---
id: p9-t14
phase: phase-9-eval-data-loop
depends_on: [p9-t09, p9-t13]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 14 — The golden set closes at 80: persona-first questions, the class balance, the N5 loader guard, and the labelled judge file

## Goal

Wave 1's four batches left the golden set at 65 rows made of questions each article answers *by
construction*. This task adds the other kind — **15 questions a client would actually type**, written
from the personas rather than from the corpus — and balances the committed file to exactly the DESIGN
§B2 targets: **80 rows = 45 answerable · 8 multi_source · 10 near_miss · 8 off_domain · 5 threshold ·
4 stale_number**. It also closes the N5 ruling in code (a `reference_answer` on an `answerable: false`
row becomes a `ValueError`, not a convention) and pins the final counts in `test_seed.py`.

Finally, it carries one **owner-gated** step: committing the 40 human-labelled judge rows from the
labelling session as `seed/judge_labels.yaml` and tightening the scorecard's pin to ≥ 40 rows. That
step lands only if the owner and Abhishek have finished labelling; everything else in this task ships
regardless.

`seed/agent_tasks.yaml` already exists (task 07) — this task does **not** touch it.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §B2 (the 80/10/40 decision, the six classes and their
  exact counts, "authored with each article … plus ~15 persona-first questions so the set is not
  'questions the article answers by construction'", the judge-labels row) and §C2 (the three personas
  and the five planted gaps).
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` — "Global Constraints" and the plan-time ruling on
  judge labels ("the labelled file is committed as `seed/judge_labels.yaml`").
- `seed/eval_questions.yaml` — the 65 committed rows at the post-task-13 state (21 phase-4 +
  44 wave-1). This task appends 15 rows and changes nothing above them.
- `apps/api/app/eval/questions.py` — `load_questions`'s validation block, in particular the
  `reference_answer` type check near the end of the per-item loop and the `Raises:` list in the
  docstring. The guard goes there.
- `apps/api/tests/test_eval_questions_v2.py` — the loader's unit tests and the `_write` helper.
- `apps/api/tests/test_seed.py` at its post-task-13 state — `_WAVE1_ARTICLES` (16 entries),
  `_load_eval_questions`, `_question_class`, `_EXPECTED_CLASS_COUNTS`, `_EXPECTED_QUESTION_TOTAL`,
  and the DB pin `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus`.
- `apps/api/app/eval/judge_scorecard.py` — `load_judge_labels`, the recognised row keys, and
  `_run_from_cli` (`--labels`, `--repeats`, `--sample`, `--export-pending`, `--out`).
- `apps/api/tests/test_judge_scorecard.py` — `test_committed_judge_labels_file_loads_and_is_usable`
  (the `>= 4` pin this task tightens) and `_REPO_ROOT`.
- `seed/judge_labels.yaml` — the four bootstrap rows, their key set and comment header.
- The 16 wave-1 article files under `seed/sample_content/` — **read the H2 headings only** (the rows
  below reference them); do not re-read their bodies.

## Files

**Modify**
- `seed/eval_questions.yaml` (append the 15 rows below, verbatim)
- `apps/api/app/eval/questions.py` (the N5 guard + its `Raises:` line)
- `apps/api/tests/test_eval_questions_v2.py` (two guard tests)
- `apps/api/tests/test_seed.py` (final class counts + two new golden-set pins)

**Modify, owner-gated (only if the labelling session is done)**
- `seed/judge_labels.yaml` (the 40 labelled rows)
- `apps/api/tests/test_judge_scorecard.py` (the `>= 4` pin becomes `>= 40` + a labeller pin)

**Do not touch:** any `seed/sample_content/*.md` file, `seed/agent_tasks.yaml`, any other file under
`apps/api/app/`, prod.

## Interfaces

### `app/eval/questions.py` — the N5 guard

Inserted immediately after the existing `reference_answer` type check, before the `questions.append(`
call:

```python
        if reference_answer is not None and not answerable:
            raise ValueError(
                f"{questions_path}[{index}]: 'reference_answer' is not allowed on an "
                f"answerable=False item (phase-9 N5 ruling: a reference answer on a row the corpus "
                f"must NOT answer gives the answer-relevance and context-recall judges a target "
                f"that cannot be supported, scoring a correct refusal as a miss): {item!r}"
            )
```

and one line added to `load_questions`'s `Raises:` list, after the `expected_slugs` clause:

```
            an `answerable: false` item carries a `reference_answer` (phase-9 N5 ruling);
```

No signature changes, no new exports, no behaviour change for any valid row.

### The class arithmetic (this is the contract `test_seed.py` pins)

| class | phase-4 (21 rows) | wave 1, batches A–D (44 rows) | this task (15 rows) | total | DESIGN §B2 target |
|---|---|---|---|---|---|
| `answerable` | 17 (by the loader's default) | 24 (6 per batch) | 4 | **45** | 45 |
| `multi_source` | 0 | 8 (2 per batch) | 0 | **8** | 8 |
| `near_miss` | 0 | 4 (1 per batch) | 6 | **10** | 10 |
| `off_domain` | 4 (by the loader's default) | 0 | 4 | **8** | 8 |
| `threshold` | 0 | 4 (1 per batch) | 1 | **5** | 5 |
| `stale_number` | 0 | 4 (1 per batch) | 0 | **4** | 4 |
| **total** | **21** | **44** | **15** | **80** | 80 |

Planted-gap coverage after this task — each of the five gaps is hit exactly twice by the 10
`near_miss` rows: non-US employees (batch A + row 8 below), stock options in a divorce (batch B +
row 10), crypto compensation (batch C + row 9), 401(k) loans against employer stock (batch D +
row 11), QSBS (rows 6 and 7 — the only gap with no wave-1 neighbour article, so both of its rows are
authored here).

## The 15 persona-first rows — append verbatim to `seed/eval_questions.yaml`

These are deliberately **not** shaped like the articles' own headings: they are what Sam, Priya and
Marcus type. Append after batch D's rows, preceded by this comment line:

```yaml
# --- phase-9 golden set (task 14): persona-first questions + the class balance to 80 ---
```

Then exactly these 15 rows, in this order, unedited:

```yaml
- question: "How much cash should I set aside for taxes on my stock comp?"
  expected_slugs: ["what-happens-to-your-rsus-at-vest"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks: ["what-happens-to-your-rsus-at-vest#how-do-i-cover-the-shortfall-before-april"]
  reference_answer: >-
    Set aside the difference between the flat supplemental rate your employer withheld and your own
    marginal rate on the vested value. You can pre-pay it with an estimated payment or by raising
    your payroll withholding instead of waiting for the return.

- question: "Everyone at work says to exercise early. Is that right for me?"
  expected_slugs: ["the-83-b-election-on-restricted-stock"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks: ["the-83-b-election-on-restricted-stock#when-is-an-83-b-election-a-good-idea"]
  reference_answer: >-
    Early exercise with an 83(b) election works best when the spread at transfer is small, you plan
    to hold the shares, and you can afford to lose the money. It backfires if the company fails or
    you leave before vesting, because the tax you paid is not refundable.

- question: "Half my money is in my employer's shares and I am nervous. What do you advise?"
  expected_slugs: ["concentrated-employer-stock-and-our-10-rule"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks:
    - "concentrated-employer-stock-and-our-10-rule#how-much-of-my-net-worth-should-sit-in-company-stock"
    - "concentrated-employer-stock-and-our-10-rule#what-is-the-risk-i-am-actually-taking"
  reference_answer: >-
    The firm's policy ceiling is 10% of investable net worth in any single company, and at half your
    portfolio the position is the dominant risk you carry alongside the salary it pays. The answer
    is a written unwind schedule inside your trading windows rather than a judgement about the
    share price.

- question: "Is working with you worth it if I mostly just have a salary and some RSUs?"
  expected_slugs: ["how-we-work-and-what-we-charge"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks:
    - "how-we-work-and-what-we-charge#who-do-you-work-with-and-who-are-you-not-a-fit-for"
  reference_answer: >-
    Queen City works with tech employees whose pay includes equity, which is exactly a salary plus
    RSUs, and it offers a flat-fee planning engagement for people who do not want an ongoing
    relationship yet. It is not a fit if you want stock picks or active trading.

- question: "Nobody has touched my account mix in over a year and stocks ran up. Is that a problem?"
  expected_slugs: ["our-rebalancing-policy-and-the-20-drawdown-rule"]
  answerable: true
  class: threshold
  persona: "Marcus"
  expected_chunks:
    - "our-rebalancing-policy-and-the-20-drawdown-rule#when-do-you-rebalance-my-portfolio"
  reference_answer: >-
    After a run-up your allocation has drifted toward stocks, so the portfolio is riskier than the
    plan it started from. The firm reviews allocations quarterly and rebalances when a holding
    drifts outside its policy band, which is what a year of untouched growth tends to cause.

- question: "My startup shares might qualify for the small business stock exclusion — do I owe nothing if I hold five years?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Priya"

- question: "Can I exclude the gain on my founder shares when we get acquired?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Priya"

- question: "I am relocating to our Dublin office next year — will my RSU vests still be taxed the same way?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Sam"

- question: "A crypto company is recruiting me and part of the pay is in tokens — how does that work?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Marcus"

- question: "We are separating and my options are on the table in the settlement — how are they valued?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Marcus"

- question: "If I take a loan from my 401(k), which investments get sold to fund it?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Sam"

- question: "What is the best credit card for travel rewards?"
  expected_slugs: []
  answerable: false
  class: off_domain
  persona: "Sam"

- question: "How do I negotiate a higher signing bonus?"
  expected_slugs: []
  answerable: false
  class: off_domain
  persona: "Priya"

- question: "Can you help me set up payroll and benefits for my side business?"
  expected_slugs: []
  answerable: false
  class: off_domain
  persona: "Marcus"

- question: "Which mortgage lender should I use for my first home?"
  expected_slugs: []
  answerable: false
  class: off_domain
  persona: "Sam"
```

Notes the implementer must respect:

- **Nothing is added to any `answerable: false` row** — no `expected_slugs` entries, no
  `expected_chunks`, and (N5) no `reference_answer`. The guard this task adds would reject the file.
- The four `answerable` rows and the `threshold` row are phrased away from their section headings on
  purpose. Do not "improve" them toward the article's wording: a question that matches the heading is
  the thing DESIGN §B2 says this set must not be made of.
- No row duplicates an existing question string (`load_questions` raises on duplicates); the nearest
  pairs are row 11 here and batch D's 401(k) near-miss, which are deliberately different questions
  about the same gap.

## Steps (TDD)

- [ ] **RED — test-author, 1/3.** In `apps/api/tests/test_eval_questions_v2.py`, append:

```python
def test_reference_answer_on_an_unanswerable_row_raises(tmp_path: Path) -> None:
    """Phase-9 N5 ruling, now enforced by the loader: a reference answer on a row the corpus must
    not answer hands the answer-relevance and context-recall judges an unsupportable target, which
    scores a correct refusal as a miss."""
    path = _write(
        tmp_path,
        [
            {
                "question": "How is my token compensation taxed?",
                "expected_slugs": [],
                "answerable": False,
                "class": "near_miss",
                "reference_answer": "It is ordinary income when you gain control of it.",
            }
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        load_questions(path)

    message = str(excinfo.value)
    assert "reference_answer" in message
    assert "answerable" in message


def test_unanswerable_rows_without_a_reference_answer_still_load(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "question": "How is my token compensation taxed?",
                "expected_slugs": [],
                "answerable": False,
                "class": "near_miss",
                "persona": "Marcus",
            }
        ],
    )

    question = load_questions(path)[0]

    assert question.question_class == "near_miss"
    assert question.reference_answer is None
    assert question.expected_chunks == []
```

- [ ] **RED — test-author, 2/3.** In `apps/api/tests/test_seed.py`, set the final counts:

```python
_EXPECTED_CLASS_COUNTS = {
    "answerable": 45,
    "multi_source": 8,
    "near_miss": 10,
    "off_domain": 8,
    "threshold": 5,
    "stale_number": 4,
}
_EXPECTED_QUESTION_TOTAL = 80
```

  and append these two pins (the golden set is frozen after this task — these are the pins the
  whole-branch review reads):

```python
# DESIGN §C2's three personas, verbatim. A typo'd persona silently empties a per-persona rollup.
_PERSONAS = {"Sam", "Priya", "Marcus"}


def test_eval_questions_personas_are_the_three_design_personas() -> None:
    used = {item["persona"] for item in _load_eval_questions() if "persona" in item}
    unknown = used - _PERSONAS
    assert not unknown, f"unknown personas {unknown}; DESIGN §C2 names {sorted(_PERSONAS)}"
    assert used == _PERSONAS, f"every persona must appear at least once; missing {_PERSONAS - used}"


def test_eval_questions_authored_class_rows_carry_a_reference_answer() -> None:
    """`multi_source`, `threshold` and `stale_number` rows exist only in the phase-9 waves, and the
    answer-relevance and context-recall judges score against `reference_answer` — a row in one of
    those classes without one is silently unscored. (The 17 phase-4 rows default to class
    `answerable` and carry no reference answer; backfilling those is wave 2's job, DESIGN §C2.)"""
    missing = [
        item["question"]
        for item in _load_eval_questions()
        if item.get("class") in {"multi_source", "threshold", "stale_number"}
        and not item.get("reference_answer")
    ]
    assert not missing, f"authored-class rows missing a reference_answer: {missing}"
```

- [ ] **RED — test-author, 3/3. Run RED and record the evidence.** From the repo root, exporting only
      `TEST_DATABASE_URL` (never `source .env`, never print the value):

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
[ -n "$TEST_DATABASE_URL" ] && echo "TEST_DATABASE_URL: set"
cd apps/api && uv run pytest tests/test_eval_questions_v2.py tests/test_seed.py -q
```

  Expected RED: `test_reference_answer_on_an_unanswerable_row_raises` fails (`DID NOT RAISE
  ValueError` — the guard does not exist yet) and the class-count pin fails (80 expected vs 65
  present). Note which new pins pass at RED and why
  (`test_unanswerable_rows_without_a_reference_answer_still_load` and the persona/authored-class
  pins pass over the post-task-13 file).

- [ ] **RED commit:** `git commit -m "test(api): N5 loader guard + final golden-set class pins (p9 t14)"`

- [ ] **GREEN — implementer, 1/2.** Add the guard to `app/eval/questions.py` exactly as in Interfaces
      (plus the `Raises:` line). Do not touch any other validation.

- [ ] **GREEN — implementer, 2/2.** Append the comment line and the 15 rows verbatim to
      `seed/eval_questions.yaml`.

- [ ] **Run GREEN:**

```bash
cd apps/api && uv run pytest tests/test_eval_questions_v2.py tests/test_seed.py -q
uv run pytest -q
```

  The whole suite must be green, including the DB pin
  `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus` (every
  `expected_chunks` ref in the 80-row file still resolves against the seeded corpus) and
  `tests/test_groundedness.py` (the loader change must not move any existing behaviour).

- [ ] **GREEN — the 80-row run on a scratch DB** (evidence for the report):

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
export OPENAI_API_KEY="$(grep -m1 '^OPENAI_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n')"
export SCRATCH_DB=advisordesk_p9golden80
export DATABASE_URL="${TEST_DATABASE_URL%/*}/$SCRATCH_DB"   # db-name substitution only
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY: set"
docker exec advisordesk-test-db psql -U postgres -c "DROP DATABASE IF EXISTS $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -c "CREATE DATABASE $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -d "$SCRATCH_DB" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed
uv run python -m app.eval.groundedness --label golden-80 --no-persist \
  | tee ../../.superpowers/sdd/phase-9-eval-data-loop/task-14-golden80-capture.txt
```

  Paste into the implementer report: the seed line (37 created / 33 published), the **per-class
  table** for all six classes, the refusal-correctness line, the failure-cause distribution, and the
  `unresolved expected_chunks refs` count (must be 0). Flag any `off_domain` or `near_miss` row that
  was answered rather than refused — those are the rows task 15's weak-query demo and task 18's
  replay will lean on, and a wrongly-answered one is a content finding, not a metric to hide.

- [ ] **Gates:** `pnpm gates:api` (ruff, ruff format, mypy, lint-imports, pytest — with only
      `TEST_DATABASE_URL` exported).

- [ ] **GREEN commit:**
      `git commit -m "feat(api): golden set at 80 rows — persona questions + N5 loader guard (p9 t14)"`

- [ ] **OWNER-GATED — the 40 labelled judge rows.** Do this step **only** if the owner confirms the
      labelling session (owner + Abhishek, task 09's `seed/judge_labels.pending.yaml` export) is
      finished and the disagreements are resolved. If it is not: stop here, leave
      `seed/judge_labels.yaml` and `tests/test_judge_scorecard.py` untouched, record the block in the
      implementer report and in `.superpowers/sdd/progress.md`, and the task is complete without it.

  1. Copy the labelled worksheet into place as `seed/judge_labels.yaml`, keeping the file's existing
     comment header. Keep each of the four bootstrap rows only if the 40 labelled rows do not already
     contain that (question, answer) pair, so the committed file holds 40–44 rows and no duplicates.
  2. Every row must carry a non-null `human_verdict` (`supported` / `unsupported`) and a non-blank
     `labeller`; both verdicts must appear. A row the two labellers could not agree on is dropped, not
     guessed — note how many were dropped.
  3. Tighten the pin in `apps/api/tests/test_judge_scorecard.py`, replacing the body of
     `test_committed_judge_labels_file_loads_and_is_usable` with exactly:

```python
def test_committed_judge_labels_file_loads_and_is_usable() -> None:
    """DESIGN §B2: ~40 human-labelled rows, stratified across classes, labelled by the owner and
    Abhishek with disagreements resolved. Before that session the file held four bootstrap rows
    (pin `>= 4`); task 14 commits the real set."""
    labels = load_judge_labels(_REPO_ROOT / "seed" / "judge_labels.yaml")

    assert len(labels) >= 40, f"DESIGN §B2 calls for ~40 labelled rows; found {len(labels)}"
    verdicts = {label.human_verdict for label in labels}
    assert True in verdicts and False in verdicts, (
        "both verdicts must appear or kappa is undefined"
    )
    assert all(label.question.strip() and label.answer.strip() for label in labels)
    assert all(label.labeller.strip() for label in labels), "every row records who labelled it"
```

  4. Run the scorecard and record κ, agreement and self-consistency:

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export OPENAI_API_KEY="$(grep -m1 '^OPENAI_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n')"
cd apps/api
uv run python -m app.eval.judge_scorecard \
  | tee ../../.superpowers/sdd/phase-9-eval-data-loop/task-14-judge-scorecard.txt
```

  5. `cd apps/api && uv run pytest tests/test_judge_scorecard.py -q`, then `pnpm gates:api`, then
     commit: `git commit -m "feat(eval): commit the 40 labelled judge rows + tighten the scorecard pin (p9 t14)"`.
     If κ lands below the §B2 target of 0.8, **do not re-label to chase it** — record the number and
     the disagreement pattern for the owner; a calibration finding is a result, not a bug.

## Verify

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
cd apps/api
uv run pytest tests/test_eval_questions_v2.py tests/test_seed.py tests/test_groundedness.py \
  tests/test_judge_scorecard.py -q
uv run python -c "
from pathlib import Path
from collections import Counter
from app.eval.questions import load_questions
rows = load_questions(Path('../../seed/eval_questions.yaml'))
print(len(rows), dict(Counter(r.question_class for r in rows)))
"
pnpm gates:api
git diff --exit-code -- ../../seed/sample_content   # must PASS: this task authors no content
```

The inline check must print `80 {'answerable': 45, 'off_domain': 8, 'multi_source': 8,
'near_miss': 10, 'threshold': 5, 'stale_number': 4}` (key order may differ).

## Acceptance

- `seed/eval_questions.yaml` holds exactly 80 rows; the class counts are `{answerable: 45,
  multi_source: 8, near_miss: 10, off_domain: 8, threshold: 5, stale_number: 4}`; the 65 pre-existing
  rows are byte-identical to their post-task-13 state.
- The 15 appended rows are verbatim as authored, in order, and every one names a persona from
  {Sam, Priya, Marcus}.
- All 10 `near_miss` rows are `answerable: false` with empty `expected_slugs`, no `expected_chunks`
  and no `reference_answer`; the five planted gaps are each covered by exactly two of them.
- `load_questions` raises `ValueError` naming `reference_answer` and `answerable` for a
  `reference_answer` on an `answerable: false` row, and still loads every valid row unchanged.
- `test_seed.py` pins the final counts plus the persona set and the "authored classes carry a
  reference answer" rule; the DB resolver pin still passes over the 80-row file.
- A `--label golden-80 --no-persist` run over the complete wave-1 corpus is captured with its
  per-class table, refusal correctness, failure-cause distribution, and 0 unresolved refs.
- No seed article is added or modified by this task; `seed/agent_tasks.yaml` is untouched.
- **Owner-gated:** either `seed/judge_labels.yaml` holds ≥ 40 fully labelled rows with both verdicts
  present and the scorecard pin reads `>= 40` (with κ recorded), **or** the step is explicitly
  recorded as blocked on the labelling session and both files are untouched.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-14-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-14-implementer.md`
- Reviewer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-14-review.md`
