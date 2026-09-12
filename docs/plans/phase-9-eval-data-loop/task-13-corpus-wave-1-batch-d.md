---
id: p9-t13
phase: phase-9-eval-data-loop
depends_on: [p9-t12]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 13 — Corpus wave 1, batch D: donating appreciated stock & DAFs · leaving your employer · wash sales across RSU/ESPP lots · what we do not do

## Goal

The last four wave-1 articles and their 11 eval questions: giving shares instead of cash, the exit
(unvested equity, the option clock, the old 401(k), deferred comp), wash sales created by your own
vesting schedule, and the firm's "what we do not do" page. This batch carries the "401(k) loans
against employer stock" planted gap as its near-miss, and its firm page is the one that deliberately
sits next to two planted gaps without answering them.

Same four-agent content pipeline as batches A–C (DESIGN §C3): test-author (pins) → drafter (Sonnet) →
fact-check agent (Sonnet, WebFetch, a different agent) → Opus batch review. Every number is verified
against a named primary source or it does not ship. **No prod publish** (task 18).

**Depends on task 12** because all four batches edit the same two files
(`seed/eval_questions.yaml`, `apps/api/tests/test_seed.py`) and because batch D's `multi_source` rows
cite batch-B slugs.

**No application code changes.** The only Python file this task touches is `apps/api/tests/test_seed.py`.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/FIRM-FACTS.md` — the fictional firm's fee schedule,
  policies and voice (controller ruling 2026-09-12): every `[FIRM POLICY]` value in this batch
  comes from THAT file verbatim — never invent a figure, never contradict it.
- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §C1 (article shape), §C2 (personas, article list, the
  five planted gaps), §C3 (authoring pipeline), §B2 (v2 eval keys, the six classes).
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` — "Global Constraints".
- `apps/api/tests/test_seed.py` — **all of it, at its post-task-12 state**: `_WAVE1_ARTICLES` (twelve
  entries), `_WAVE1_TAGS`/`_ALLOWED_TAGS`, `_wave1_records`, `_h2_sections`, the token-band /
  heading / class-count pins, and the pre-existing DB pin
  `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus`.
- `seed/eval_questions.yaml` — the 54 committed rows; this task appends 11 more and changes nothing
  above them.
- `seed/sample_content/isos-and-nsos-how-each-one-is-taxed.md` and
  `seed/sample_content/onboarding-with-us-and-what-to-bring.md` — the files batch D's multi_source
  rows cite.
- `seed/sample_content/how-we-work-and-what-we-charge.md` — the firm voice and the fictional figures
  D4 must stay consistent with (especially "who we are not a fit for", which D4 expands).
- `seed/sample_content/tax-loss-harvesting-basics.md` — the phase-4 article on harvesting mechanics.
  D3 is the *equity-lot* case and must not restate it.
- `apps/api/app/rag/chunking.py` — `_HEADING_RE`, `count_tokens`, the 400+50 budget.
- `apps/api/app/services/content.py` lines 26–32 — `_slugify`.
- `apps/api/app/eval/questions.py` — `load_questions` validation and `resolve_expected_chunks`.

Do **not** read task 14.

## Files

**Create (content)**
- `seed/sample_content/donating-appreciated-stock-and-using-a-daf.md`
- `seed/sample_content/leaving-your-employer-with-equity-on-the-table.md`
- `seed/sample_content/wash-sales-across-rsu-and-espp-lots.md`
- `seed/sample_content/what-we-do-not-do-and-why.md`

**Create (fact-check reports, gitignored scratch area)**
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-donating-appreciated-stock-and-using-a-daf.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-leaving-your-employer-with-equity-on-the-table.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-wash-sales-across-rsu-and-espp-lots.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-what-we-do-not-do-and-why.md`

**Modify**
- `seed/eval_questions.yaml` (append the 11 rows below, verbatim)
- `apps/api/tests/test_seed.py` (the edits in Steps RED)

**Do not touch:** the 33 existing `seed/sample_content/*.md` files, any file under `apps/api/app/`,
`seed/agent_tasks.yaml`, `seed/judge_labels.yaml`, prod.

## Interfaces

| Artifact | Consumer |
|---|---|
| four published seed articles — wave 1 complete at 16 | task 14 (persona questions + the final class balance), task 18 (prod publish + replay) |
| 11 eval rows incl. 1 near_miss at the "401(k) loans against employer stock" planted gap | task 14's class balance; task 15's weak-query demo |
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
4. **Numbers are earned.** A number appears only if the fact-check report has a `verified` line for it
   naming the fetched URL and quoting the source. Otherwise write **the rule, not the number**.
   Unverifiable claim ⇒ the article FAILS and goes back to the drafter.
5. **Fictional firm policy** lines are marked `[FIRM POLICY — fictional, skip fact-check]`; in the
   article they read as the firm's own policy and never appear under `## Sources`. D4's statements
   about what the firm will not do must agree with `how-we-work-and-what-we-charge.md`.
6. **Planted gaps stay unwritten:** no rule and no number for non-US employees' equity, crypto
   compensation, stock options in a divorce, 401(k) loans against employer stock, or QSBS (§1202).
   **D4 is the sharpest case in the corpus:** it may say the firm does not advise on crypto, private
   deals or options strategies, and it may say where to go instead — it must not state how any of
   them is taxed, and it must not mention 401(k) loans or QSBS at all.
7. **Voice:** one firm voice, second person to the client. D4 speaks as "we"; D1–D3 are explainers
   that name the firm at most once.
8. `_Current as of 2026-09_` closes the Key numbers section; the verbatim footer is the last non-blank
   line (em dash U+2014).

---

## Article brief D1 — Donating Appreciated Stock and Using a DAF

- **Title (exact):** `Donating Appreciated Stock and Using a DAF`
- **Filename:** `seed/sample_content/donating-appreciated-stock-and-using-a-daf.md`
- **Tags:** `tax-planning`, `equity-compensation` · **Status:** `published`
- **Persona:** Marcus — gives to charity every year, holds low-basis employer stock, is unwinding a
  concentrated position.
- **Decision it serves:** give shares or cash, and whether to route a large gift through a
  donor-advised fund.

**H2 outline (verbatim headings, in this order):**

1. `## Why donate shares instead of cash?` — giving long-term appreciated shares deducts fair market
   value without realizing the gain; the charity receives the whole position; selling first means the
   gain is yours.
2. `## How much of my income can I deduct?` — the AGI percentage limit for appreciated capital-gain
   property given to a public charity, the different limit for cash, and the carryforward period.
   Verified figures only.
3. `## What is a donor-advised fund and when does it help?` — an account at a sponsoring charity: the
   deduction lands in the year of the contribution while grants go out later; why that pairs with a
   single high-income year (a vest, an IPO, a tender offer).
4. `## Can I donate shares I just received from a vest?` — shares held a year or less are short-term
   property and the deduction is limited to basis; for newly vested RSU shares basis is close to
   today's price, so little is lost but little is gained — the saving comes from donating shares held
   more than a year.
5. `## What do I need to substantiate the gift?` — the written acknowledgement, Form 8283 above the
   statutory threshold, and the appraisal rule for non-publicly-traded stock (with the exception for
   publicly traded securities). Verified thresholds only.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the AGI limit on gifts of appreciated capital-gain property to public charities, and the limit for cash gifts | IRS Publication 526, "Limits on Deductions" | `[STATUTORY]` |
| the carryforward period for an excess contribution | IRS Pub 526 | `[STATUTORY]` |
| the deduction rule for property held one year or less | IRS Pub 526, "Giving Property That Has Increased in Value" | rule + the holding period |
| the contribution threshold above which Form 8283 is required, and the threshold above which a qualified appraisal is required (plus the publicly-traded-securities exception) | Instructions for Form 8283 + IRS Publication 561 | `[STATUTORY]` |
| the 2026 standard deduction amounts (the itemizing hurdle a gift has to clear) | the IRS newsroom release "IRS provides tax inflation adjustments for tax year 2026" **and** the revenue procedure it links — record the Rev. Proc. number | `[ANNUAL]` |

**`## Sources`:** IRS Pub 526 · IRS Pub 561 · Instructions for Form 8283 · the IRS 2026
inflation-adjustment release and its revenue procedure.

---

## Article brief D2 — Leaving Your Employer With Equity on the Table

- **Title (exact):** `Leaving Your Employer With Equity on the Table`
- **Filename:** `seed/sample_content/leaving-your-employer-with-equity-on-the-table.md`
- **Tags:** `equity-compensation`, `retirement` · **Status:** `published`
- **Persona:** Marcus — resigning in a few weeks, with unvested RSUs, vested options, a large 401(k)
  and a deferred-comp election.
- **Decision it serves:** what to do, and in what order, in the weeks either side of a last day.

**H2 outline (verbatim headings, in this order):**

1. `## What happens to my unvested equity when I resign?` — unvested RSUs and options are normally
   forfeited on the last day; what to check in the grant (acceleration, retirement provisions,
   garden leave); that a vest date days after departure is usually lost.
2. `## How long do I have to exercise my vested options?` — the post-termination exercise window is a
   plan term; separately, an ISO exercised after the statutory post-termination period stops being an
   ISO and is taxed as an NSO. Verified periods only.
3. `## What should I do with my old 401(k)?` — leave it, roll it to the new plan, or roll it to an
   IRA; the direct-rollover mechanic versus the indirect rollover's deadline and mandatory
   withholding; the separation-from-service exception to the early-distribution penalty. Verified
   figures only. **Do not mention plan loans** (planted gap).
4. `## What happens to my ESPP and my last vest?` — the offering period ends at termination and
   accumulated payroll deductions are refunded; a final vest still runs through payroll; the ESPP
   holding periods keep running on shares you already own (pointer to batch A, no restatement).
5. `## What about deferred comp and my final paycheck?` — nonqualified deferred compensation pays out
   on the schedule already elected, not when you ask; §409A is why the election cannot be changed at
   the exit; accrued PTO and a final bonus are supplemental wages.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the post-termination period within which an ISO exercise still qualifies as an ISO exercise | IRC §422(a)(2) | `[STATUTORY]` |
| the indirect-rollover deadline and the mandatory withholding rate on an eligible rollover distribution paid to you | IRS Publication 575, "Rollovers" (and IRC §3405(c)) | `[STATUTORY]` |
| the age at/after which separation from service avoids the additional tax on an early plan distribution, and the additional-tax rate itself | IRS Pub 575, "Tax on Early Distributions" | `[STATUTORY]` |
| the 2026 elective deferral limit that applies across two employers in one calendar year | the IRS newsroom release announcing 2026 retirement-plan limits and the Notice it links | `[ANNUAL]` |
| that a §409A deferral election cannot be accelerated or changed at separation | Treas. Reg. §1.409A-3 (ecfr.gov) | rule, no number |

**`## Sources`:** IRS Pub 575 · IRS Pub 525 · IRC §422 · Treas. Reg. §1.409A-3 · the IRS 2026
retirement-plan limits release and its Notice.

---

## Article brief D3 — Wash Sales Across RSU and ESPP Lots

- **Title (exact):** `Wash Sales Across RSU and ESPP Lots`
- **Filename:** `seed/sample_content/wash-sales-across-rsu-and-espp-lots.md`
- **Tags:** `tax-planning`, `equity-compensation` · **Status:** `published`
- **Persona:** Sam and Marcus — anyone harvesting a loss on company stock while a vest or an ESPP
  purchase is scheduled.
- **Decision it serves:** when a loss sale is safe, given a vesting calendar nobody controls.

**H2 outline (verbatim headings, in this order):**

1. `## What is a wash sale, in plain terms?` — a loss sale plus an acquisition of substantially
   identical stock inside the statutory window; the loss is disallowed now and added to the
   replacement lot's basis, not lost forever. Verified window only.
2. `## How can my own vesting schedule cause a wash sale?` — shares delivered by a vest are an
   acquisition; a vest inside the window on either side of the loss sale disallows the loss; the
   practical fix is choosing the sale date around the vest calendar.
3. `## Does my ESPP purchase count as a replacement buy?` — yes, a purchase is a purchase; the
   purchase date is fixed by the offering period, so the lever is the timing of the loss sale;
   dividend reinvestment is the third silent trigger.
4. `## How do I harvest a loss on company stock without a wash sale?` — sequencing against vest and
   purchase dates, turning off reinvestment, and not buying a substantially identical position in
   another account (including an IRA, where the loss is permanently lost).
5. `## What does my broker report, and what do I have to fix?` — the 1099-B wash-sale adjustment,
   that brokers apply the rule per account while the law applies to you, and which corrections land
   on Form 8949.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the number of days before and after a loss sale in which a replacement purchase triggers the rule (and the total window) | IRS Publication 550, "Wash Sales" (and IRC §1091) | `[STATUTORY]` |
| that the disallowed loss is added to the basis of the replacement shares | IRS Pub 550, "Wash Sales" | rule, no number |
| the annual limit on net capital loss deductible against ordinary income (and the married-filing-separately figure), plus the carryforward | IRS Pub 550, "Capital Losses" (and IRC §1211(b)) | `[STATUTORY]` |
| that a purchase in an IRA permanently disallows the loss | IRS Revenue Ruling 2008-5 (irs.gov/irb) | rule, no number |
| where a wash-sale adjustment is reported | Instructions for Form 8949 | rule, no number |

**`## Sources`:** IRS Pub 550 · IRC §1091 · IRC §1211 · Rev. Rul. 2008-5 · Instructions for Form 8949.

---

## Article brief D4 — What We Do Not Do, and Why

- **Title (exact):** `What We Do Not Do, and Why`
- **Filename:** `seed/sample_content/what-we-do-not-do-and-why.md`
- **Tags:** `our-firm` · **Status:** `published`
- **Persona:** all three; the page that sets expectations before a prospect asks for the wrong thing.
- **Decision it serves:** whether the firm is the right provider for a given question, and who to
  call when it is not.

**H2 outline (verbatim headings, in this order):**

1. `## Do you pick individual stocks or time the market?` — no; the policy and the reason, in the
   firm's voice. `[FIRM POLICY — fictional, skip fact-check]`
2. `## Do you sell insurance or annuities?` — no; fee-only means no commissions, and insurance needs
   are analysed and then referred out. `[FIRM POLICY]` (the fee-only definition itself is sourced)
3. `## Will you prepare my tax return or give me legal advice?` — no; the firm plans the tax
   consequences and coordinates with your CPA and attorney, who own the filing and the documents.
   `[FIRM POLICY]`
4. `## Do you advise on crypto, private deals, or options strategies?` — no. Name them, say the firm
   will not advise on them and will not be paid to look at them, and stop. **No tax rule and no
   number for any of them** — this section is deliberately adjacent to a planted gap.
5. `## Who should I call instead?` — the referral map: CPA, estate attorney, insurance broker,
   equity-plan administrator; and that the firm makes referrals without compensation.
   `[FIRM POLICY]`

**Key numbers (2026) — items:**

| Item | Source | Note |
|---|---|---|
| referral policy, analysis-without-sale policy, the fee already published on the fees page | none | `[FIRM POLICY — fictional, skip fact-check]` — identical figures to `how-we-work-and-what-we-charge.md` |
| the definition of "fee-only" compensation | CFP Board's compensation-disclosure definition (cfp.net) | rule, no number |
| that an investment adviser owes a fiduciary duty of care and loyalty, and must disclose material conflicts | SEC "Commission Interpretation Regarding Standard of Conduct for Investment Advisers" (Release IA-5248) | rule, no number |
| that the services and compensation an adviser offers are disclosed in Form ADV Part 2A | SEC Form ADV Part 2A instructions (Items 4 and 5) | rule, no number |

**`## Sources`:** CFP Board fee-only definition · SEC IA-5248 · SEC Form ADV Part 2A instructions.
The fictional policies are **not** sourced.

---

## Eval questions — append verbatim to `seed/eval_questions.yaml`

Append after batch C's rows, preceded by this comment line:

```yaml
# --- phase-9 wave 1, batch D (task 13): donating stock + DAF · leaving · wash sales · what we do not do ---
```

Per article (DESIGN §C2: "every article ships with its 2–4 eval questions"): rows 1–3 → **D1**,
rows 4–6 → **D2** (row 5 is D2's planted-gap near-miss, authored with it but citing nothing),
rows 7–9 → **D3**, rows 10–11 → **D4**. Classes within the batch: 6 `answerable`, 2 `multi_source`,
1 `near_miss`, 1 `threshold`, 1 `stale_number`.

Then exactly these 11 rows, in this order, unedited:

```yaml
- question: "Why is donating appreciated company stock better than donating cash?"
  expected_slugs: ["donating-appreciated-stock-and-using-a-daf"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks: ["donating-appreciated-stock-and-using-a-daf#why-donate-shares-instead-of-cash"]
  reference_answer: >-
    Giving shares you have held more than a year lets you deduct their full fair market value
    without ever realizing the capital gain, so the charity receives the whole position. If you sell
    first and donate the proceeds, the gain is yours to pay tax on.

- question: "Can I donate shares I just received from an RSU vest?"
  expected_slugs: ["donating-appreciated-stock-and-using-a-daf"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks:
    - "donating-appreciated-stock-and-using-a-daf#can-i-donate-shares-i-just-received-from-a-vest"
  reference_answer: >-
    You can give them away immediately, but shares held a year or less are short-term property, so
    the deduction is limited to your basis. For newly vested RSU shares that basis is close to
    today's price, so little is lost — the tax saving comes from giving shares held more than a year.

- question: "How much of my income can I deduct for a gift of appreciated stock, and what is this year's standard deduction?"
  expected_slugs: ["donating-appreciated-stock-and-using-a-daf"]
  answerable: true
  class: stale_number
  persona: "Marcus"
  expected_chunks: ["donating-appreciated-stock-and-using-a-daf#key-numbers-2026"]

- question: "I am resigning next month — what happens to my unvested RSUs and my vested options?"
  expected_slugs: ["leaving-your-employer-with-equity-on-the-table"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks:
    - "leaving-your-employer-with-equity-on-the-table#what-happens-to-my-unvested-equity-when-i-resign"
    - "leaving-your-employer-with-equity-on-the-table#how-long-do-i-have-to-exercise-my-vested-options"
  reference_answer: >-
    Unvested RSUs and options are normally forfeited on your last day unless your grant says
    otherwise. Vested options stay exercisable only for the post-termination window in the plan, and
    an incentive stock option exercised after the statutory post-termination period is taxed as a
    nonqualified option instead.

- question: "Can I borrow from my 401(k) when the balance is mostly employer stock?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Marcus"

- question: "If I leave before my ISO shares are long-term, what does that cost me in tax?"
  expected_slugs:
    - "leaving-your-employer-with-equity-on-the-table"
    - "isos-and-nsos-how-each-one-is-taxed"
  answerable: true
  class: multi_source
  persona: "Marcus"
  expected_chunks:
    - "leaving-your-employer-with-equity-on-the-table#how-long-do-i-have-to-exercise-my-vested-options"
    - "isos-and-nsos-how-each-one-is-taxed#how-long-do-i-have-to-hold-iso-shares-for-the-best-tax-treatment"
  reference_answer: >-
    ISO treatment needs the shares held past both statutory holding periods; selling earlier is a
    disqualifying disposition and the spread becomes ordinary income. Leaving also starts the
    statutory post-termination clock, after which an exercise no longer qualifies as an ISO exercise
    at all.

- question: "Can an RSU vest two weeks after I sell at a loss create a wash sale?"
  expected_slugs: ["wash-sales-across-rsu-and-espp-lots"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks:
    - "wash-sales-across-rsu-and-espp-lots#how-can-my-own-vesting-schedule-cause-a-wash-sale"
  reference_answer: >-
    Yes. Shares delivered by a vest are an acquisition of the same stock, so a vest inside the
    statutory window on either side of your loss sale disallows that loss for now. The disallowed
    amount is added to the basis of the newly vested shares.

- question: "Does my ESPP purchase count as buying replacement shares?"
  expected_slugs: ["wash-sales-across-rsu-and-espp-lots"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks:
    - "wash-sales-across-rsu-and-espp-lots#does-my-espp-purchase-count-as-a-replacement-buy"
  reference_answer: >-
    Yes — an ESPP purchase is a purchase of the same stock, so it can trigger the wash-sale rule
    against a loss taken within the window on either side. Because the purchase date is fixed by the
    offering period, the lever you control is the timing of the loss sale.

- question: "I sold company shares for less than I paid and my broker's form says the loss was not allowed. Why?"
  expected_slugs: ["wash-sales-across-rsu-and-espp-lots"]
  answerable: true
  class: threshold
  persona: "Marcus"
  expected_chunks:
    - "wash-sales-across-rsu-and-espp-lots#what-does-my-broker-report-and-what-do-i-have-to-fix"
  reference_answer: >-
    Your 1099-B is flagging a wash sale: you acquired the same stock within the statutory window
    before or after the sale, so the loss is disallowed for now and added to the new lot's basis.
    Brokers apply the rule per account, so a purchase elsewhere can make your return differ from
    the form.

- question: "Is there anything you will not help me with?"
  expected_slugs: ["what-we-do-not-do-and-why"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks:
    - "what-we-do-not-do-and-why#do-you-pick-individual-stocks-or-time-the-market"
    - "what-we-do-not-do-and-why#will-you-prepare-my-tax-return-or-give-me-legal-advice"
  reference_answer: >-
    Queen City does not pick individual stocks or time the market, does not sell insurance or
    annuities, and does not prepare tax returns or give legal advice. It plans around those things
    and refers you to a CPA or an attorney when the work belongs to one.

- question: "Can you do my tax return and handle the paperwork for my ISO exercise?"
  expected_slugs: ["what-we-do-not-do-and-why", "onboarding-with-us-and-what-to-bring"]
  answerable: true
  class: multi_source
  persona: "Marcus"
  expected_chunks:
    - "what-we-do-not-do-and-why#will-you-prepare-my-tax-return-or-give-me-legal-advice"
    - "onboarding-with-us-and-what-to-bring#what-do-you-need-from-my-equity-paperwork"
  reference_answer: >-
    The firm does not prepare returns; it works alongside your CPA and gives them the numbers they
    need. It does collect and keep your equity paperwork — grant agreements, the plan document,
    exercise records and Forms 3921 and 3922 — so an exercise is planned and documented before it
    happens.
```

**The one row the implementer completes:** the `stale_number` row ships from this brief *without*
`reference_answer`, because its answer is a 2026 figure this brief must not invent. After the
fact-check report lands, the implementer appends a two-sentence `reference_answer` stating (a) the
verified AGI percentage limit for gifts of appreciated capital-gain property to a public charity and
(b) the verified 2026 standard deduction for married filing jointly and for a single filer, using the
IRS sources' own figures. They must be byte-identical to D1's `## Key numbers (2026)` lines and to the
`verified` rows in `factcheck-donating-appreciated-stock-and-using-a-daf.md`. No other authored row
may be edited.

**Why the near_miss row is where it is:** it points at the "401(k) loans against employer stock"
planted gap while sitting beside D2's old-401(k) section and C1's concentration page — maximum
retrieval similarity, no answer anywhere in the corpus. D2 is explicitly forbidden from mentioning
plan loans for exactly this reason.

## Steps (TDD)

- [ ] **RED — test-author, 1/2.** In `apps/api/tests/test_seed.py`, bump the corpus counts to the
      wave-1 complete state:

```python
_EXPECTED_SEED_FILE_COUNT = 37
_EXPECTED_PUBLISHED_COUNT = 33
_EXPECTED_DRAFT_COUNT = 4
```

  add batch D's four entries to `_WAVE1_ARTICLES` (keeping batches A–C, twelve entries, so the map
  holds all sixteen wave-1 articles):

```python
    "donating-appreciated-stock-and-using-a-daf": (
        "Donating Appreciated Stock and Using a DAF",
        frozenset({"tax-planning", "equity-compensation"}),
    ),
    "leaving-your-employer-with-equity-on-the-table": (
        "Leaving Your Employer With Equity on the Table",
        frozenset({"equity-compensation", "retirement"}),
    ),
    "wash-sales-across-rsu-and-espp-lots": (
        "Wash Sales Across RSU and ESPP Lots",
        frozenset({"tax-planning", "equity-compensation"}),
    ),
    "what-we-do-not-do-and-why": (
        "What We Do Not Do, and Why",
        frozenset({"our-firm"}),
    ),
```

  update the class-count totals (batch D adds 6 answerable + 2 multi_source + 1 near_miss +
  1 threshold + 1 stale_number):

```python
_EXPECTED_CLASS_COUNTS = {
    "answerable": 41,
    "multi_source": 8,
    "near_miss": 4,
    "off_domain": 4,
    "threshold": 4,
    "stale_number": 4,
}
_EXPECTED_QUESTION_TOTAL = 65
```

  and add the wave-1-complete pin (the inventory check the whole-branch review leans on):

```python
# DESIGN §C2's four firm pages, by slug. Pinned by slug rather than by the `our-firm` tag because
# `concentrated-employer-stock-and-our-10-rule` also carries that tag (it states a firm policy)
# while being one of the twelve equity/benefits explainers.
_WAVE1_FIRM_PAGES = {
    "how-we-work-and-what-we-charge",
    "onboarding-with-us-and-what-to-bring",
    "our-rebalancing-policy-and-the-20-drawdown-rule",
    "what-we-do-not-do-and-why",
}


def test_wave_1_is_complete_at_sixteen_articles() -> None:
    """DESIGN §C2: wave 1 is 12 equity/benefits explainers + 4 firm pages. The two "where you live"
    articles and the fundamentals upgrade are wave 2 — `north-carolina` stays out of the tag
    vocabulary until then."""
    assert len(_WAVE1_ARTICLES) == 16
    assert _WAVE1_FIRM_PAGES <= set(_WAVE1_ARTICLES), (
        f"missing firm pages: {sorted(_WAVE1_FIRM_PAGES - set(_WAVE1_ARTICLES))}"
    )
    assert len(set(_WAVE1_ARTICLES) - _WAVE1_FIRM_PAGES) == 12
    assert all("our-firm" in _WAVE1_ARTICLES[slug][1] for slug in _WAVE1_FIRM_PAGES)
    assert "north-carolina" not in _ALLOWED_TAGS
```

- [ ] **RED — test-author, 2/2. Run RED and record the evidence.** From the repo root, exporting only
      `TEST_DATABASE_URL`:

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
[ -n "$TEST_DATABASE_URL" ] && echo "TEST_DATABASE_URL: set"
cd apps/api && uv run pytest tests/test_seed.py -q
```

  Expected RED: the file-count pin fails (33 ≠ 37), the published-count pin fails (29 ≠ 33),
  `_wave1_records()` asserts batch D's four files are missing, and the class-count pin fails (65
  expected vs 54 present). `test_wave_1_is_complete_at_sixteen_articles` passes at RED (it reads the
  map, not the disk) — say so in the report.

- [ ] **RED commit:** `git commit -m "test(api): pin wave-1 batch D corpus shape + eval class counts (p9 t13)"`

- [ ] **GREEN — drafter (Sonnet), 1/3.** Write the four articles per their briefs and the shape
      contract. Three hard constraints for this batch: D2's 401(k) section must not mention plan
      loans; D3 must not restate `tax-loss-harvesting-basics.md`; D4 must name crypto, private deals
      and options strategies without explaining the tax of any of them.

- [ ] **GREEN — fact-check agent (Sonnet, a DIFFERENT agent), 2/3.** WebFetch every primary source
      named in each brief, then write
      `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md`:

```markdown
# Fact-check — <slug>

Fetched <date>. Sources are primary only (irs.gov / sec.gov / ecfr.gov / uscode.house.gov / cfp.net).

| # | Claim (verbatim from the article) | Source + URL fetched | Source's own words | Verdict |
|---|---|---|---|---|
| 1 | ... | IRS Pub 550, "Wash Sales" — https://... | "..." | verified |
| 2 | ... | — | — | unverifiable |

## Unverifiable claims (each must be removed or reduced to the rule before the article ships)
- ...

## Firm-policy lines skipped (fictional, per the brief)
- ...
```

  One row per number **and** per stated rule. Any `unverifiable` row fails the article: hand it back,
  the drafter removes the number (keeping the rule), re-check. Repeat until clean. Specifics for this
  batch: D1's standard-deduction figures and D2's deferral limit must each name the revenue procedure
  or Notice behind them, and the IRA wash-sale claim must cite Rev. Rul. 2008-5 itself.

- [ ] **GREEN — drafter, 3/3.** Append the comment line and the 11 eval rows verbatim, then write the
      `stale_number` row's `reference_answer` from the verified AGI limit and 2026 standard deduction.

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
export SCRATCH_DB=advisordesk_p9wave1d
export DATABASE_URL="${TEST_DATABASE_URL%/*}/$SCRATCH_DB"   # db-name substitution only
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY: set"
docker exec advisordesk-test-db psql -U postgres -c "DROP DATABASE IF EXISTS $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -c "CREATE DATABASE $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -d "$SCRATCH_DB" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed
uv run python -m app.eval.groundedness --label wave1-d --no-persist \
  | tee ../../.superpowers/sdd/phase-9-eval-data-loop/task-13-harness-capture.txt
```

  Expected seed line: 37 created, 33 published. Paste into the implementer report: the seed line, the
  **per-class table**, the summary line, the failure-cause distribution, and the
  `unresolved expected_chunks refs` count (must be 0). This is the first run over the complete wave-1
  corpus — record the near_miss rows' `top_similarity` values, because they are the numbers the
  near-miss demo beat depends on.

- [ ] **Gates:** `pnpm gates:api`.

- [ ] **GREEN commit:**
      `git commit -m "feat(seed): wave-1 batch D — donating stock, leaving, wash sales, what we do not do (p9 t13)"`

- [ ] **Opus batch review** (reviewer ≠ drafter ≠ fact-checker): the four articles against their
      briefs and the shape contract, the four fact-check reports (every number traced to a fetched
      URL), the 11 YAML rows against the authored block, the harness capture, **and** one whole-wave
      check: all 16 wave-1 articles use a consistent firm voice, the fictional firm figures agree
      across the four firm pages, and no article leaks a planted gap.

## Verify

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
cd apps/api && uv run pytest tests/test_seed.py tests/test_eval_questions_v2.py -q
pnpm gates:api
git diff --stat main -- ../../seed/sample_content   # 16 files added (wave 1 complete), 0 modified
```

## Acceptance

- Four new files at the pinned paths with the pinned titles, tags and `status: published`; batches
  A–C and the 21 basics are untouched. Wave 1 is complete at 16 articles (12 + 4 firm pages).
- Every article matches the shape contract: H2-only, 4–6 question sections of 150–350 tokens,
  `## Key numbers (2026)` then `## Sources` last, `_Current as of 2026-09_` closing Key numbers, the
  verbatim footer last.
- **Every number in every article has a `verified` line in that article's fact-check report naming
  the fetched primary-source URL and quoting the source**, including the revenue procedure / Notice
  behind D1's and D2's annual figures. No `unverifiable` rows remain.
- D2 never mentions 401(k) plan loans; D4 names crypto, private deals and options strategies without
  stating any tax rule or number for them; no article mentions QSBS.
- D4's firm statements and figures agree with `how-we-work-and-what-we-charge.md`; D3 does not
  duplicate `tax-loss-harvesting-basics.md`.
- `seed/eval_questions.yaml` ends with the comment line and the 11 rows exactly as authored, plus the
  one `reference_answer` added to the `stale_number` row.
- Class counts are `{answerable: 41, multi_source: 8, near_miss: 4, off_domain: 4, threshold: 4,
  stale_number: 4}`, total 65 rows — the remainder task 14 balances to 80.
- The DB resolver pin passes; a real seed on a scratch DB reports 37 created / 33 published; the
  `--label wave1-d --no-persist` run prints a per-class table with 0 unresolved refs and the
  near_miss rows' `top_similarity` values are recorded.
- Nothing was published to prod.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-13-test-author.md`
- Implementer (drafter): `.superpowers/sdd/phase-9-eval-data-loop/reports/task-13-implementer.md`
- Fact-check: `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md` (four files)
- Reviewer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-13-review.md`
