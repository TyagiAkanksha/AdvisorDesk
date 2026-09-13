---
id: p9-t12
phase: phase-9-eval-data-loop
depends_on: [p9-t11]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 12 — Corpus wave 1, batch C: concentrated employer stock · tender offers & lock-ups · mega-backdoor Roth · rebalancing + the 20% drawdown policy

## Goal

Marcus's batch, plus Priya's liquidity event. Four more wave-1 articles and their 11 eval questions:
the firm's concentration policy (the 10% rule) and how a position gets unwound inside trading
windows, tender offers and lock-ups, the mega-backdoor Roth, and the firm's rebalancing policy
including what happens in a 20% drawdown. The batch carries the "crypto compensation" planted gap as
its near-miss.

Same four-agent content pipeline as batches A and B (DESIGN §C3): test-author (pins) → drafter
(Sonnet) → fact-check agent (Sonnet, WebFetch, a different agent) → Opus batch review. Every number
is verified against a named primary source or it does not ship. **No prod publish** (task 18).

**Depends on task 11** because all four batches edit the same two files
(`seed/eval_questions.yaml`, `apps/api/tests/test_seed.py`) and because batch C's `multi_source` rows
cite a batch-A slug.

**No application code changes.** The only Python file this task touches is `apps/api/tests/test_seed.py`.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/FIRM-FACTS.md` — the fictional firm's fee schedule,
  policies and voice (controller ruling 2026-09-12): every `[FIRM POLICY]` value in this batch
  comes from THAT file verbatim — never invent a figure, never contradict it.
- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §C1 (article shape), §C2 (personas, article list,
  the five planted gaps), §C3 (authoring pipeline), §B2 (v2 eval keys, the six classes).
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` — "Global Constraints".
- `apps/api/tests/test_seed.py` — **all of it, at its post-task-11 state**: `_WAVE1_ARTICLES` (eight
  entries), `_WAVE1_TAGS`/`_ALLOWED_TAGS`, `_wave1_records`, `_h2_sections`, the token-band /
  heading / class-count pins, and the pre-existing DB pin
  `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus`.
- `seed/eval_questions.yaml` — the 43 committed rows (21 phase-4 + 11 batch A + 11 batch B); this
  task appends 11 more and changes nothing above them.
- `seed/sample_content/how-we-work-and-what-we-charge.md` and
  `seed/sample_content/onboarding-with-us-and-what-to-bring.md` — the firm voice and the fictional
  figures batch C's two firm pages must stay consistent with.
- `seed/sample_content/what-happens-to-your-rsus-at-vest.md` — the file batch C's multi_source rows
  cite.
- `seed/sample_content/rebalancing-your-portfolio-basics.md` — the phase-4 **draft** on rebalancing
  mechanics. C4 is the firm's *policy* page and must not restate it; it must also keep a different
  title and slug (it does).
- `apps/api/app/rag/chunking.py` — `_HEADING_RE` (any ATX heading is a chunk boundary),
  `count_tokens` (`cl100k_base`), `chunk_markdown`'s 400+50 budget.
- `apps/api/app/services/content.py` lines 26–32 — `_slugify`.
- `apps/api/app/eval/questions.py` — `load_questions` validation and `resolve_expected_chunks`.

Do **not** read tasks 13–14.

## Files

**Create (content)**
- `seed/sample_content/concentrated-employer-stock-and-our-10-rule.md`
- `seed/sample_content/tender-offers-and-lock-up-periods.md`
- `seed/sample_content/the-mega-backdoor-roth-step-by-step.md`
- `seed/sample_content/our-rebalancing-policy-and-the-20-drawdown-rule.md`

**Create (fact-check reports, gitignored scratch area)**
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-concentrated-employer-stock-and-our-10-rule.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-tender-offers-and-lock-up-periods.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-the-mega-backdoor-roth-step-by-step.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-our-rebalancing-policy-and-the-20-drawdown-rule.md`

**Modify**
- `seed/eval_questions.yaml` (append the 11 rows below, verbatim)
- `apps/api/tests/test_seed.py` (the edits in Steps RED)

**Do not touch:** the 29 existing `seed/sample_content/*.md` files, any file under `apps/api/app/`,
`seed/agent_tasks.yaml`, `seed/judge_labels.yaml`, prod.

## Interfaces

| Artifact | Consumer |
|---|---|
| four published seed articles | task 13 (multi_source pairs), 14 (persona questions), 18 (prod publish + replay) |
| 11 eval rows incl. 1 near_miss at the "crypto compensation" planted gap | task 14's class balance; task 15's weak-query demo |
| four fact-check reports | the Opus batch review; the whole-branch final review |

### Article shape contract (all four files)

Exactly this shape, nothing else:

```markdown
---
title: <the exact title from the brief>
tags:
  - <tag>
  - <tag>
status: published
---

<lead paragraph, 60-120 words, no heading: who this is for and what decision it serves>

## <client-phrased question 1>

<150-350 tokens answering exactly that question>

## <client-phrased question 2>

...

## Key numbers (2026)

- **<item>** — <verified value> (<source short name>)
- ...

_Current as of 2026-09_

## Sources

- <Source title> — <primary URL>
- ...

Sample content for demonstration purposes — not financial advice.
```

Binding rules:

1. **H2 only.** No `#` H1, no `###`+ anywhere — every ATX heading is a chunk boundary.
2. **Headings verbatim from the brief** (the eval rows reference `slug#slugify(heading)`).
3. **Token band:** each question H2 section 150–350 `cl100k` tokens (`count_tokens`); `Key numbers
   (2026)` and `Sources` ≤ 350 with no lower bound; the lead paragraph ≤ 350.
4. **Numbers are earned.** A number appears only if the fact-check report has a `verified` line for
   it naming the fetched URL and quoting the source. Otherwise write **the rule, not the number**.
   Unverifiable claim ⇒ the article FAILS and goes back to the drafter.
5. **Fictional firm policy** lines are marked `[FIRM POLICY — fictional, skip fact-check]`; in the
   article they read as the firm's own policy and never appear under `## Sources`. Any fee, band,
   threshold or cadence figure must match `how-we-work-and-what-we-charge.md` and
   `onboarding-with-us-and-what-to-bring.md` where those already state it.
6. **Planted gaps stay unwritten:** no rule and no number for non-US employees' equity, crypto
   compensation, stock options in a divorce, 401(k) loans against employer stock, or QSBS (§1202).
   C1 and C4 both brush against crypto and hedging — a one-clause "we do not advise on this"
   boundary is allowed; a tax rule or a number is not.
7. **Voice:** one firm voice, second person to the client. C1 and C4 are firm pages and speak as
   "we"; C2 and C3 are explainers that name the firm at most once.
8. `_Current as of 2026-09_` closes the Key numbers section; the verbatim footer is the last
   non-blank line (em dash U+2014).

---

## Article brief C1 — Concentrated Employer Stock and Our 10% Rule

- **Title (exact):** `Concentrated Employer Stock and Our 10% Rule`
- **Filename:** `seed/sample_content/concentrated-employer-stock-and-our-10-rule.md`
- **Tags:** `our-firm`, `investing-basics`, `equity-compensation` · **Status:** `published`
- **Persona:** Marcus — staff engineer at a public company, large vested position in his employer's
  stock, maxed 401(k), subject to trading windows.
- **Decision it serves:** how much company stock to keep, and the mechanics of getting from here to
  there without breaking a trading policy.

**H2 outline (verbatim headings, in this order):**

1. `## How much of my net worth should sit in company stock?` — the firm's policy ceiling and what it
   is measured against (investable net worth, not total net worth). `[FIRM POLICY — fictional, skip
   fact-check]` for the 10% figure itself.
2. `## What is the risk I am actually taking?` — single-stock risk vs market risk in plain terms: the
   correlation between the position and the salary that funds your life; a concentrated position can
   fall far more than the index and need not recover with it. No invented statistics — if a
   dispersion statistic is wanted, it must be sourced or omitted.
3. `## How do we unwind a concentrated position?` — a written schedule of partial sales, the order of
   lots (basis and holding period), the new-shares-first principle (selling each vest costs little
   tax), and a stated end date. `[FIRM POLICY]` for cadence.
4. `## What about my trading window and blackout periods?` — open windows and blackouts as company
   policy; a Rule 10b5-1 trading plan adopted while you hold no material non-public information, and
   the cooling-off period the SEC rule imposes before the first trade.
5. `## Can I hedge instead of selling?` — collars, prepaid forwards and pledging as things that exist
   and that the firm does not do or advise on; the one-clause boundary and the pointer to the "what
   we do not do" page (batch D). No options-strategy mechanics.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the 10% of investable net worth ceiling; the review cadence; the default unwind horizon | none | `[FIRM POLICY — fictional, skip fact-check]` |
| the cooling-off period between adopting a Rule 10b5-1 plan and the first trade (and that it differs for directors and officers) | 17 CFR 240.10b5-1 (ecfr.gov) and SEC Release 33-11138, "Insider Trading Arrangements and Related Disclosures" | `[STATUTORY]` — quote the rule's own text |
| the conditions a 10b5-1 plan must meet to be an affirmative defence (no MNPI at adoption, good faith, no influence over execution) | 17 CFR 240.10b5-1(c) | rule, no number |
| the holding period that makes a sale long-term | IRS Topic No. 409, Capital Gains and Losses | `[STATUTORY]` |

**`## Sources`:** 17 CFR 240.10b5-1 · SEC Release 33-11138 · IRS Topic No. 409. The fictional policy
figures are **not** sourced.

---

## Article brief C2 — Tender Offers and Lock-Up Periods

- **Title (exact):** `Tender Offers and Lock-Up Periods`
- **Filename:** `seed/sample_content/tender-offers-and-lock-up-periods.md`
- **Tags:** `equity-compensation`, `tax-planning` · **Status:** `published`
- **Persona:** Priya — a tender offer is coming at her pre-IPO employer; an IPO and a lock-up may
  follow.
- **Decision it serves:** whether to sell into the tender, and how much.

**H2 outline (verbatim headings, in this order):**

1. `## What is a tender offer and why is my company running one?` — an offer to buy shares from
   existing holders at a set price for a set period; why private companies run them (employee
   liquidity, investor demand); that participation is a choice.
2. `## How is the money I get from a tender offer taxed?` — it is a sale: capital gain over basis,
   long-term only if the holding period is met; withholding is generally not applied to a sale, so
   the tax is yours to set aside.
3. `## Should I sell some shares into the tender?` — framed as the concentration and liquidity
   question it is, with a pointer to the firm's concentration policy (C1); the pre-IPO valuation is
   not a price you can rely on later.
4. `## What does a lock-up period stop me from doing?` — a contractual restriction from the
   underwriting agreement, not a tax rule; the tax on settlement is already fixed while the price is
   not; plan the sale schedule and the tax set-aside before it lifts.
5. `## What happens to my ISOs in a tender offer?` — selling ISO shares before the statutory holding
   periods is a disqualifying disposition and the spread becomes ordinary income; exercising in order
   to tender is a decision with an AMT tail (cross-reference batch B, do not re-derive AMT).

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the minimum period an issuer tender offer must stay open | 17 CFR 240.13e-4(f) (ecfr.gov) | `[STATUTORY]` |
| the two ISO holding periods, and that failing them is a disqualifying disposition | IRC §422(a)(1) + IRS Publication 525, "Incentive stock options" | `[STATUTORY]` |
| the holding period for long-term capital gain | IRS Topic No. 409 | `[STATUTORY]` |
| the net investment income tax rate and the income thresholds it applies above | Instructions for Form 8960 (and IRC §1411) | `[STATUTORY]` — note in the article that these thresholds are not inflation-adjusted |

**`## Sources`:** 17 CFR 240.13e-4 · IRS Pub 525 · IRS Topic No. 409 · Instructions for Form 8960.

> Lock-up length is a market convention: write "typically about six months" only if the
> fact-checker verifies it against a primary source (e.g. an SEC investor bulletin); otherwise
> "for a period set by the underwriting agreement".

---

## Article brief C3 — The Mega-Backdoor Roth, Step by Step

- **Title (exact):** `The Mega-Backdoor Roth, Step by Step`
- **Filename:** `seed/sample_content/the-mega-backdoor-roth-step-by-step.md`
- **Tags:** `retirement`, `tax-planning` · **Status:** `published`
- **Persona:** Marcus — already maxing his elective deferral, wants the next tax-advantaged dollar.
- **Decision it serves:** whether his plan supports after-tax contributions plus a Roth conversion,
  and how much room he actually has.

**H2 outline (verbatim headings, in this order):**

1. `## What is a mega-backdoor Roth?` — after-tax (non-Roth) contributions to the 401(k), then an
   in-plan Roth conversion or an in-service rollover to a Roth IRA; the name is industry slang, not a
   tax term.
2. `## How much can actually go in?` — the overall annual limit on all contributions to the plan for
   you, minus your elective deferrals and your employer's contributions; what is left is the
   after-tax room. State the limits only as verified.
3. `## Does my plan even allow this?` — the plan document must permit after-tax contributions **and**
   either in-plan Roth conversions or in-service distributions; how to check (summary plan
   description, plan administrator); that nondiscrimination testing can cap or refund contributions.
4. `## What about the pro-rata rule and earnings?` — earnings on after-tax contributions are taxable
   when converted; converting promptly keeps the taxable slice small; the separate-accounting rule
   for after-tax money.
5. `## What order should I fund my accounts in?` — the firm's funding order: match, then HSA if
   eligible, then deferral, then after-tax; stated as the firm's policy, with a pointer to the
   existing HSA article rather than restating it. `[FIRM POLICY — fictional, skip fact-check]` for
   the order itself.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the 2026 elective deferral limit (§402(g)) | the IRS newsroom release announcing 2026 retirement-plan limits **and** the IRS Notice it links — record the Notice number in the report | `[ANNUAL]` |
| the 2026 overall limit on annual additions (§415(c)) | same source | `[ANNUAL]` |
| the age-50 catch-up amount, and the higher catch-up for ages 60–63 | same source (and the IRS "401(k) plan catch-up contribution limits" page) | `[ANNUAL]` |
| the 2026 annual compensation limit (§401(a)(17)) | same source | `[ANNUAL]` |
| that earnings on after-tax contributions are taxable on conversion | IRS Publication 575, "Rollovers" / designated Roth account discussion | rule, no number |

**`## Sources`:** the IRS 2026 retirement-plan limits release and its Notice · IRS Pub 575 · IRS
"Retirement topics — 401(k) and profit-sharing plan contribution limits".

---

## Article brief C4 — Our Rebalancing Policy and the 20% Drawdown Rule

- **Title (exact):** `Our Rebalancing Policy and the 20% Drawdown Rule`
- **Filename:** `seed/sample_content/our-rebalancing-policy-and-the-20-drawdown-rule.md`
- **Tags:** `our-firm`, `investing-basics` · **Status:** `published`
- **Persona:** all three; in practice the page a client opens when markets fall.
- **Decision it serves:** what the firm will do, and what it will ask of you, before the next
  drawdown.

**H2 outline (verbatim headings, in this order):**

1. `## When do you rebalance my portfolio?` — quarterly review plus drift bands around each target
   weight; rebalance on breach, not on the calendar. `[FIRM POLICY — fictional, skip fact-check]`
2. `## What do you do in a 20% drawdown?` — the out-of-cycle review the policy triggers: rebalance
   into what fell, harvest losses in taxable accounts where no wash sale results, revisit the cash
   reserve, and change the plan only if the client's facts changed. `[FIRM POLICY]` for the 20%
   trigger.
3. `## Will rebalancing create a tax bill?` — where rebalancing is done first (tax-deferred
   accounts), how new cash and dividends are used, and the wash-sale constraint on harvesting —
   sourced.
4. `## What will you ask me to do in a downturn?` — the client-side policy: no unscheduled selling,
   keep contributions running, one conversation before any change. `[FIRM POLICY]`
5. `## How does my company stock fit into rebalancing?` — a concentrated position is unwound on its
   own schedule and is not treated as a diversified asset class; pointer to C1. `[FIRM POLICY]`

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the drift bands, the quarterly cadence, the 20% drawdown trigger, the cash-reserve target | none | `[FIRM POLICY — fictional, skip fact-check]` — keep consistent with the other firm pages |
| the wash-sale window on either side of a loss sale, and that a substantially identical security triggers it | IRS Publication 550, "Wash Sales" (and IRC §1091) | `[STATUTORY]` |
| the annual limit on net capital loss deductible against ordinary income, and that the excess carries forward | IRS Pub 550, "Capital Losses" (and IRC §1211(b)) | `[STATUTORY]` |

**`## Sources`:** IRS Pub 550 · IRC §1091 · IRC §1211. The fictional policy figures are **not**
sourced.

---

## Eval questions — append verbatim to `seed/eval_questions.yaml`

Append after batch B's rows, preceded by this comment line:

```yaml
# --- phase-9 wave 1, batch C (task 12): concentration · tender offers · mega-backdoor Roth · rebalancing ---
```

Per article (DESIGN §C2: "every article ships with its 2–4 eval questions"): rows 1–3 → **C1**,
rows 4–6 → **C2** (row 5 is C2's planted-gap near-miss, authored with it but citing nothing),
rows 7–9 → **C3**, rows 10–11 → **C4**. Classes within the batch: 6 `answerable`, 2 `multi_source`,
1 `near_miss`, 1 `threshold`, 1 `stale_number`.

Then exactly these 11 rows, in this order, unedited:

```yaml
- question: "How much of my net worth is too much in my company's stock?"
  expected_slugs: ["concentrated-employer-stock-and-our-10-rule"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks:
    - "concentrated-employer-stock-and-our-10-rule#how-much-of-my-net-worth-should-sit-in-company-stock"
  reference_answer: >-
    Queen City's policy is that a single company's stock should not exceed 10% of your investable
    net worth. Above that, the firm treats the excess as a position to unwind on a written schedule
    rather than a reason to guess at the share price.

- question: "I can only trade in an open window — how do we sell down my position?"
  expected_slugs: ["concentrated-employer-stock-and-our-10-rule"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks:
    - "concentrated-employer-stock-and-our-10-rule#what-about-my-trading-window-and-blackout-periods"
    - "concentrated-employer-stock-and-our-10-rule#how-do-we-unwind-a-concentrated-position"
  reference_answer: >-
    Sales are scheduled inside your company's open trading windows, in partial tranches rather than
    one large sale. Where blackouts get in the way, a Rule 10b5-1 plan adopted while you hold no
    material non-public information can let pre-scheduled sales run after its cooling-off period.

- question: "I am over your concentration limit and my next RSU tranche vests in March — how do we bring it down?"
  expected_slugs:
    - "concentrated-employer-stock-and-our-10-rule"
    - "what-happens-to-your-rsus-at-vest"
  answerable: true
  class: multi_source
  persona: "Marcus"
  expected_chunks:
    - "concentrated-employer-stock-and-our-10-rule#how-do-we-unwind-a-concentrated-position"
    - "what-happens-to-your-rsus-at-vest#should-i-sell-my-shares-at-vest-or-hold-them"
  reference_answer: >-
    The first lever is the new shares: selling each tranche at vest adds almost no tax cost because
    you are already taxed on its full value. The existing position is unwound on a written schedule
    inside your trading windows, with each lot's basis and holding period considered before it is
    sold.

- question: "My startup is running a tender offer — how will the proceeds be taxed?"
  expected_slugs: ["tender-offers-and-lock-up-periods"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks: ["tender-offers-and-lock-up-periods#how-is-the-money-i-get-from-a-tender-offer-taxed"]
  reference_answer: >-
    Selling into a tender offer is a sale: you owe capital gains tax on the difference between the
    price and your basis, long-term only if you met the holding period. If the shares came from an
    ISO exercise, the sale can also be a disqualifying disposition that turns part of the gain into
    ordinary income.

- question: "Part of my offer is paid in stablecoins and token grants — how is that taxed?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Priya"

- question: "After the listing I am told I cannot touch my shares for six months. What is that, and what should I be doing in the meantime?"
  expected_slugs: ["tender-offers-and-lock-up-periods"]
  answerable: true
  class: threshold
  persona: "Priya"
  expected_chunks: ["tender-offers-and-lock-up-periods#what-does-a-lock-up-period-stop-me-from-doing"]
  reference_answer: >-
    That is a lock-up: a contractual restriction on selling for a set period after the offering,
    imposed by the underwriting agreement rather than by tax law. Use the time to set the sale
    schedule and the tax set-aside, because the restriction ends on a date you already know.

- question: "What is a mega-backdoor Roth, and will my 401(k) let me do it?"
  expected_slugs: ["the-mega-backdoor-roth-step-by-step"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks:
    - "the-mega-backdoor-roth-step-by-step#what-is-a-mega-backdoor-roth"
    - "the-mega-backdoor-roth-step-by-step#does-my-plan-even-allow-this"
  reference_answer: >-
    A mega-backdoor Roth means making after-tax, non-Roth contributions to your 401(k) and then
    moving them into a Roth account through an in-plan conversion or a rollover. It only works if
    your plan document allows both the after-tax contributions and the conversion or in-service
    distribution.

- question: "I already max out my 401(k) — how much more can I put in after tax?"
  expected_slugs: ["the-mega-backdoor-roth-step-by-step"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks: ["the-mega-backdoor-roth-step-by-step#how-much-can-actually-go-in"]
  reference_answer: >-
    Your room is the overall annual limit on everything contributed to the plan for you, minus your
    own elective deferrals and anything your employer contributes. Whatever is left is the most you
    can add as after-tax contributions, and plan testing can reduce it further.

- question: "What is the total amount that can go into my 401(k) from all sources this year?"
  expected_slugs: ["the-mega-backdoor-roth-step-by-step"]
  answerable: true
  class: stale_number
  persona: "Marcus"
  expected_chunks: ["the-mega-backdoor-roth-step-by-step#key-numbers-2026"]

- question: "When do you rebalance my portfolio, and what happens in a big market drop?"
  expected_slugs: ["our-rebalancing-policy-and-the-20-drawdown-rule"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks:
    - "our-rebalancing-policy-and-the-20-drawdown-rule#when-do-you-rebalance-my-portfolio"
    - "our-rebalancing-policy-and-the-20-drawdown-rule#what-do-you-do-in-a-20-drawdown"
  reference_answer: >-
    The firm reviews allocations quarterly and rebalances when a holding drifts outside its policy
    band. A drop of 20% or more triggers an out-of-cycle review that rebalances into what fell and
    harvests losses in taxable accounts where doing so would not create a wash sale.

- question: "If the market falls 20% while most of my money is in company stock, what do you do?"
  expected_slugs:
    - "our-rebalancing-policy-and-the-20-drawdown-rule"
    - "concentrated-employer-stock-and-our-10-rule"
  answerable: true
  class: multi_source
  persona: "Marcus"
  expected_chunks:
    - "our-rebalancing-policy-and-the-20-drawdown-rule#what-do-you-do-in-a-20-drawdown"
    - "concentrated-employer-stock-and-our-10-rule#what-is-the-risk-i-am-actually-taking"
  reference_answer: >-
    The drawdown review still runs, but a concentrated position changes what it can do: one company
    can fall much further than the market and need not recover with it. The firm keeps unwinding
    the position on its schedule rather than pausing sales because the price is down.
```

**The one row the implementer completes:** the `stale_number` row ships from this brief *without*
`reference_answer`, because its answer is a 2026 figure this brief must not invent. After the
fact-check report lands, the implementer appends a two-sentence `reference_answer` stating (a) the
verified 2026 overall limit on annual additions to a defined-contribution plan and (b) that it counts
your deferrals, employer contributions and after-tax contributions together, using the IRS source's
own figure. It must be byte-identical to C3's `## Key numbers (2026)` line and to the `verified` row
in `factcheck-the-mega-backdoor-roth-step-by-step.md`. No other authored row may be edited.

**Why the near_miss row is where it is:** it points at the "crypto compensation" planted gap while
sitting beside a tender-offer article full of liquidity-event language — high similarity, no answer.

## Steps (TDD)

- [ ] **RED — test-author, 1/2.** In `apps/api/tests/test_seed.py`, bump the corpus counts:

```python
_EXPECTED_SEED_FILE_COUNT = 33
_EXPECTED_PUBLISHED_COUNT = 29
_EXPECTED_DRAFT_COUNT = 4
```

  add batch C's four entries to `_WAVE1_ARTICLES` (keeping batches A and B):

```python
    "concentrated-employer-stock-and-our-10-rule": (
        "Concentrated Employer Stock and Our 10% Rule",
        frozenset({"our-firm", "investing-basics", "equity-compensation"}),
    ),
    "tender-offers-and-lock-up-periods": (
        "Tender Offers and Lock-Up Periods",
        frozenset({"equity-compensation", "tax-planning"}),
    ),
    "the-mega-backdoor-roth-step-by-step": (
        "The Mega-Backdoor Roth, Step by Step",
        frozenset({"retirement", "tax-planning"}),
    ),
    "our-rebalancing-policy-and-the-20-drawdown-rule": (
        "Our Rebalancing Policy and the 20% Drawdown Rule",
        frozenset({"our-firm", "investing-basics"}),
    ),
```

  and update the class-count totals (batch C adds 6 answerable + 2 multi_source + 1 near_miss +
  1 threshold + 1 stale_number):

```python
_EXPECTED_CLASS_COUNTS = {
    "answerable": 35,
    "multi_source": 6,
    "near_miss": 3,
    "off_domain": 4,
    "threshold": 3,
    "stale_number": 3,
}
_EXPECTED_QUESTION_TOTAL = 54
```

- [ ] **RED — test-author, 2/2. Run RED and record the evidence.** From the repo root, exporting
      only `TEST_DATABASE_URL`:

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
[ -n "$TEST_DATABASE_URL" ] && echo "TEST_DATABASE_URL: set"
cd apps/api && uv run pytest tests/test_seed.py -q
```

  Expected RED: the file-count pin fails (29 ≠ 33), the published-count pin fails (25 ≠ 29),
  `_wave1_records()` asserts batch C's four files are missing, and the class-count pin fails
  (54 expected vs 43 present). Paste those failure lines.

- [ ] **RED commit:** `git commit -m "test(api): pin wave-1 batch C corpus shape + eval class counts (p9 t12)"`

- [ ] **GREEN — drafter (Sonnet), 1/3.** Write the four articles per their briefs and the shape
      contract. Two hard constraints for this batch: C4 must not restate the phase-4 draft
      `rebalancing-your-portfolio-basics.md` (it is the firm's *policy*, not the mechanics), and
      neither C1 nor C4 may explain any hedging or options strategy beyond naming it as out of scope.

- [ ] **GREEN — fact-check agent (Sonnet, a DIFFERENT agent), 2/3.** WebFetch every primary source
      named in each brief, then write
      `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md`:

```markdown
# Fact-check — <slug>

Fetched <date>. Sources are primary only (irs.gov / sec.gov / ecfr.gov / uscode.house.gov).

| # | Claim (verbatim from the article) | Source + URL fetched | Source's own words | Verdict |
|---|---|---|---|---|
| 1 | ... | 17 CFR 240.10b5-1(c) — https://... | "..." | verified |
| 2 | ... | — | — | unverifiable |

## Unverifiable claims (each must be removed or reduced to the rule before the article ships)
- ...

## Firm-policy lines skipped (fictional, per the brief)
- ...
```

  One row per number **and** per stated rule. Any `unverifiable` row fails the article: hand it back,
  the drafter removes the number (keeping the rule), re-check. Repeat until clean. Two specifics for
  this batch: the 10b5-1 cooling-off figures must come from the rule text or Release 33-11138, not
  from a law-firm summary; and C3's limits must name the IRS Notice behind the 2026 figures.

- [ ] **GREEN — drafter, 3/3.** Append the comment line and the 11 eval rows verbatim, then write the
      `stale_number` row's `reference_answer` from the verified §415(c) figure.

- [ ] **Run GREEN (pins):**

```bash
cd apps/api && uv run pytest tests/test_seed.py tests/test_eval_questions_v2.py -q
```

  All pins green, including the pre-existing DB pin
  `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus`.

- [ ] **GREEN — real seed + harness run on a scratch DB** (evidence for the report):

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
export OPENAI_API_KEY="$(grep -m1 '^OPENAI_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n')"
export SCRATCH_DB=advisordesk_p9wave1c
export DATABASE_URL="${TEST_DATABASE_URL%/*}/$SCRATCH_DB"   # db-name substitution only
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY: set"
docker exec advisordesk-test-db psql -U postgres -c "DROP DATABASE IF EXISTS $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -c "CREATE DATABASE $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -d "$SCRATCH_DB" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed
uv run python -m app.eval.groundedness --label wave1-c --no-persist \
  | tee ../../.superpowers/sdd/phase-9-eval-data-loop/task-12-harness-capture.txt
```

  Expected seed line: 33 created, 29 published. Paste into the implementer report: the seed line, the
  **per-class table**, the summary line, the failure-cause distribution, and the
  `unresolved expected_chunks refs` count (must be 0). Note any class that moved against task 11's
  capture — in particular whether the three firm pages have started competing with each other in
  retrieval.

- [ ] **Gates:** `pnpm gates:api`.

- [ ] **GREEN commit:**
      `git commit -m "feat(seed): wave-1 batch C — concentration, tender offers, mega-backdoor Roth, rebalancing (p9 t12)"`

- [ ] **Opus batch review** (reviewer ≠ drafter ≠ fact-checker): the four articles against their
      briefs and the shape contract, the four fact-check reports (every number traced to a fetched
      URL), the 11 YAML rows against the authored block, the harness capture.

## Verify

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
cd apps/api && uv run pytest tests/test_seed.py tests/test_eval_questions_v2.py -q
pnpm gates:api
git diff --stat main -- ../../seed/sample_content   # 12 files added (batches A-C), 0 modified
```

## Acceptance

- Four new files at the pinned paths with the pinned titles, tags and `status: published`; batches A
  and B and the 21 basics are untouched.
- Every article matches the shape contract: H2-only, 4–6 question sections of 150–350 tokens,
  `## Key numbers (2026)` then `## Sources` last, `_Current as of 2026-09_` closing Key numbers, the
  verbatim footer last.
- **Every number in every article has a `verified` line in that article's fact-check report naming
  the fetched primary-source URL and quoting the source**, including the 10b5-1 cooling-off period
  from the rule text and the IRS Notice behind C3's 2026 limits. No `unverifiable` rows remain.
- The firm pages' fictional figures are mutually consistent with batches A and B and absent from
  `## Sources`; C4 does not duplicate `rebalancing-your-portfolio-basics.md`.
- No article states a rule or number for any of the five planted gaps — in particular nothing about
  crypto compensation — and no hedging/options mechanics appear anywhere.
- `seed/eval_questions.yaml` ends with the comment line and the 11 rows exactly as authored, plus the
  one `reference_answer` added to the `stale_number` row.
- Class counts are `{answerable: 35, multi_source: 6, near_miss: 3, off_domain: 4, threshold: 3,
  stale_number: 3}`, total 54 rows.
- The DB resolver pin passes; a real seed on a scratch DB reports 33 created / 29 published; the
  `--label wave1-c --no-persist` run prints a per-class table with 0 unresolved refs.
- Nothing was published to prod.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-12-test-author.md`
- Implementer (drafter): `.superpowers/sdd/phase-9-eval-data-loop/reports/task-12-implementer.md`
- Fact-check: `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md` (four files)
- Reviewer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-12-review.md`
