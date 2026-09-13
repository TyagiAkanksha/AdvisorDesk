---
id: p9-t10
phase: phase-9-eval-data-loop
depends_on: [p9-t04, p9-t05, p9-t09]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 10 — Corpus wave 1, batch A: RSUs at vest · double-trigger RSUs & IPOs · ESPP dispositions · how we work & fees

## Goal

The first four wave-1 articles land in `seed/sample_content/` with their 11 eval questions. These are
the four the talk's demo beats lean on hardest (Sam's first vest, Priya's IPO, Sam's ESPP window, and
"who are you and what do you charge"), so they are authored first and reviewed hardest.

This is a **content** task run as a four-agent pipeline (DESIGN §C3): test-author (pins) → drafter
(Sonnet) → fact-check agent (Sonnet, WebFetch, separate agent) → Opus batch review. Every number in
every article is verified against a named primary source or it does not ship. Nothing is published to
prod here — prod publish is task 18's owner-gated step.

**No application code changes.** The only Python file this task touches is `apps/api/tests/test_seed.py`.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/FIRM-FACTS.md` — the fictional firm's fee schedule,
  policies and voice (controller ruling 2026-09-12): every `[FIRM POLICY]` value in this batch
  comes from THAT file verbatim — never invent a figure, never contradict it.
- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §C1 (article shape: H2 = chunk = retrieval unit,
  150–350 tokens, Key numbers, Sources, `_Current as of 2026-09_`, new titles because seed is
  idempotent by title), §C2 (personas Sam/Priya/Marcus; the article list; the five planted gaps),
  §C3 (the authoring pipeline), §B2 (the v2 eval-question keys and the six classes).
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` — "Global Constraints" (content rules, commit
  gates, the `TEST_DATABASE_URL`-only env rule).
- `apps/api/tests/test_seed.py` — **all of it**. Every pin the new files must satisfy is there:
  frontmatter `title`/`tags`/`status`, the verbatim footer, `slug == filename stem`, the tag
  vocabulary, the file/published/draft count bands, the eval-YAML shape pins, and the DB pin
  `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus`.
- `seed/eval_questions.yaml` — the committed 21 rows (17 answerable + 4 unanswerable) and their YAML
  style; this task appends 11 rows and changes nothing above them.
- `seed/sample_content/hsa-triple-tax-advantage-basics.md` and
  `seed/sample_content/understanding-index-funds-basics.md` — the existing house voice, frontmatter
  block, heading style and footer placement. Wave-1 files add Key numbers / Sources / the
  `_Current as of` line, which these do not have.
- `apps/api/app/rag/chunking.py` — `_HEADING_RE` (line ~31: any ATX heading starts a chunk),
  `_split_sections`, and `count_tokens` (line ~67; `cl100k_base`). `chunk_markdown`'s budget is
  400 tokens + 50 overlap, which is why an authored section stops at 350.
- `apps/api/app/services/content.py` lines 26–32 — `_SLUG_INVALID_RE` / `_slugify`: every
  non-`[a-z0-9]` run becomes one `-`, then outer `-` are stripped. This is the rule that makes
  `filename == slugify(title)` and `slug#heading-slug` refs resolvable.
- `apps/api/app/eval/questions.py` — `load_questions` (the validation every appended row must pass:
  unknown keys rejected, `expected_chunks` must be `<slug>#<heading-slug>` **and** its slug must be
  in that row's `expected_slugs`, no duplicate question text) and `resolve_expected_chunks`.

Do **not** read the other batch files (11–13) or task 14 — they are independent.

## Files

**Create (content)**
- `seed/sample_content/what-happens-to-your-rsus-at-vest.md`
- `seed/sample_content/double-trigger-rsus-and-an-ipo.md`
- `seed/sample_content/espp-qualifying-and-disqualifying-dispositions.md`
- `seed/sample_content/how-we-work-and-what-we-charge.md`

**Create (fact-check reports, gitignored scratch area)**
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-what-happens-to-your-rsus-at-vest.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-double-trigger-rsus-and-an-ipo.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-espp-qualifying-and-disqualifying-dispositions.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-how-we-work-and-what-we-charge.md`

**Modify**
- `seed/eval_questions.yaml` (append the 11 rows below, verbatim, after the existing 21)
- `apps/api/tests/test_seed.py` (the pins in Steps RED)

**Do not touch:** the 21 existing `seed/sample_content/*.md` files, any file under `apps/api/app/`,
`seed/agent_tasks.yaml`, `seed/judge_labels.yaml`, prod.

## Interfaces

Nothing here is imported by code. What this task produces for later tasks:

| Artifact | Consumer |
|---|---|
| four published seed articles, 20 new chunks-worth of sections | tasks 11–13 (multi_source pairs), 14 (persona questions), 18 (prod publish + replay) |
| 11 eval rows incl. 1 near_miss at the "non-US employees" planted gap | task 14's class balance; task 15's weak-query demo |
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

1. **H2 only.** No `#` H1, no `###`+ anywhere. Every ATX heading is a chunk boundary
   (`chunking._HEADING_RE`), so an H3 would silently split a section and break an
   `expected_chunks` ref.
2. **Headings verbatim from the brief.** The eval rows below reference
   `slug#slugify(heading)`; a reworded heading breaks the DB resolver pin.
3. **Token band:** each question H2 section (heading line included) is 150–350 `cl100k` tokens
   (`app.rag.chunking.count_tokens`). `Key numbers (2026)` and `Sources` have no lower bound but
   must stay ≤ 350. The lead paragraph must also stay ≤ 350.
4. **Numbers are earned.** A number may appear in the article **only** if the fact-check report has
   a `verified` line for it naming the source URL and quoting the source's own words. Otherwise
   write **the rule, not the number** ("the flat supplemental-wage rate your employer applies",
   not "22%"). Unverifiable claim ⇒ the article FAILS and goes back to the drafter.
5. **Fictional firm policy** lines are marked in the brief `[FIRM POLICY — fictional, skip
   fact-check]`. In the article they must read as the firm's own policy ("Our policy is…", "We
   review…") so no reader mistakes them for law, and they must **not** appear under `## Sources`.
6. **Planted gaps stay unwritten.** Never explain, in any article, the tax treatment of: non-US
   employees' equity, crypto compensation, stock options in a divorce, 401(k) loans against
   employer stock, QSBS (§1202). A one-clause "this article does not cover X" boundary is allowed;
   a rule or a number for X is not. These are the live near-miss material (DESIGN §C2).
7. **Voice:** one firm voice, second person to the client, Queen City Wealth Planning named only in
   firm articles and in a single "what we'd do" sentence in an equity article. No advice imperatives
   beyond the firm's stated policies.
8. `_Current as of 2026-09_` is the last line of the Key numbers section; the footer line is the
   last non-blank line of the file, verbatim (em dash U+2014).

---

## Article brief A1 — What Happens to Your RSUs at Vest

- **Title (exact):** `What Happens to Your RSUs at Vest`
- **Filename:** `seed/sample_content/what-happens-to-your-rsus-at-vest.md`
- **Tags:** `equity-compensation`, `tax-planning` · **Status:** `published`
- **Persona:** Sam — new-grad engineer, first RSU tranche vesting, has never heard "supplemental
  withholding".
- **Decision it serves:** how much cash to set aside before April, and whether to sell at vest.

**H2 outline (verbatim headings, in this order):**

1. `## What happens when my RSUs vest?` — delivery of shares, full FMV at vest is ordinary
   compensation income on the W-2, payroll withholds (usually share withholding / "sell to cover").
2. `## Why was so little tax withheld on my vest?` — supplemental-wage withholding is a flat rate,
   not your marginal rate; the gap is the shortfall. State the rate only if verified.
3. `## Should I sell my shares at vest or hold them?` — basis resets to the vest value, so selling
   at vest is close to tax-neutral; holding is a concentration decision, not a tax decision.
4. `## How do I cover the shortfall before April?` — estimated payments or extra payroll
   withholding; the mechanism, and that the amount depends on your bracket.
5. `## What is my cost basis after a vest?` — basis = FMV at vest; holding period starts at vest;
   the common double-counting error when the 1099-B shows a zero or missing basis.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| flat withholding rate on supplemental wages up to $1,000,000, and the mandatory rate above it | IRS Publication 15 (Circular E), section 7 "Supplemental wages" | `[STATUTORY]` — quote Pub 15's own words |
| Social Security wage base for 2026 (withholding on a large vest stops above it) | SSA 2026 COLA fact sheet (ssa.gov press factsheets) | `[ANNUAL]` |
| Additional Medicare Tax rate and the wage threshold where it starts | IRS Pub 15, "Additional Medicare Tax withholding" | `[STATUTORY]` |
| holding period that makes a later gain long-term | IRS Topic No. 409, Capital Gains and Losses | `[STATUTORY]` — "more than one year" |
| that RSU income is reported as wages | IRS Publication 525, "Restricted Property" / RSU discussion | rule, no number |

**`## Sources`:** IRS Pub 15 · IRS Pub 525 · IRS Topic No. 409 · SSA 2026 COLA fact sheet. Primary
URLs only (irs.gov / ssa.gov), each one actually fetched by the fact-checker.

---

## Article brief A2 — Double-Trigger RSUs and an IPO

- **Title (exact):** `Double-Trigger RSUs and an IPO`
- **Filename:** `seed/sample_content/double-trigger-rsus-and-an-ipo.md`
- **Tags:** `equity-compensation`, `tax-planning` · **Status:** `published`
- **Persona:** Priya — senior IC at a pre-IPO company whose S-1 has just been filed.
- **Decision it serves:** what to expect (and set aside) at settlement, and how to plan around a
  lock-up she cannot control.

**H2 outline (verbatim headings, in this order):**

1. `## What does double-trigger vesting mean?` — two conditions (time + liquidity event); nothing is
   delivered and nothing is taxed until both are met; why private companies use it.
2. `## When do I owe tax if my company goes public?` — tax at settlement, value at settlement is
   ordinary wage income; settlement may be at the IPO, shortly after, or at lock-up expiry
   depending on the plan.
3. `## What is a sell-to-cover at IPO, and can I opt out?` — the mechanics of share withholding vs
   sell-to-cover; plans rarely give a choice; what lands in your brokerage account.
4. `## How does the lock-up period change my planning?` — a contractual restriction, not a tax rule;
   the tax is already fixed at settlement while the price is not; a plan for the day it lifts.
5. `## What if the liquidity event never comes?` — expiry of the liquidity condition, forfeiture,
   and the fact that unsettled RSUs are not taxed and cannot be 83(b)'d.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the flat supplemental-wage withholding rate, and the rate above $1,000,000 of supplemental wages | IRS Pub 15, section 7 | `[STATUTORY]` |
| that RSU income is taxed at settlement, not at grant (and that §83(b) is unavailable for an unfunded RSU promise) | IRS Pub 525, "Restricted Property" (and its §83 discussion) | rule, no number |
| holding period for long-term treatment after settlement | IRS Topic No. 409 | `[STATUTORY]` |
| Social Security wage base for 2026 | SSA 2026 COLA fact sheet | `[ANNUAL]` |

**`## Sources`:** IRS Pub 15 · IRS Pub 525 · IRS Topic No. 409 · SSA 2026 COLA fact sheet.

> Lock-up length is a contractual market convention, not a rule: say "typically about six months"
> only if the fact-checker verifies it against a primary source (e.g. an SEC investor bulletin);
> otherwise write "for a period set by the underwriting agreement".

---

## Article brief A3 — ESPP Qualifying and Disqualifying Dispositions

- **Title (exact):** `ESPP Qualifying and Disqualifying Dispositions`
- **Filename:** `seed/sample_content/espp-qualifying-and-disqualifying-dispositions.md`
- **Tags:** `equity-compensation`, `tax-planning` · **Status:** `published`
- **Persona:** Sam — first ESPP window, contributing through payroll, no idea what the holding
  periods do.
- **Decision it serves:** sell at purchase or hold for a qualifying disposition.

**H2 outline (verbatim headings, in this order):**

1. `## How does my ESPP purchase actually work?` — offering date, purchase date, payroll
   accumulation, the discount and the look-back; the §423 statutory limits.
2. `## What makes a sale qualifying or disqualifying?` — the two holding periods measured from two
   different dates; anything earlier is disqualifying.
3. `## How much of my ESPP gain is ordinary income?` — disqualifying: the purchase-date discount is
   ordinary income, the rest capital; qualifying: the lesser-of rule, remainder long-term.
4. `## Should I sell my ESPP shares right away?` — the trade-off between the tax saving from waiting
   and the added single-stock risk; what the firm's concentration policy implies.
5. `## Which tax forms will I get?` — Form 3922 from your employer, the 1099-B from the broker, and
   why the 1099-B basis is often wrong for ESPP lots.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the $25,000 per-calendar-year limit on ESPP stock accrual | IRC §423(b)(8) (uscode.house.gov or law.cornell.edu) | `[STATUTORY]` |
| the maximum discount a §423 plan may offer (purchase price floor as a % of FMV) | IRC §423(b)(6) + IRS Pub 525 "Employee stock purchase plan" | `[STATUTORY]` |
| the two holding periods for a qualifying disposition (from grant/offering date and from transfer/purchase date) | IRC §423(a)(1) + IRS Pub 525 | `[STATUTORY]` |
| when Form 3922 must be furnished to you | Instructions for Forms 3921 and 3922 | `[STATUTORY]` |

**`## Sources`:** IRS Pub 525 (ESPP section) · Instructions for Forms 3921 and 3922 · IRC §423.

---

## Article brief A4 — How We Work and What We Charge

- **Title (exact):** `How We Work and What We Charge`
- **Filename:** `seed/sample_content/how-we-work-and-what-we-charge.md`
- **Tags:** `our-firm` · **Status:** `published`
- **Persona:** all three (this is the page every prospect reads first).
- **Decision it serves:** hire the firm or not.

**H2 outline (verbatim headings, in this order):**

1. `## How does Queen City Wealth Planning get paid?` — fee-only; the two engagement shapes (ongoing
   advisory fee, flat-fee planning project); no commissions, no referral fees, no asset-based
   kickbacks. `[FIRM POLICY — fictional, skip fact-check]` for every amount.
2. `## What does your fee cover?` — planning, equity-comp decisions, tax coordination with your CPA,
   the concentration and rebalancing reviews, unlimited questions between meetings. `[FIRM POLICY]`
3. `## Who do you work with, and who are you not a fit for?` — tech employees with equity comp;
   explicitly not a fit for day traders, crypto-first portfolios, or clients wanting stock picks.
   `[FIRM POLICY]`
4. `## What does fee-only and fiduciary mean in practice?` — the only section with real outside
   rules: the fiduciary duty an SEC-registered investment adviser owes, and what "fee-only" means as
   a defined term. Verified, sourced.
5. `## How often will we meet?` — cadence and what each meeting covers. `[FIRM POLICY]`

**Key numbers (2026) — items:**

| Item | Source | Note |
|---|---|---|
| ongoing advisory fee, flat-fee planning price, minimum relationship size, review cadence | none | `[FIRM POLICY — fictional, skip fact-check]` — take every figure from `FIRM-FACTS.md` verbatim (never invent) so all firm pages agree |
| that an investment adviser owes its clients a fiduciary duty of care and loyalty | SEC "Commission Interpretation Regarding Standard of Conduct for Investment Advisers" (Release IA-5248) | rule, no number |
| that the firm's brochure (Form ADV Part 2A) must be delivered before or at the time of entering into an advisory contract | SEC Rule 204-3 / Form ADV Part 2A instructions (sec.gov) | rule, no number |
| the definition of "fee-only" compensation | CFP Board's compensation-disclosure definition (cfp.net) | rule, no number |

**`## Sources`:** SEC IA-5248 · SEC Form ADV Part 2A instructions / Rule 204-3 · CFP Board fee-only
definition. The fictional fee schedule is **not** sourced and must not be listed here.

---

## Eval questions — append verbatim to `seed/eval_questions.yaml`

Append after the existing 21 rows, preceded by this comment line:

```yaml
# --- phase-9 wave 1, batch A (task 10): RSU vest · double-trigger IPO · ESPP · firm fees ---
```

Per article (DESIGN §C2: "every article ships with its 2–4 eval questions"): rows 1–3 → **A1**,
rows 4–6 → **A2**, rows 7–9 → **A3** (row 8 is A3's planted-gap near-miss, authored with it but
citing nothing), rows 10–11 → **A4**. Classes within the batch: 6 `answerable`, 2 `multi_source`,
1 `near_miss`, 1 `threshold`, 1 `stale_number`.

Then exactly these 11 rows, in this order, unedited:

```yaml
- question: "My first RSU tranche vests next month — what actually happens on the vest date?"
  expected_slugs: ["what-happens-to-your-rsus-at-vest"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks: ["what-happens-to-your-rsus-at-vest#what-happens-when-my-rsus-vest"]
  reference_answer: >-
    On the vest date the shares are delivered to you and their full market value that day is
    ordinary compensation income reported on your W-2. Your employer withholds tax on that
    amount, most often by holding back some of the vesting shares.

- question: "Why was the tax withheld on my RSU vest less than what I actually owe?"
  expected_slugs: ["what-happens-to-your-rsus-at-vest"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks: ["what-happens-to-your-rsus-at-vest#why-was-so-little-tax-withheld-on-my-vest"]
  reference_answer: >-
    RSU income is withheld at the flat supplemental-wage rate rather than at your marginal rate,
    so if your marginal rate is higher the withholding covers only part of the bill. The
    difference is due with your return unless you pre-pay it.

- question: "What flat rate does my employer withhold on an RSU vest this year?"
  expected_slugs: ["what-happens-to-your-rsus-at-vest"]
  answerable: true
  class: stale_number
  persona: "Sam"
  expected_chunks: ["what-happens-to-your-rsus-at-vest#key-numbers-2026"]

- question: "What does double-trigger vesting actually mean for my RSUs?"
  expected_slugs: ["double-trigger-rsus-and-an-ipo"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks: ["double-trigger-rsus-and-an-ipo#what-does-double-trigger-vesting-mean"]
  reference_answer: >-
    Double-trigger RSUs need two conditions before you own shares: the time-based vesting
    condition and a liquidity event such as an IPO or acquisition. Until both are met nothing is
    delivered and nothing is taxed.

- question: "My company just filed to go public — when will I owe tax on my RSUs?"
  expected_slugs: ["double-trigger-rsus-and-an-ipo"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks: ["double-trigger-rsus-and-an-ipo#when-do-i-owe-tax-if-my-company-goes-public"]
  reference_answer: >-
    Tax is due when the shares actually settle, which for double-trigger RSUs is when the
    liquidity condition is met — at or shortly after the IPO, or at lock-up expiry if the plan
    says so. The value at settlement is ordinary wage income.

- question: "My RSUs settle at the IPO and then I am locked up for six months — how should I think about selling?"
  expected_slugs: ["double-trigger-rsus-and-an-ipo", "what-happens-to-your-rsus-at-vest"]
  answerable: true
  class: multi_source
  persona: "Priya"
  expected_chunks:
    - "double-trigger-rsus-and-an-ipo#how-does-the-lock-up-period-change-my-planning"
    - "what-happens-to-your-rsus-at-vest#should-i-sell-my-shares-at-vest-or-hold-them"
  reference_answer: >-
    You already paid ordinary income tax on the settlement value, so selling soon after the
    lock-up lifts usually creates little further gain or loss. Holding instead is a decision to
    keep a concentrated position, which is a risk question rather than a tax question.

- question: "How is my ESPP taxed if I sell the shares right after the purchase date?"
  expected_slugs: ["espp-qualifying-and-disqualifying-dispositions"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks:
    - "espp-qualifying-and-disqualifying-dispositions#what-makes-a-sale-qualifying-or-disqualifying"
    - "espp-qualifying-and-disqualifying-dispositions#how-much-of-my-espp-gain-is-ordinary-income"
  reference_answer: >-
    Selling that soon is a disqualifying disposition: the discount you received is ordinary income
    on your W-2 and anything above the purchase price is a short-term capital gain. No part of the
    sale gets long-term rates.

- question: "I am on our Berlin payroll — how is my ESPP purchase taxed in Germany?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Sam"

- question: "I have been buying company shares through payroll deductions. What changes for me once I have held them a while?"
  expected_slugs: ["espp-qualifying-and-disqualifying-dispositions"]
  answerable: true
  class: threshold
  persona: "Sam"
  expected_chunks:
    - "espp-qualifying-and-disqualifying-dispositions#what-makes-a-sale-qualifying-or-disqualifying"
  reference_answer: >-
    An ESPP sale is qualifying only once both statutory holding periods are met, measured from the
    offering date and from the purchase date; before that it is disqualifying. In a qualifying sale
    a smaller part of the gain is ordinary income and the rest is long-term capital gain.

- question: "How does Queen City Wealth Planning charge for its services?"
  expected_slugs: ["how-we-work-and-what-we-charge"]
  answerable: true
  class: answerable
  persona: "Marcus"
  expected_chunks: ["how-we-work-and-what-we-charge#how-does-queen-city-wealth-planning-get-paid"]
  reference_answer: >-
    Queen City Wealth Planning is fee-only: it is paid directly by its clients and takes no
    commissions or referral fees. Its published schedule sets out an ongoing advisory fee and a
    flat-fee planning engagement.

- question: "If I hire you, how do you help me decide whether to sell my RSUs at vest, and how are you paid for that?"
  expected_slugs: ["how-we-work-and-what-we-charge", "what-happens-to-your-rsus-at-vest"]
  answerable: true
  class: multi_source
  persona: "Marcus"
  expected_chunks:
    - "how-we-work-and-what-we-charge#what-does-your-fee-cover"
    - "what-happens-to-your-rsus-at-vest#should-i-sell-my-shares-at-vest-or-hold-them"
  reference_answer: >-
    The sell-or-hold decision sits inside the ongoing advisory relationship the firm's fee covers,
    alongside the withholding check and the concentration review. Because the firm is fee-only,
    the recommendation does not change based on whether you sell.
```

**The one row the implementer completes:** the `stale_number` row above deliberately ships from this
brief *without* `reference_answer`, because its answer is a figure this brief must not invent. After
the fact-check report lands, the implementer appends a `reference_answer` to that row containing
(a) the verified flat supplemental-wage withholding rate for 2026 exactly as IRS Pub 15 states it,
and (b) the rate that applies above $1,000,000 of supplemental wages, in two sentences. The figure
must be byte-identical to the one in A1's `## Key numbers (2026)` section and to the `verified` line
in `factcheck-what-happens-to-your-rsus-at-vest.md`. No other authored row may be edited.

**Why the near_miss row is where it is:** it points at the "non-US employees" planted gap (DESIGN
§C2) while sitting next to a high-similarity ESPP article — exactly the near-miss geometry task 15's
weak-query classifier needs.

## Steps (TDD)

- [ ] **RED — test-author, 1/4.** In `apps/api/tests/test_seed.py`, add `Counter` to the stdlib
      imports (`from collections import Counter`) and add `slugify_heading` to the existing
      `from app.eval.questions import ...` line.

- [ ] **RED — test-author, 2/4.** Replace the two count-band pins
      (`test_seed_corpus_directory_exists_and_file_count_is_in_expected_band` and
      `test_seed_corpus_published_and_draft_counts_are_in_expected_bands`) and the tag-vocabulary
      pin (`test_seed_corpus_tags_are_subset_of_the_six_prd_tags`) with exactly:

```python
# Phase-9 wave 1 (DESIGN §C2) grows the phase-4 corpus of 21 files by four per batch. Exact
# counts, not bands: a content wave that lands three of its four files must fail loudly.
_EXPECTED_SEED_FILE_COUNT = 25
_EXPECTED_PUBLISHED_COUNT = 21
_EXPECTED_DRAFT_COUNT = 4

# Tag vocabulary = PRD §8's six + the wave-1 additions (INDEX Global Constraints: the vocabulary is
# widened in the same task as the first article that uses a new tag). `north-carolina` belongs to
# the two "where you live" articles, which are wave 2 — it is deliberately NOT allowed yet.
_WAVE1_TAGS = {"equity-compensation", "our-firm"}
_ALLOWED_TAGS = _SIX_TAGS | _WAVE1_TAGS


def test_seed_corpus_directory_exists_and_file_count_is_in_expected_band() -> None:
    """21 phase-4 basics + 4 files per landed wave-1 batch (task 10 = batch A)."""
    files = _seed_md_files()
    assert len(files) == _EXPECTED_SEED_FILE_COUNT, (
        f"expected {_EXPECTED_SEED_FILE_COUNT} seed files, found {len(files)}: "
        f"{[f.name for f in files]}"
    )


def test_seed_corpus_published_and_draft_counts_are_in_expected_bands() -> None:
    records = _all_seed_records()
    published = [r for r in records if r["frontmatter"].get("status") == "published"]
    drafts = [r for r in records if r["frontmatter"].get("status") == "draft"]
    assert len(published) == _EXPECTED_PUBLISHED_COUNT, (
        f"expected {_EXPECTED_PUBLISHED_COUNT} published, found {len(published)}"
    )
    assert len(drafts) == _EXPECTED_DRAFT_COUNT, (
        f"expected {_EXPECTED_DRAFT_COUNT} drafts, found {len(drafts)}"
    )
    assert len(published) + len(drafts) == len(records), (
        "every seed file must be either published or draft"
    )


def test_seed_corpus_tags_are_subset_of_the_allowed_vocabulary() -> None:
    for record in _all_seed_records():
        tags = set(record["frontmatter"].get("tags") or [])
        unknown = tags - _ALLOWED_TAGS
        assert not unknown, (
            f"{record['path'].name}: tags {unknown} are outside the allowed vocabulary "
            f"{sorted(_ALLOWED_TAGS)}"
        )
```

  `test_seed_corpus_each_of_the_six_tags_is_used_at_least_twice` stays **untouched** — it pins the
  PRD six only, and `our-firm` is used once in batch A (a wave-1 equivalent pin arrives in task 11,
  when the second `our-firm` article lands).

  **Which pin, and the "same commit" rule.** The pin being extended is
  `test_seed_corpus_tags_are_subset_of_the_six_prd_tags` (it reads `_SIX_TAGS` directly); it is
  renamed to `test_seed_corpus_tags_are_subset_of_the_allowed_vocabulary` and reads a new
  `_ALLOWED_TAGS = _SIX_TAGS | _WAVE1_TAGS`, with `_SIX_TAGS` left intact for the PRD-six usage pin.
  `equity-compensation` arrives with A1 and `our-firm` with A4 — the first articles in the corpus to
  use either tag. Global Constraints say the vocabulary is widened "in the same commit as the first
  article using a new tag"; under this task's TDD split the widening lands one commit *earlier*, in
  the RED commit, together with the failing count pins. That satisfies the rule's intent — there is
  no commit in which a committed seed file carries a tag the pins reject — and it is the only
  ordering compatible with RED-before-GREEN. Do not defer the widening to the GREEN commit.

- [ ] **RED — test-author, 3/4.** Append this block at the end of
      `apps/api/tests/test_seed.py`:

```python
# ---- phase-9 wave-1 corpus (DESIGN §C1: H2 section == chunk == retrieval unit) ----

# slug -> (exact frontmatter title, exact frontmatter tag set). One entry per wave-1 article,
# added by the batch task that authored it (task 10 = batch A). Titles are pinned verbatim because
# `app.seed` is idempotent BY TITLE: a retitled file would silently create a second row on prod.
_WAVE1_ARTICLES: dict[str, tuple[str, frozenset[str]]] = {
    "what-happens-to-your-rsus-at-vest": (
        "What Happens to Your RSUs at Vest",
        frozenset({"equity-compensation", "tax-planning"}),
    ),
    "double-trigger-rsus-and-an-ipo": (
        "Double-Trigger RSUs and an IPO",
        frozenset({"equity-compensation", "tax-planning"}),
    ),
    "espp-qualifying-and-disqualifying-dispositions": (
        "ESPP Qualifying and Disqualifying Dispositions",
        frozenset({"equity-compensation", "tax-planning"}),
    ),
    "how-we-work-and-what-we-charge": (
        "How We Work and What We Charge",
        frozenset({"our-firm"}),
    ),
}

_KEY_NUMBERS_HEADING = "Key numbers (2026)"
_SOURCES_HEADING = "Sources"
_CURRENT_AS_OF_LINE = "_Current as of 2026-09_"
# Structural H2s carry lists, not prose: capped, but exempt from the 150-token floor.
_STRUCTURAL_H2 = {_KEY_NUMBERS_HEADING, _SOURCES_HEADING}
_H2_MIN_TOKENS = 150
_H2_MAX_TOKENS = 350

_H2_RE = re.compile(r"^## (?P<text>.+)$", re.MULTILINE)
# Any ATX heading that is NOT an H2: H1 (`# `) or H3-H6 (`### ` .. `###### `).
_NON_H2_HEADING_RE = re.compile(r"^(?:#|#{3,6}) .*$", re.MULTILINE)


def _wave1_records() -> dict[str, dict[str, Any]]:
    """The parsed seed record for every wave-1 slug, keyed by slug (asserts each file exists)."""
    by_slug = {record["path"].stem: record for record in _all_seed_records()}
    missing = sorted(set(_WAVE1_ARTICLES) - set(by_slug))
    assert not missing, f"wave-1 article files missing from seed/sample_content/: {missing}"
    return {slug: by_slug[slug] for slug in _WAVE1_ARTICLES}


def _h2_sections(body: str) -> list[tuple[str, str]]:
    """(heading text, section text including its heading line) per H2, in document order."""
    matches = list(_H2_RE.finditer(body))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections.append((match.group("text").strip(), body[match.start() : end]))
    return sections


def test_wave_1_articles_carry_their_pinned_title_tags_and_status() -> None:
    for slug, (title, tags) in _WAVE1_ARTICLES.items():
        frontmatter = _wave1_records()[slug]["frontmatter"]
        assert frontmatter["title"] == title, (
            f"{slug}: title is {frontmatter['title']!r}, brief pins {title!r} "
            "(seed is idempotent by title — a drifted title creates a duplicate row)"
        )
        assert set(frontmatter["tags"]) == set(tags), (
            f"{slug}: tags are {sorted(frontmatter['tags'])}, brief pins {sorted(tags)}"
        )
        assert frontmatter["status"] == "published", f"{slug}: wave-1 articles ship published"


def test_wave_1_articles_use_h2_headings_only() -> None:
    """Every ATX heading is a chunk boundary (`app.rag.chunking._HEADING_RE`), so an H1 or H3
    would split an authored section and break its `expected_chunks` reference."""
    for slug, record in _wave1_records().items():
        stray = _NON_H2_HEADING_RE.findall(record["body"])
        assert not stray, f"{slug}: non-H2 headings found: {stray}"


def test_wave_1_articles_have_key_numbers_sources_and_the_current_as_of_line() -> None:
    for slug, record in _wave1_records().items():
        headings = [heading for heading, _ in _h2_sections(record["body"])]
        assert _KEY_NUMBERS_HEADING in headings, f"{slug}: missing '## {_KEY_NUMBERS_HEADING}'"
        assert _SOURCES_HEADING in headings, f"{slug}: missing '## {_SOURCES_HEADING}'"
        assert headings[-2:] == [_KEY_NUMBERS_HEADING, _SOURCES_HEADING], (
            f"{slug}: the last two H2s must be Key numbers then Sources, got {headings[-2:]}"
        )
        key_numbers = dict(_h2_sections(record["body"]))[_KEY_NUMBERS_HEADING]
        non_blank = [line.strip() for line in key_numbers.splitlines() if line.strip()]
        assert non_blank[-1] == _CURRENT_AS_OF_LINE, (
            f"{slug}: Key numbers must end with {_CURRENT_AS_OF_LINE!r}, got {non_blank[-1]!r}"
        )
        sources = dict(_h2_sections(record["body"]))[_SOURCES_HEADING]
        assert "http" in sources, f"{slug}: Sources section lists no URL"


def test_wave_1_question_sections_are_inside_the_retrieval_token_band() -> None:
    """DESIGN §C1: an H2 section is the retrieval unit — 150-350 tokens, comfortably under
    `chunk_markdown`'s 400-token budget so it is never split."""
    from app.rag.chunking import count_tokens

    for slug, record in _wave1_records().items():
        body = record["body"]
        sections = _h2_sections(body)
        question_sections = [
            (heading, text) for heading, text in sections if heading not in _STRUCTURAL_H2
        ]
        assert 4 <= len(question_sections) <= 6, (
            f"{slug}: expected 4-6 question H2 sections, found {len(question_sections)}"
        )
        first_h2 = _H2_RE.search(body)
        lead = body[: first_h2.start()] if first_h2 else body
        assert count_tokens(lead) <= _H2_MAX_TOKENS, (
            f"{slug}: lead paragraph is {count_tokens(lead)} tokens, max {_H2_MAX_TOKENS}"
        )
        for heading, text in sections:
            tokens = count_tokens(text)
            assert tokens <= _H2_MAX_TOKENS, (
                f"{slug} / '{heading}': {tokens} tokens, max {_H2_MAX_TOKENS}"
            )
            if heading not in _STRUCTURAL_H2:
                assert tokens >= _H2_MIN_TOKENS, (
                    f"{slug} / '{heading}': {tokens} tokens, min {_H2_MIN_TOKENS}"
                )


def test_wave_1_h2_heading_slugs_are_unique_within_each_article() -> None:
    """`resolve_expected_chunks` takes the first matching heading; two H2s with the same slug
    would make an `expected_chunks` reference ambiguous."""
    for slug, record in _wave1_records().items():
        slugs = [slugify_heading(heading) for heading, _ in _h2_sections(record["body"])]
        duplicates = {value for value in slugs if slugs.count(value) > 1}
        assert not duplicates, f"{slug}: duplicate heading slugs {duplicates}"


def test_wave_1_expected_chunks_refs_name_real_headings_in_their_file() -> None:
    """The fast, pure-file twin of the DB resolver pin: catches a typo'd ref without seeding."""
    headings_by_slug = {
        slug: {slugify_heading(heading) for heading, _ in _h2_sections(record["body"])}
        for slug, record in _wave1_records().items()
    }
    for item in _load_eval_questions():
        for ref in item.get("expected_chunks", []):
            ref_slug, _, heading_slug = ref.partition("#")
            if ref_slug not in headings_by_slug:
                continue
            assert heading_slug in headings_by_slug[ref_slug], (
                f"{ref}: {ref_slug}.md has no H2 whose slug is {heading_slug!r} "
                f"(its headings: {sorted(headings_by_slug[ref_slug])})"
            )


# ---- eval-question class balance (DESIGN §B2: 80 rows at the end of task 14) ----

# Running totals after the batch this task lands. Phase-4 baseline: 17 answerable + 4 off_domain
# (both by the loader's default rule — those rows carry no explicit `class`). Batch A adds
# 6 answerable + 2 multi_source + 1 near_miss + 1 threshold + 1 stale_number.
_EXPECTED_CLASS_COUNTS = {
    "answerable": 23,
    "multi_source": 2,
    "near_miss": 1,
    "off_domain": 4,
    "threshold": 1,
    "stale_number": 1,
}
_EXPECTED_QUESTION_TOTAL = 32


def _question_class(item: dict[str, Any]) -> str:
    """The class a row resolves to, using `app.eval.questions.load_questions`' default rule."""
    return item.get("class", "answerable" if item["answerable"] else "off_domain")


def test_eval_questions_class_counts_match_the_authored_plan() -> None:
    items = _load_eval_questions()
    counts = dict(Counter(_question_class(item) for item in items))
    assert counts == _EXPECTED_CLASS_COUNTS, (
        f"class counts {counts} != planned {_EXPECTED_CLASS_COUNTS} (DESIGN §B2)"
    )
    assert len(items) == _EXPECTED_QUESTION_TOTAL


def test_eval_questions_unanswerable_rows_never_carry_a_reference_answer() -> None:
    """Phase-9 N5 ruling: a `reference_answer` on an `answerable: false` row hands the
    context-recall and answer-relevance judges a target the corpus must NOT contain, which would
    score a correct refusal as a miss. Task 14 adds the loader-level guard; this is the file pin."""
    offenders = [
        item["question"]
        for item in _load_eval_questions()
        if item["answerable"] is False and "reference_answer" in item
    ]
    assert not offenders, f"answerable:false rows carrying a reference_answer: {offenders}"


def test_eval_questions_near_miss_rows_are_unanswerable_and_uncited() -> None:
    """A near_miss row points at a planted gap (DESIGN §C2): no expected slugs, no expected
    chunks — the corpus is supposed to miss it."""
    for item in _load_eval_questions():
        if _question_class(item) != "near_miss":
            continue
        assert item["answerable"] is False, f"near_miss row marked answerable: {item['question']!r}"
        assert item["expected_slugs"] == [], f"near_miss row has expected_slugs: {item!r}"
        assert not item.get("expected_chunks"), f"near_miss row has expected_chunks: {item!r}"
```

- [ ] **RED — test-author, 4/4. Run RED and record the evidence.** From the repo root, exporting
      only `TEST_DATABASE_URL` (never `source .env`, never print the value):

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
[ -n "$TEST_DATABASE_URL" ] && echo "TEST_DATABASE_URL: set"
cd apps/api && uv run pytest tests/test_seed.py -q
```

  Expected RED: the file-count pin fails (21 ≠ 25), the published-count pin fails (17 ≠ 21),
  `_wave1_records()` asserts the four files are missing, and the class-count pin fails (21 rows,
  `{'answerable': 17, 'off_domain': 4}`). Paste those failure lines. Note in the report that the
  widened tag-vocabulary pin and the three "no reference_answer / near_miss shape" pins **pass**
  at RED (a widening and a guard over rows that do not exist yet) — that is expected, not a gap.

- [ ] **RED commit:** `git commit -m "test(api): pin wave-1 batch A corpus shape + eval class counts (p9 t10)"`

- [ ] **GREEN — drafter (Sonnet), 1/3.** Write the four articles per their briefs and the Article
      shape contract. Where a number is not yet verified, write the rule and leave a list of the
      values you need at the top of each draft's fact-check request. Do not touch
      `seed/eval_questions.yaml` yet.

- [ ] **GREEN — fact-check agent (Sonnet, a DIFFERENT agent), 2/3.** For each article, WebFetch
      every primary source named in its brief, then write
      `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md` in this format:

```markdown
# Fact-check — <slug>

Fetched <date>. Sources are primary only (irs.gov / ssa.gov / sec.gov / uscode.house.gov / cfp.net).

| # | Claim (verbatim from the article) | Source + URL fetched | Source's own words | Verdict |
|---|---|---|---|---|
| 1 | ... | IRS Pub 15, section 7 — https://... | "..." | verified |
| 2 | ... | — | — | unverifiable |

## Unverifiable claims (each must be removed or reduced to the rule before the article ships)
- ...

## Firm-policy lines skipped (fictional, per the brief)
- ...
```

  Rules: one row per number **and** per stated rule; a claim with no fetched source line is
  `unverifiable` and the article **FAILS** — hand it back to the drafter, who removes the number
  (keeping the rule) and resubmits. Repeat until no `unverifiable` row remains. Record the loop
  count in the implementer report.

- [ ] **GREEN — drafter, 3/3.** Append the comment line and the 11 eval rows verbatim, then write
      the `stale_number` row's `reference_answer` from the verified Pub 15 line (the only authored
      row you may extend — see "The one row the implementer completes").

- [ ] **Run GREEN (pins):**

```bash
cd apps/api && uv run pytest tests/test_seed.py tests/test_eval_questions_v2.py -q
```

  All pins green, including the pre-existing DB pin
  `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus` — that is the
  proof every new `slug#heading-slug` ref resolves against the real seeded corpus.

- [ ] **GREEN — real seed + harness run on a scratch DB** (evidence for the report). The scratch DB
      is derived from `TEST_DATABASE_URL` by substituting the database name; nothing here may touch
      the dev or prod database:

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
export OPENAI_API_KEY="$(grep -m1 '^OPENAI_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n')"
export SCRATCH_DB=advisordesk_p9wave1a
export DATABASE_URL="${TEST_DATABASE_URL%/*}/$SCRATCH_DB"   # db-name substitution only
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY: set"
docker exec advisordesk-test-db psql -U postgres -c "DROP DATABASE IF EXISTS $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -c "CREATE DATABASE $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -d "$SCRATCH_DB" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed
uv run python -m app.eval.groundedness --label wave1-a --no-persist \
  | tee ../../.superpowers/sdd/phase-9-eval-data-loop/task-10-harness-capture.txt
```

  (If `TEST_DATABASE_URL` carries a query string, strip it before substituting and say so in the
  report.) Expected seed line: 25 created, 21 published. Paste into the implementer report: the
  seed report line, the **per-class table**, the summary line, the failure-cause distribution, and
  the `unresolved expected_chunks refs` count (must be 0).

- [ ] **Gates:** `pnpm gates:api` (ruff, ruff format, mypy, lint-imports, pytest — with only
      `TEST_DATABASE_URL` exported).

- [ ] **GREEN commit:**
      `git commit -m "feat(seed): wave-1 batch A — RSU vest, double-trigger IPO, ESPP, firm fees (p9 t10)"`

- [ ] **Opus batch review** (reviewer ≠ drafter ≠ fact-checker): the four articles against their
      briefs and the shape contract, the four fact-check reports (every number traced), the 11 YAML
      rows against the authored block, and the harness capture.

## Verify

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
cd apps/api && uv run pytest tests/test_seed.py tests/test_eval_questions_v2.py -q
pnpm gates:api
git diff --stat main -- ../../seed/sample_content   # exactly 4 files added, 0 modified
```

## Acceptance

- Four new files exist at the pinned paths with the pinned titles, tags and `status: published`;
  no existing seed file is modified.
- Every article matches the shape contract: H2-only, 4–6 question sections each 150–350 tokens,
  `## Key numbers (2026)` then `## Sources` last, the `_Current as of 2026-09_` line closing Key
  numbers, the verbatim footer last.
- **Every number in every article has a `verified` line in that article's fact-check report naming
  the fetched primary-source URL and quoting the source.** No `unverifiable` rows remain; removed
  claims are listed in the report.
- Fictional firm figures appear only in A4, read as firm policy, and are absent from `## Sources`.
- No article states a rule or number for any of the five planted gaps.
- `seed/eval_questions.yaml` ends with the comment line and the 11 rows exactly as authored, plus
  the one `reference_answer` added to the `stale_number` row from the verified Pub 15 figure.
- `test_seed.py` class counts are `{answerable: 23, multi_source: 2, near_miss: 1, off_domain: 4,
  threshold: 1, stale_number: 1}`, total 32 rows.
- The DB resolver pin passes: every `expected_chunks` ref resolves against the seeded corpus.
- A real `python -m app.seed` on a scratch DB reports 25 created / 21 published, and a
  `--label wave1-a --no-persist` harness run prints a per-class table with 0 unresolved refs.
- Nothing was published to prod.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-10-test-author.md`
- Implementer (drafter): `.superpowers/sdd/phase-9-eval-data-loop/reports/task-10-implementer.md`
- Fact-check: `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md` (four files)
- Reviewer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-10-review.md`
