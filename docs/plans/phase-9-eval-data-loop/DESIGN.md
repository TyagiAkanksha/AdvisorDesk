# Phase 9 — Evaluated, self-improving loop + designed corpus — Design Spec

**Status:** approved by owner 2026-09-12 (seven decisions taken one at a time; plan approved via
Plan Mode). Implementation plan: `docs/plans/phase-9-eval-data-loop/00-INDEX.md` + task files
(written per step). Drives the 2026-09-24 talk *"Beyond RAG: Building an Evaluated,
Self-Improving Agentic AI System"*.
**Goal:** make AdvisorDesk's evaluation and improvement loop real and measurable — persisted eval
runs with standard metrics, an agent trajectory suite, a calibrated judge with a scorecard, an
automatic failure taxonomy, weak-query detection, a data-gated proposal record — on top of a
corpus designed so that grounding, refusal and gaps are visible to a technical audience.

Governing docs: `advisordesk-prd.md` (§1.3 principles, §2 user stories, §6 MCP tools, §7 RAG,
§8 seed data, §9.1 metrics), `CONVENTIONS.md` (§5 Settings/zero-env, §8 regenerate
`openapi.json`/`mcp-tools.json`, §10 tests), `docs/FRONTEND-CONVENTIONS.md` (feedback UI).

---


## Context — why this, and why now

**The topic is two things at once.** AdvisorDesk is "a content hub for financial advisory firms:
advisors publish guidance, clients get cited answers **only** from it" (PRD §1). On 24 Sep the
owner co-presents *"Beyond RAG: Building an Evaluated, Self-Improving Agentic AI System"* using
AdvisorDesk as the case study, and the abstract promises the audience will see: weak/failed
queries **detected → root cause analysed → fixes proposed → validated by an eval harness before
acceptance**, plus a live demo.

**"Data" therefore means more than articles.** The system has two data flows, and the talk needs
both to be real:

1. **Knowledge flow** — markdown articles → published `content` rows → auto-chunked (every heading
   is a chunk boundary, ≤400+50 tokens) → embedded (OpenAI text-embedding-3-small @1024) →
   retrieved (top-6, cosine ≥ 0.5) → cited answer, or refusal.
2. **Feedback flow** — every question and answer is stored (`chat_messages`: question text,
   citations, `retrieval_found`, `top_similarity`) → `report_content_gaps` lists questions the
   corpus could not answer → (today: nothing further).

**Where we actually stand (facts from the code, 2026-09-11):**

| Data | Today | Verdict for the topic |
|---|---|---|
| Corpus | 28 published items on prod; 21 seed files (17 pub + 4 draft), all ~500-word generic "X Basics" explainers, 6 fixed tags, 100 chunks | An LLM answers all of it without the corpus → grounding/refusal are invisible in a demo; no *specific* facts a firm would own; no deliberate structure for gaps |
| Eval set | 21 questions (17 answerable, 4 off-domain); schema `question / expected_slugs / answerable` only | Too small and one-dimensional: no near-miss, multi-source, or stale-fact classes; no persona; can't explain *why* something failed |
| Eval results | Harness prints a table and exits; **nothing persisted**; single recorded number (58.8%) is sampling noise (temperature 1.0 until yesterday's fix) | "Validated before acceptance" cannot be shown — there is no before/after to compare |
| Serve-time signals | `retrieval_found` (1 bit) + `top_similarity` (written, never read); no per-citation score, no latency, no user feedback | "Weak query" = refusal only; a bad *answer* is undetectable |
| Gap → fix | `content_gaps()` = list of refused questions, newest first; no clustering, no cause, no proposal object; agent can `create_draft` but nothing links a draft to the gap it fixes | The "self-improving" step has no data to stand on |

So the plan is a **data plan in four parts**: (A) signals, (B) evaluation as data, (C) the corpus
and question set as *designed* data, (D) the proposal record that closes the loop. The code that
uses (A)–(D) — weak-query classification, the proposal tools, the demo — is scoped here only as far
as the data needs it; it gets its own task files.

## Guiding decisions (all decided 2026-09-12)

- **D1 — Domain (DECIDED 2026-09-12): equity compensation & benefits for tech employees.**
  A fictional fee-only planning firm ("Queen City Wealth Planning" — DECIDED; Charlotte is
  its address, not its content) whose clients are engineers: RSUs, ESPP, ISOs/NSOs & AMT, 83(b),
  401(k) match & mega-backdoor Roth, HSA, tender offers/IPO lock-ups, leaving with unvested
  equity. Fictional firm and policies, **real, sourced rules and numbers** (IRS publications and
  form instructions, SSA), realistic questions. **Deciding criterion — the talk is a tech talk:
  the room must be able to judge answers live.** Every engineer in the audience has RSUs and
  knows the questions, so grounding, refusal and "rejected its own fix" are checkable in their
  heads; NC-specific rules would have to be taken on faith, so NC shrinks to a 2-article "where
  you live matters" slice. Product-faithful (PRD §1: an advisory firm's content hub); the 27
  existing basics survive as the fundamentals tier. Rejected: dogfooding the repo's own docs
  (verifiable, but breaks the product frame and reads as the "basic RAG" the title moves beyond)
  — kept as an optional 2-minute side demo if time allows.
- **D2 — User feedback signal (DECIDED: yes):** thumbs-up/down on client answers — API column +
  endpoint + a small client UI. The only human signal in the loop; something the audience can
  click during the demo.
- **D3 — Evaluation becomes persistent** (not optional): every harness run writes rows so two runs
  can be diffed. Without this the talk's central claim has no evidence.
- **D4 — The eval set is designed by failure class**, not just "answerable or not".
- **D5 — Scope for the talk:** everything below is sized so that data + loop are demoable by
  ~22 Sep; the corpus lands in two waves (wave 1 = 16 new, rest after the talk if needed).
- **D6 — Demo beats (DECIDED):** (1) an engineer's RSU question → cited answer the room can
  verify; (2) off-domain question → refusal; (3) a planted-gap question → refusal → weak-query
  report shows `near_miss` with the closest source and its similarity; (4) propose → draft →
  publish → harness re-run → `compare_runs` → accept — with the rehearsed variant where a bad
  fix regresses two questions and is **rejected**. Optional (5): a 👎 appears as
  `negative_feedback`; audience questions typed live feed beat 3.
- **D7 — Judge (DECIDED):** `gpt-4o` for recorded numbers (answerer stays `gpt-4o-mini`);
  the human-labelled scorecard covers the same-family caveat.

## Part A — Serve-time signals (what makes "weak" measurable)

Add to `chat_messages` (additive, inside the single migration `0009`):

| Signal | Shape | Why |
|---|---|---|
| per-citation `similarity` | inside the existing `citations` JSONB (no DDL) — `app/services/chat.py:141-148` drops `RetrievedChunk.similarity` today | every stored answer becomes a retrieval trace ("which source was weak"); readers use `.get()` for old rows |
| `feedback` | `smallint NULL`, CHECK in (−1, 1) — nullable so "never asked" ≠ "neutral"; `POST /api/v1/public/chat/{message_id}/feedback` | the only *human* ground truth; the SSE `done` event **already carries `message_id`** (`public_routes.py:252-254`; the client types and discards it) so no wire change |
| `latency_ms` | `integer NULL`, from the `time.monotonic()` already taken in the route | joinable per question; today p50/p95 live only in logs |

Cut as YAGNI: an `answer_kind` column — refused/answered derives from `retrieval_found`; `error`
turns are rolled back today and never get a row (a route change, not a schema one).
`chat_sessions` stays as is (no identity — PRD §12).

## Evaluation approach — DECIDED 2026-09-12 (fixes the shape of the eval data)

Owner chose: **in-house standard metrics + an agent trajectory suite + a calibrated judge**, plus
the three "standout" pieces. Rationale: for a talk, owning the metric definitions beats a
framework dependency; RAGAS is run once on the same golden set as a cross-check slide.

| Layer | Metric (standard name) | How, in our harness |
|---|---|---|
| Retrieval | recall@k (primary, k=6), precision@k, MRR | golden set carries `expected_chunks` (heading-level ids), not just slugs; pure math on `retrieve()` output |
| Generation | faithfulness (claim-level), answer relevance, context precision, context recall | four rubric judges (structured YES/NO + reason), the existing per-sentence judge = faithfulness |
| Refusal | refusal correctness (off-domain + threshold classes) | existing |
| Agent | task success, tool-call precision/recall vs a reference trajectory, step count vs minimum, loops | 8–10 scripted CMS tasks from PRD §2 user stories, run through the real agent loop on a scratch DB; end-state asserted in the DB |
| Judge | **scorecard**: agreement with ~40 human labels (target κ ≥ 0.8), self-consistency ×3, position/verbosity spot-check | judge = a stronger model than the answerer (`gpt-4o` default; a second-family judge optional) |
| Diagnosis | **failure taxonomy** per failed question: `retrieval_miss` · `corpus_gap` · `threshold_refusal` · `generation_unfaithful` · `judge_disagreement` | computed from the signals above; maps 1:1 onto proposal kinds (`new_article` / `expand_article` / `retune`) |
| Reporting | **stability**: every metric reported with its spread over 3 runs | harness `--runs 3`; the temperature-bug lesson as a rule |

Data this implies (Part B below): `expected_chunks` and a short reference answer per eval
question; an `agent_tasks.yaml` with reference trajectories + end-state checks; a
`judge_labels.yaml` of ~40 human-labelled (question, answer, supported?) rows.

## Part B — Evaluation as data

**B1. Persist runs.** New tables (model file `apps/api/app/models/eval.py`):
- `eval_runs`: id, created_at, `label`, `git_sha`, `embedding_model`, `chat_model`, `judge_model`,
  `similarity_threshold`, `retrieval_k`, corpus fingerprint (`corpus_content_count`,
  `corpus_chunk_count`, `corpus_max_updated_at`, `corpus_digest` = sha256 of (slug, updated_at)
  pairs[:16]), totals (`total_questions`, `pct_fully_supported`, `refusal_correct`,
  `refusal_total`).
- `eval_results`: run_id (FK cascade), question, `question_class`, persona, answerable,
  expected_slugs/cited_slugs (JSONB), slugs_hit, fully_supported (null for uncovered), refused,
  verdict, `top_similarity`, `answer_text`; unique (run_id, question).
- `EvalRow` gains `top_similarity` + `answer_text` (both already in hand in
  `_evaluate_question`). `run_eval()` stays pure; persistence lives in `_run_from_cli`, which
  gains argparse: `--label`, `--questions`, `--no-persist` (default persists — the CLI already
  needs `DATABASE_URL`), `--compare-to <run_id|latest>`. Stdout table unchanged.
- New service `apps/api/app/services/eval_runs.py`: `record_run`, `corpus_fingerprint`,
  `compare_runs(before, after) → RunDiff{regressions, improvements, unchanged, added, removed,
  pct_delta}` (joined on question text), `latest_runs`. It lives in `app.services` because the
  import-linter contracts let `app.mcp` import `app.services` but not `app.eval`.
- **`compare_runs` is the one thing never cut** — it is the evidence behind "validated before
  acceptance".

**B2. Eval data — DECIDED 2026-09-12: 80 questions / 10 agent tasks / 40 human labels.**
- `seed/eval_questions.yaml` v2 — required `question`, `expected_slugs`, `answerable`; new
  optional `class` ∈ {`answerable`, `multi_source`, `near_miss`, `off_domain`, `threshold`,
  `stale_number`}, `persona`, `expected_chunks` (as `slug#section-heading-slug`, resolved to
  chunk rows by heading text so recall@k survives re-chunking), `reference_answer` (2–3
  sentences, for the answer-relevance/context-recall judges). Python/column name
  `question_class` (`class` is a keyword); defaults keep the current file valid; `off_domain` ⇒
  not answerable. Counts: 45 answerable · 8 multi_source · 10 near_miss (the planted gaps) ·
  8 off_domain · 5 threshold (answer exists, phrased far from the question — the retune class) ·
  4 stale_number. Authored with each article (2–4 each) plus ~15 persona-first questions so the
  set is not "questions the article answers by construction". `test_seed.py` pins become
  `REQUIRED ⊆ keys ⊆ REQUIRED ∪ OPTIONAL` + membership checks; "≥12 answerable" and "expected
  slugs are published stems" stay.
- `seed/agent_tasks.yaml` (new) — 10 tasks from PRD §2 user stories: draft-and-tag · count by
  tag · find-and-publish drafts with a tag · archive by title · edit a body · add/remove tags ·
  report weak queries · propose a fix from a gap · draft→publish→verify · one ambiguous task
  where the right move is to ask. Each: `prompt`, `reference_trajectory` (ordered tool names +
  argument constraints), `min_steps`, `end_state` (DB assertions: e.g. a published row with
  tags X). Run through the real agent loop against a scratch schema.
- `seed/judge_labels.yaml` (new) — 40 rows (question, answer, cited chunk texts, human
  verdict, labeller), stratified across classes; labelled independently by the owner and
  Abhishek, disagreements resolved together. Feeds the judge scorecard (κ, self-consistency ×3).

**B3. Baseline discipline.** Run the harness 3× on the *current* corpus at `temperature=0` before
any content changes (proves determinism now), record run ids; then after each content wave.
The committed 58.8% is retired with an explanation (noise), not silently overwritten.

## Part C — The corpus and questions as designed data

**C1. Shape every article for the pipeline**, not just for readers (facts: heading = chunk
boundary; ≤400 tokens per section; the retriever matches *question wording*):
- H2 sections of 150–350 tokens, each answering one question, headed the way a client asks it
  ("What happens to my RSUs when they vest?") — the section *is* the retrieval unit.
- A **"Key numbers (2026)"** section per article, and a **"Sources"** section (primary source
  URLs) — real, checkable; a `_Current as of 2026-09_` line.
- One firm voice; the mandated footer line stays (`test_seed.py` pins it); frontmatter unchanged
  (`title`, `tags`, `status`) — plus new tags are allowed only by extending the six-tag vocabulary
  pin (`equity-compensation`, `north-carolina`, `our-firm`).
- Filename = slugified title (pinned). Seed is idempotent **by title**: changed bodies never
  reload — so corpus v2 uses **new titles** (the 27 basics keep theirs) and prod is updated
  through the CMS/MCP `create_draft`+`publish`, seed files are the source of truth.

**C2. Personas (the questions come from these):** *Sam*, new-grad engineer, first RSU grant,
first ESPP window, no idea what "supplemental withholding" is · *Priya*, senior IC at a pre-IPO
startup, ISOs, tender offer coming, AMT scare · *Marcus*, staff engineer at a public company,
concentrated employer stock, maxed 401(k), asking about mega-backdoor Roth and leaving.

**C2. Article list (wave 1 = 15 core, wave 2 = 12):**
- *Equity & compensation for engineers (14, wave 1 = first 10):* RSUs at vest — withholding,
  the supplemental-rate shortfall, sell-or-hold · double-trigger RSUs and IPOs · ESPP —
  qualifying vs disqualifying dispositions · ISOs vs NSOs — how each is taxed · AMT from an ISO
  exercise (and the credit) · the 83(b) election · concentrated employer stock — the firm's 10%
  rule and unwinding it · tender offers and lock-ups · 10b5-1 plans for insiders · mega-backdoor
  Roth (after-tax 401(k)) · HSA as a stealth retirement account · donating appreciated stock &
  DAFs · leaving your employer — unvested equity, 401(k), deferred comp · wash-sale rules across
  RSU/ESPP lots and tax-loss harvesting.
- *Where you live matters (2):* state tax on equity comp when you move (NC as the worked
  example) · remote work across state lines.
- *The firm (6):* how we work & fees · onboarding · rebalancing policy · what we do in a 20%
  drawdown · what we don't do · meetings & what to bring.
- *Fundamentals (existing 27):* keep; add "Key numbers (2026)" + Sources in wave 2.
- **Planted gaps** (never written, so they are live near-miss material the room will hit):
  RSU/ESPP for non-US employees · crypto compensation · stock options in a divorce · 401(k)
  loans against employer stock · QSBS. The near-miss eval class points at these.
- Every article ships with its 2–4 eval questions (B2) — the same way code ships with tests.

**C3. Authoring pipeline (three agents, like code):** brief (audience, the decision, sources) →
draft (Sonnet) → **fact-check agent** verifies every number/rule against the cited primary source
via WebFetch and fails the article on any unverifiable claim → controller/owner skim → file lands
in `seed/sample_content/` → published on prod via MCP. Fictional-firm policies are marked as such
in the brief so the fact-checker skips them.

**C4. Traffic replay:** ~40 realistic persona questions (a subset deliberately near-miss) replayed
against prod via `/api/v1/public/chat` before the talk, so the weak-query report has real rows.

## Part D — Weak queries and the proposal record (closing the loop, minimally)

- **`weak_queries(session, *, days, limit, threshold)`** in `app/services/chat.py` — a second
  consumer of the already-tested user↔reply pairing (extract it from `content_gaps()` into a
  private select; `content_gaps` becomes a wrapper so its 12 tests, `mcp-tools.json` and PRD §6
  stay frozen). Classified in Python, first match wins: `negative_feedback` (feedback = −1) →
  `refused` (not found, `top_similarity` < threshold − 0.15 or null) → `near_miss` (not found,
  `≥ threshold − 0.15`) → `low_confidence` (found, `< threshold + 0.10`). Grouped by exact
  normalised text (casefold, collapse whitespace, strip `?!.`) → `WeakQueryGroup{count, kinds,
  worst_top_similarity, examples[:3]}`. Exposed as a new MCP tool `report_weak_queries`.
- **`content_proposals`** (created in the same migration even if its tools slip): id,
  created_at/updated_at, `kind` (`new_article|expand_article|retune`), `title`, `rationale`,
  `evidence` JSONB **snapshot** of weak-query rows (not FKs — chat rows are prunable and the
  blob is what goes on the slide), `target_content_id?`, `draft_content_id?`, `status`
  (`proposed|accepted|rejected`), `eval_run_before_id?`, `eval_run_after_id?`, `created_by?`.
- **Tools** (`app/mcp/tools_proposals.py`, `app/services/proposals.py`): `propose_content_fix`
  (creates the draft via the existing `create_draft`, links it, stamps the latest run as
  `before`), `list_proposals`, `accept_proposal(proposal_id, eval_run_after_id)`,
  `reject_proposal`. Sequence: propose → agent publishes the draft → harness re-run → accept.
- **"Validated before acceptance" is a data precondition**, not a synchronous harness run (a run
  is minutes — no MCP step budget allows it): `accept_proposal` raises `ConflictError` unless
  before/after runs exist, the after-run's `corpus_digest` differs, `pct_fully_supported` did not
  drop and `compare_runs(...).regressions` is empty. A regressed proposal is rejected and the
  draft archived — the best demo beat available ("the harness said no, so the system rejected
  its own fix").
- Corpus versioning needs no new column: `Content.updated_at` is stamped on every write, so the
  digest above identifies the corpus a run measured.

## Migration `0009_eval_and_feedback` (one, additive, no backfill)

`chat_messages` + `feedback`, `latency_ms` · `eval_runs` · `eval_results` · `content_proposals`.
Enums as text + CHECK (matches `Content.status`); `downgrade` drops in reverse FK order. Parity
gate: `tests/test_models_schema.py` compares ORM vs migration incl. server defaults.

## Execution order (each row = SDD task files + three agents; details in task files)

1. **Signals + eval persistence** — migration 0009 (feedback, latency_ms, eval_runs,
   eval_results, content_proposals), `citations.similarity`, feedback endpoint (+ `openapi.json`
   / client codegen), `models/eval.py`, `services/eval_runs.py`, harness argparse + persist +
   `compare_runs` + `--runs 3` stability, eval YAML v2 loader and pins. *(~3 tasks)*
2. **Metrics v2** — `expected_chunks` resolution + recall@k/precision@k/MRR; answer-relevance,
   context-precision, context-recall rubric judges; judge model setting (`gpt-4o`); the failure
   taxonomy classifier over a run's rows. *(~2 tasks)*
3. **Agent trajectory suite** — `seed/agent_tasks.yaml` loader, run tasks through the real agent
   loop on a scratch schema with a recording tool wrapper, score trajectory/success/steps,
   persist as an `eval_runs` row of kind `agent`. *(~2 tasks)*
4. **Judge scorecard** — `seed/judge_labels.yaml` loader, κ vs human labels, self-consistency
   ×3, position/verbosity spot-check, one report. *(1 task; the 40 labels come from the owner +
   Abhishek's labelling session — the harness writes the unlabelled rows out for them)*
5. **Baseline** — 3× harness on the *current* corpus, persisted (proves determinism; retires the
   58.8% with an explanation). *(script run)*
6. **Corpus wave 1 + golden set** — 16 articles (12 equity + 4 firm) with 2–4 questions each +
   ~15 persona-first questions → 80 total incl. planted-gap near-misses; authoring pipeline C3;
   seed files land; prod publish via MCP; harness run + `compare_runs`. *(content tasks,
   batchable; runs in parallel with 2–4)*
7. **Weak queries + proposals** — `weak_queries`, `report_weak_queries`, proposal kinds from the
   taxonomy, `services/proposals.py`, four MCP tools (+ `mcp-tools.json`), agent prompt
   awareness. *(~2.5 tasks)*
8. **Feedback UI** — client 👍/👎 under assistant bubbles. *(1 task)*
9. **Traffic replay + demo rehearsal** — replay set against prod, before/after run ids, the
   "rejected its own fix" rehearsal, run sheet. *(1 task)*
10. **Corpus wave 2** — ~10 more + fundamentals upgrade; RAGAS cross-check run (after the talk
    if time is short).

Process: each task = task file → test-author → implementer → reviewer (Sonnet-first, Opus on the
migration/harness/agent-suite/proposal tasks and the whole-branch final), per CLAUDE.md; one
branch (`feat/eval-data-loop`), PR, deploy in the additive order (migrate first — 0009 is
additive). Cut order if squeezed: RAGAS cross-check → wave 2 → feedback UI → proposal tools
(table stays) → position/verbosity spot-check → `latency_ms`. Never cut: `compare_runs`,
the taxonomy, the 3-run spread, the agent suite (it is what makes "agent evaluation" true).

## Verification

- API: `uv run pytest` with `TEST_DATABASE_URL` (migration round-trip; new pins for feedback,
  eval persistence, weak-query classes); `openapi.json` regenerated + client codegen in the same
  commit for the feedback endpoint; import-linter contracts green.
- Content: `test_seed.py` pins (frontmatter, footer, slug=stem, tag vocabulary, eval schema v2);
  fact-check reports per article with source URLs; `python -m app.seed` on a scratch DB →
  expected `created/published/chunk_count`.
- Loop: on a scratch DB — replay the near-miss questions → `weak_queries()` lists them classified
  → `propose_content_fix` creates the draft → publish → harness run `after` shows the near-miss
  rows flipping to PASS with no regressions (`compare_runs`) → `accept_proposal`; and the
  rehearsed bad fix is rejected. Agent suite: 10/10 tasks scored, trajectory report persisted.
  Judge scorecard: κ vs the 40 labels and ×3 self-consistency reported; taxonomy distribution
  before/after wave 1; every metric with its 3-run spread.
- Prod: publish wave 1 through the CMS; the `prod-probe` workflow stays green; a live run of the
  loop end-to-end recorded in the run sheet.

## Decisions — all taken 2026-09-12, one by one

1. **Domain:** equity compensation & benefits for tech employees; fictional fee-only firm
   **Queen City Wealth Planning**; real sourced rules. Criterion: the room can judge answers live.
2. **Evaluation approach:** in-house standard metrics (RAGAS-named) + agent trajectory suite +
   calibrated `gpt-4o` judge; standout pieces = judge scorecard, failure taxonomy, stability.
3. **Eval data:** 80 questions / 10 agent tasks / 40 human labels.
4. **Demo beats + corpus:** the four beats above; wave 1 = 12 equity + 4 firm articles, 27
   basics kept, 5 planted gaps.
5. **Feedback signal:** yes (API + client UI). **Judge:** gpt-4o.

