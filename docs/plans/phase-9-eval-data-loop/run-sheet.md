# 2026-09-24 run sheet — the evaluated, self-improving loop

One page. Five sections: before you go on, the four beats plus the rejected-fix variant, the line,
what to say when a metric moves, and what's left for after.

## 1. Before you go on

- URLs: client `https://advisordesk.tyagiakanksha.com`, API
  `https://api.advisordesk.tyagiakanksha.com`, admin `https://admin.advisordesk.tyagiakanksha.com/signin`.
- The 40-question replay already ran **yesterday** (`docs/plans/phase-9-eval-data-loop/rehearsal.md`
  §4 step 3) — do not re-run it today.
- `prod-probe` (GitHub Actions, every 6h) green as of this morning.
- Remaining per-IP budget: 50/day − 40 (yesterday's replay) = **10 questions left today**. No live
  fishing for a good example on stage — every live question spends part of that budget.
- The claude.ai connector is already connected to the AdvisorDesk MCP server.
- Browser tabs pre-opened: client chat, admin sign-in, the connector's chat.
- One terminal, `export API=https://api.advisordesk.tyagiakanksha.com` already run.
- Decide **before** walking on stage whether beat 4 runs against prod at all (see beat 4's
  fallback) — a failed live publish costs more than a rehearsed scratch-DB run.

## 2. The four beats

### Beat 1 — a grounded answer the room can verify (2 min)

Ask (client chat): *"My first RSU tranche vested and the tax withheld looked low. Why?"*
The room sees tokens stream, then citations, then the answer. Read out the cited article title and
one specific number from it (the flat 22% supplemental withholding rate). **Fallback:** the
recorded `replay-<date>.json` outcome for this exact question (it is one of the 40; find it by
`question` field) — read the citation count and paste the answer text.

### Beat 2 — an off-domain refusal (1 min)

Ask: *"What is the weather in Charlotte tomorrow?"* Point out: no citations, an explicit "no
published guidance" refusal, not a hallucinated forecast. **Fallback:** a screenshot (pre-captured;
this beat has no state that can change between rehearsal and stage).

### Beat 3 — a planted gap, live (3 min)

Ask one of the ten planted-gap questions (e.g. *"Does your equity compensation guidance apply to
employees outside the United States?"*). Then open `report_weak_queries` (connector or bearer
fallback) and show this exact question grouped, its `kind` (`near_miss` or `refused`), and its
`worst_top_similarity`. **Say what these mean before the room asks:** `near_miss` = something
cleared the retrieval threshold but the system still declined (a distractor chunk close enough to
retrieve, not close enough to answer from); `refused` = nothing cleared the threshold at all — both
are "correctly said no," not a bug. **Record the actual kind/similarity from prod** in
`rehearsal.md` §4 step 4 before the talk — which of the five gaps lands in which class is a fact
about the live corpus, not something to predict from the scratch-DB numbers. **Fallback:** the
recorded §4 step 4 output in `rehearsal.md`.

### Beat 4 — propose → measure → accept, then the rejected variant (5 min + 3 min)

**Decide in advance (§1): this beat runs on the scratch DB from `rehearsal.md`, not prod** — no
live embedding calls, no prod writes, and no risk of an agent stalling in front of the room. If the
scratch-DB run is pre-loaded in a second terminal, this beat is the flagship version
(`rehearsal.md` §3): show the planted-gap question refused live (or via the recording), show
`report_weak_queries` grouping it `near_miss`, show `propose_content_fix`'s evidence, publish the
real article, then **ship its eval rows** — show the fenced diff (§3 step 3: two golden `near_miss`
rows re-labelled `answerable: true`, three new rows added) and say out loud that this is a
demo-time edit, never committed to `seed/eval_questions.yaml`. Show the before/after `compare` line
(pct 91.9% → 94.0%, **0 regressions, 3 `added`**), show `accept_proposal` succeeding. If step 3 gets
cut for time, say the fallback line instead (§5 below) and fall back to `rehearsal.md` §3-alt's
retune, which needs no golden-set edit (pct 91.9% → 95.2%, 0 regressions). Then the rejected
variant: show `rehearsal.md` §5's bad-fix `compare` line (pct 94.0% → 95.5%, **2 regressions,
named**), show `accept_proposal` raising the verbatim `ConflictError`, show `reject_proposal`
archiving the draft.

**If this runs through the agent (connector) instead of raw script calls, drive it ONE instruction
per message, never a compound one.** Two of the ten agent-suite tasks stall specifically on
compound instructions (`docs/plans/phase-9-eval-data-loop/verification-record.md` §9a,
`.superpowers/sdd/phase-9-eval-data-loop/reports/agent-suite-regression.md`): `draft-publish-verify`
stalled after drafting in 2 of 3 fresh runs even after the system prompt was told a single message
asking for both a draft AND a publish is itself the request to do both — the model's own stated
reasoning explicitly names that instruction and still declines to act on it, asking for a second
turn. **Fallback if the agent stalls anyway:** say so plainly ("it drafted but wants a second
instruction to publish — that's a known, measured behavior, not a crash") and send the publish
instruction as its own message; if it stalls again, switch to the raw script calls in
`rehearsal.md` §3/§5, which do not depend on the agent's own judgment about compound instructions.

## 3. The line

Say it, don't imply it: *"Nothing here applies itself. The system detects, it proposes, it
measures — and a human accepts. 'Self-improving' means the loop proposes its own fixes and can
prove whether they worked; it does not mean unsupervised."*

## 4. What to say when a metric moves

- **A number differs from the slide** → "this is a live run; the recorded run is `<id>`, and the
  3-run spread for this metric was ±X" — pull the exact spread from
  `docs/plans/phase-9-eval-data-loop/verification-record.md` (the rebaseline record's
  `pct_fully_supported` spread) rather than restating a number here; this doc is exactly why every
  metric in this phase is reported as mean ± spread over persisted runs, never a single draw.
  Rehearsing this beat itself proved the point: landing a clean, zero-*unrelated*-regression
  after-run for the accepted flagship fix (`rehearsal.md` §3) took four attempts — one hit an
  unrelated noisy row, two hit a judge artifact on a bare declarative opening sentence in the new
  article's own answer (fixed by rephrasing the article, not by re-running) — and the targeted
  fix's own rows flipped reliably once that was fixed. §3-alt's simpler retune needed 1-2 retries
  for the same reason. Which specific borderline row moves is not reliable; that the fix's own row
  moves is.
- **The judge disagrees with the room** → point to the scorecard: κ vs. the human labels (§10 of
  `verification-record.md`), and `judge_disagreement` is a taxonomy cause with **no content fix** —
  it means calibrate the judge (task 08's territory), not rewrite an article.
- **Groundedness looks low** → the retired 58.8% story (`verification-record.md` §7): a single,
  unpersisted, `temperature=1.0` run judged by the same model family that wrote the answers. Fixed
  and re-baselined; the number now reported is a mean over persisted runs, with its spread, on
  `temperature=0` and a stronger judge model — which is *why* a spread is reported at all instead of
  one number.
- **The agent stalls or does something odd mid-demo** → `temperature=0` does not make tool-calling
  deterministic (`verification-record.md` §9a: six agent-suite measurements across two code states
  scored 80/100/90/90/80/80 — no prompt wording tried so far has produced three identical runs).
  Name it as a measured fact, use the fallback (§2, beat 4), and move on.
- **A beat fails live for any other reason** → name the fallback, move on, come back to it in
  questions.

## 5. What we found by measuring ourselves

Each finding below is real and evidenced — a pointer, not a restated number, so there is one
source of truth per fact.

1. **Three splitter/judge bugs**, fixed in one pass: abbreviation-unsafe sentence splitting, a
   boilerplate refusal closer bleeding into faithfulness scoring, and the old (pre-5.4) judge/answer
   model pairing. `apps/api/app/eval/groundedness.py`'s splitter fix, commit `03ade1c`;
   `.superpowers/sdd/phase-9-eval-data-loop/reports/task-05d-implementer.md`.
2. **The refusal-semantics defect**: the weak-query decline detector missed 2 of 3 real refusal
   strings recorded in the golden set (a substring match too narrow for the model's actual refusal
   phrasing) while false-positiving on a substantive answer that merely ended with a hedge.
   `.superpowers/sdd/phase-9-eval-data-loop/reports/task-15-review.md` (finding), fix commit
   `57b8efb`.
3. **Mis-pinned ground truth that made recall@k look perfect**: four golden `expected_chunks` refs
   were drawn from whatever the retriever happened to return, not from what actually supports the
   answer; re-pointing them to the correct section dropped `recall_at_k` from 1.00 to as low as 0.50
   on three of the four — the metric was measuring the retriever against itself.
   `.superpowers/sdd/phase-9-eval-data-loop/progress.md` ("MAJOR MEASUREMENT INSIGHT", task 14);
   `.superpowers/sdd/phase-9-eval-data-loop/reports/task-14-review.md`.
4. **The acceptance-gate hole found by attacking it**: an Opus review of task 16 found that an
   empty or narrower after-run passed the regression gate vacuously (nothing to compare means
   nothing can regress) and that a stale, pre-dating run could be accepted as "after" with no
   ordering check. `.superpowers/sdd/phase-9-eval-data-loop/reports/task-16-review.md`; fixed in
   commit `83e0a54` (the acceptance gate is twelve rungs as of this phase, not the six the original
   design sketched).
5. **A good fix for a planted gap was refused by the gate because the golden set still said the
   gap was unanswerable — the eval data was the stale thing, so a fix must ship with its eval
   rows.** Measured directly, twice, on two different planted gaps, before the fix: closing a real
   content gap with a genuinely good article flipped that gap's own golden `near_miss` row from a
   correct refusal to a real, correct answer the stale `answerable: false` label didn't expect —
   `accept_proposal` correctly refused a good fix. DESIGN §C's own rule ("a fix ships with its eval
   rows, the same way code ships with tests") is the actual fix: re-label the gap's `near_miss` rows
   `answerable: true` and add the new article's own eval rows in the same demo action, and the
   after-run shows 0 regressions with the new rows landing as `added` (the coverage gate allows a
   superset). `docs/plans/phase-9-eval-data-loop/rehearsal.md` §2's closing note (the failure) and
   §3 (the fix, run for real). **Say this line if step 3 gets cut on stage.**
6. **A faithfulness judge cannot tell "supported by a wrong source" from "supported by a right
   source"** — confidently wrong, self-consistent prose sailed through faithfulness scoring in the
   rehearsal's first bad-fix attempt; only retrieval displacement (out-ranking the real article,
   not out-arguing the judge) reliably broke the gate. `docs/plans/phase-9-eval-data-loop/
   rehearsal.md` §5.
7. **`pct_fully_supported` alone can hide a real regression** — the rehearsal's final bad-fix run
   showed pct *improve* (+1.6) while two real, named regressions sat underneath it, because an
   unrelated genuine fix landed in the same before/after window. This is exactly why the acceptance
   gate checks `pct not dropped` and `compare_runs(...).regressions == []` as two separate gates,
   not one. `docs/plans/phase-9-eval-data-loop/rehearsal.md` §5.
8. **The agent suite's own reference trajectory was stale** — it demanded a literal `create_draft`
   call for a "propose a fix" task after tasks 15/16 taught the agent to call `propose_content_fix`
   instead, so a correctly-behaving run was scored as a partial failure until fixed.
   `.superpowers/sdd/phase-9-eval-data-loop/reports/agent-suite-regression.md`; fixed in commit
   `d5ac13c`; the corrected three-run spread (83.3% ± 10.0) is `verification-record.md` §9a.

## After the talk

Leftovers that belong to the whole-branch review, not the stage: corpus wave 2, the RAGAS
cross-check, the retrieval-recall weakness in `multi_source` questions (ledgered: cap chunks per
content in top-k, or MMR diversity — a real candidate now that this task's bad-fix beat proved
retrieval displacement is easy to trigger deliberately, which cuts both ways), updating the golden
set's `near_miss` rows once a planted gap is actually closed on prod, and the harness not printing
its own `eval_runs` id (a `psql` round-trip is currently the only way to read it back).
