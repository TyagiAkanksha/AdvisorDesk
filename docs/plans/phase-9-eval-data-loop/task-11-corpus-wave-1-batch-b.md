---
id: p9-t11
phase: phase-9-eval-data-loop
depends_on: [p9-t10]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 11 — Corpus wave 1, batch B: ISOs vs NSOs · AMT from an ISO exercise · the 83(b) election · onboarding

## Goal

Priya's batch. Four more wave-1 articles plus their 11 eval questions: the option-tax mechanics
(ISO vs NSO), the AMT scare and the credit that follows it, the 83(b) election and its 30-day clock,
and the firm's onboarding page. The batch carries the "stock options in a divorce" planted gap as its
near-miss.

Same four-agent content pipeline as batch A (DESIGN §C3): test-author (pins) → drafter (Sonnet) →
fact-check agent (Sonnet, WebFetch, a different agent) → Opus batch review. Every number is verified
against a named primary source or it does not ship. **No prod publish** (task 18).

**Depends on task 10** because both batches edit the same two files (`seed/eval_questions.yaml`,
`apps/api/tests/test_seed.py`) and because batch B's `multi_source` row cites a batch-A slug.

**No application code changes.** The only Python file this task touches is `apps/api/tests/test_seed.py`.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/FIRM-FACTS.md` — the fictional firm's fee schedule,
  policies and voice (controller ruling 2026-09-12): every `[FIRM POLICY]` value in this batch
  comes from THAT file verbatim — never invent a figure, never contradict it.
- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §C1 (article shape), §C2 (personas, article list,
  the five planted gaps), §C3 (authoring pipeline), §B2 (v2 eval keys, the six classes).
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` — "Global Constraints".
- `apps/api/tests/test_seed.py` — **all of it, at its post-task-10 state**: the `_WAVE1_ARTICLES`
  map, `_wave1_records`, `_h2_sections`, the token-band / heading / class-count pins batch A added,
  and the pre-existing DB pin
  `test_eval_questions_expected_chunks_refs_all_resolve_against_the_seeded_corpus`.
- `seed/eval_questions.yaml` — the 32 committed rows (21 phase-4 + 11 batch A); this task appends 11
  more and changes nothing above them.
- `seed/sample_content/what-happens-to-your-rsus-at-vest.md` — batch A's reference implementation of
  the shape contract (the file this batch's multi_source row cites), and
  `seed/sample_content/how-we-work-and-what-we-charge.md` for the firm voice and the fictional fee
  figures batch B's onboarding page must stay consistent with.
- `apps/api/app/rag/chunking.py` — `_HEADING_RE` (any ATX heading is a chunk boundary),
  `count_tokens` (`cl100k_base`), `chunk_markdown`'s 400+50 budget.
- `apps/api/app/services/content.py` lines 26–32 — `_slugify`, the rule behind
  `filename == slugify(title)` and resolvable `slug#heading-slug` refs.
- `apps/api/app/eval/questions.py` — `load_questions` validation and `resolve_expected_chunks`.

Do **not** read tasks 12–14.

## Files

**Create (content)**
- `seed/sample_content/isos-and-nsos-how-each-one-is-taxed.md`
- `seed/sample_content/amt-after-an-iso-exercise-and-the-credit-that-follows.md`
- `seed/sample_content/the-83-b-election-on-restricted-stock.md`
- `seed/sample_content/onboarding-with-us-and-what-to-bring.md`

**Create (fact-check reports, gitignored scratch area)**
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-isos-and-nsos-how-each-one-is-taxed.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-amt-after-an-iso-exercise-and-the-credit-that-follows.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-the-83-b-election-on-restricted-stock.md`
- `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-onboarding-with-us-and-what-to-bring.md`

**Modify**
- `seed/eval_questions.yaml` (append the 11 rows below, verbatim)
- `apps/api/tests/test_seed.py` (the edits in Steps RED)

**Do not touch:** the 25 existing `seed/sample_content/*.md` files (including batch A's four), any
file under `apps/api/app/`, `seed/agent_tasks.yaml`, `seed/judge_labels.yaml`, prod.

## Interfaces

| Artifact | Consumer |
|---|---|
| four published seed articles | tasks 12–13 (multi_source pairs), 14 (persona questions), 18 (prod publish + replay) |
| 11 eval rows incl. 1 near_miss at the "options in a divorce" planted gap | task 14's class balance; task 15's weak-query demo |
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
   article they read as the firm's own policy and never appear under `## Sources`. Any fee figure
   must match `how-we-work-and-what-we-charge.md` exactly.
6. **Planted gaps stay unwritten:** no rule and no number for non-US employees' equity, crypto
   compensation, stock options in a divorce, 401(k) loans against employer stock, or QSBS (§1202).
   A one-clause "not covered here" boundary is allowed; an explanation is not.
7. **Voice:** one firm voice, second person to the client; Queen City Wealth Planning named in the
   firm article and at most once per equity article.
8. `_Current as of 2026-09_` closes the Key numbers section; the verbatim footer is the last
   non-blank line (em dash U+2014).

---

## Article brief B1 — ISOs and NSOs: How Each One Is Taxed

- **Title (exact):** `ISOs and NSOs: How Each One Is Taxed`
- **Filename:** `seed/sample_content/isos-and-nsos-how-each-one-is-taxed.md`
- **Tags:** `equity-compensation`, `tax-planning` · **Status:** `published`
- **Persona:** Priya — senior IC at a pre-IPO startup holding ISOs, with NSOs from an earlier job.
- **Decision it serves:** whether and when to exercise, and what cash each route needs.

**H2 outline (verbatim headings, in this order):**

1. `## What is the difference between an ISO and an NSO?` — who can receive each, the statutory
   requirements an ISO must meet, and the single sentence that matters: the difference shows up at
   exercise.
2. `## What do I owe when I exercise an NSO?` — the spread is ordinary compensation income, withheld
   through payroll as supplemental wages; basis becomes the FMV at exercise.
3. `## What do I owe when I exercise an ISO?` — no regular-tax income at exercise if you hold; the
   spread is an AMT item (point at the AMT article, do not re-explain AMT here); the $100,000
   first-year-exercisable limit and what happens to the excess.
4. `## How long do I have to hold ISO shares for the best tax treatment?` — the two statutory
   holding periods; a sale before either one is a disqualifying disposition and the spread becomes
   ordinary income.
5. `## What if my options expire before I can exercise?` — the maximum statutory option term, the
   post-termination exercise window as a plan term, and the three-month ISO rule (cross-reference
   only; batch D's leaving article owns it).

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the $100,000 limit on ISO stock first exercisable in a calendar year | IRC §422(d) (uscode.house.gov / law.cornell.edu) | `[STATUTORY]` |
| the two ISO holding periods (from grant and from exercise) | IRC §422(a)(1) + IRS Publication 525, "Incentive stock options" | `[STATUTORY]` |
| the maximum term of an ISO from its grant date | IRC §422(b)(3) | `[STATUTORY]` |
| the post-termination period within which an ISO exercise still qualifies | IRC §422(a)(2) | `[STATUTORY]` |
| that an NSO spread at exercise is wages subject to withholding | IRS Pub 525, "Nonstatutory stock options" + IRS Pub 15 section 7 | rule, no number |
| the form your employer files/furnishes for an ISO exercise | Instructions for Forms 3921 and 3922 | `[STATUTORY]` (the furnishing deadline) |

**`## Sources`:** IRS Pub 525 · Instructions for Forms 3921 and 3922 · IRC §422 · IRS Pub 15.

---

## Article brief B2 — AMT After an ISO Exercise, and the Credit That Follows

- **Title (exact):** `AMT After an ISO Exercise, and the Credit That Follows`
- **Filename:** `seed/sample_content/amt-after-an-iso-exercise-and-the-credit-that-follows.md`
- **Tags:** `equity-compensation`, `tax-planning` · **Status:** `published`
- **Persona:** Priya — has been told exercising early is smart and is now frightened of AMT.
- **Decision it serves:** how many ISOs to exercise this year.

**H2 outline (verbatim headings, in this order):**

1. `## Why does exercising an ISO trigger AMT?` — the spread is not regular-tax income but is an AMT
   adjustment; AMT is a parallel calculation and you pay the higher of the two.
2. `## How do I estimate the AMT on my exercise?` — the sequence: AMT income, exemption, phaseout,
   the two AMT rates, compare with regular tax; Form 6251 is where it happens.
3. `## What is the AMT credit and when do I get it back?` — the minimum tax credit carries forward
   and is used in years when regular tax exceeds AMT; Form 8801; usually recovered over several
   years, not at once.
4. `## Can I exercise up to the point where AMT starts?` — the "exercise to the crossover point"
   idea stated as arithmetic, not advice; what makes the estimate move (other income, the spread,
   the exemption phaseout).
5. `## What if the shares drop after I exercise?` — the risk of paying AMT on a value that no longer
   exists; that selling in the same calendar year as the exercise removes the AMT adjustment but
   makes the sale a disqualifying disposition.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the 2026 AMT exemption amounts (single / married filing jointly) | the IRS newsroom release "IRS provides tax inflation adjustments for tax year 2026" **and** the revenue procedure it links — record the Rev. Proc. number in the report | `[ANNUAL]` |
| the 2026 exemption phaseout thresholds | same source | `[ANNUAL]` |
| the two AMT rate brackets and the income point where the rate changes | Instructions for Form 6251 | `[STATUTORY]`/`[ANNUAL]` — take the instructions' own figure |
| that the ISO spread at exercise is an AMT adjustment | Instructions for Form 6251, "Exercise of incentive stock options" + IRS Pub 525 | rule, no number |
| that the AMT paid becomes a minimum tax credit carried forward | Instructions for Form 8801 | rule, no number |

**`## Sources`:** Instructions for Form 6251 · Instructions for Form 8801 · IRS Pub 525 · the IRS
2026 inflation-adjustment release and its revenue procedure.

---

## Article brief B3 — The 83(b) Election on Restricted Stock

- **Title (exact):** `The 83(b) Election on Restricted Stock`
- **Filename:** `seed/sample_content/the-83-b-election-on-restricted-stock.md`
- **Tags:** `equity-compensation`, `tax-planning` · **Status:** `published`
- **Persona:** Priya — offered early exercise on her option grant, or holding restricted stock at an
  early-stage company.
- **Decision it serves:** file the election or not, and before when.

**H2 outline (verbatim headings, in this order):**

1. `## What does an 83(b) election actually do?` — moves taxation of restricted property to transfer
   date instead of as the restrictions lapse; small ordinary-income amount now, later appreciation
   as capital gain.
2. `## When does the 30-day clock start and end?` — counted in calendar days from the transfer of the
   property; no extension; what "transfer" means for early-exercised options.
3. `## When is an 83(b) election a good idea?` — low spread at transfer, a plan to hold, and the
   capacity to lose the money; the cases where it backfires (the company fails, you leave before
   vesting, the tax paid is not refundable).
4. `## How do I file it and what do I keep?` — the statement's required contents, where it goes, the
   copy for your employer, and keeping proof of mailing with your records.
5. `## Does an 83(b) election apply to my RSUs?` — no: an RSU is an unfunded promise, not transferred
   property; the shortest honest section in the corpus.

**Key numbers (2026) — items and their PRIMARY SOURCE to fetch:**

| Item | Primary source to fetch | Note |
|---|---|---|
| the 30-day deadline for filing an 83(b) election | IRC §83(b)(2) + Treas. Reg. §1.83-2(b) (ecfr.gov) | `[STATUTORY]` |
| that the election may not be revoked without IRS consent | Treas. Reg. §1.83-2(f) | rule, no number |
| the information the election statement must contain | Treas. Reg. §1.83-2(e) (and Rev. Proc. 2012-29's model election, if fetched) | rule, no number |
| that an RSU is not "property" transferred at grant, so §83(b) is unavailable | IRS Pub 525, "Restricted property" discussion | rule, no number |

**`## Sources`:** IRC §83 · Treas. Reg. §1.83-2 · Rev. Proc. 2012-29 · IRS Pub 525.

---

## Article brief B4 — Onboarding With Us and What to Bring

- **Title (exact):** `Onboarding With Us and What to Bring`
- **Filename:** `seed/sample_content/onboarding-with-us-and-what-to-bring.md`
- **Tags:** `our-firm` · **Status:** `published`
- **Persona:** all three; in practice the page a new client reads the week they sign.
- **Decision it serves:** what to gather before the first meeting, and what the first month looks
  like.

**H2 outline (verbatim headings, in this order):**

1. `## What happens in the first 30 days?` — the sequence of meetings and deliverables.
   `[FIRM POLICY — fictional, skip fact-check]`
2. `## What documents should I bring to our first meeting?` — pay statements, last year's return,
   account statements, insurance and benefits summaries. The document *names* are real (W-2, 1099-B,
   Form 3921, Form 3922) and must be sourced.
3. `## What do you need from my equity paperwork?` — grant agreements, the plan document, the
   exercise history, Forms 3921/3922, vesting schedules; why each one changes the answer.
4. `## How do you handle my data and logins?` — read-only account links, no password sharing,
   document-vault practice. `[FIRM POLICY]`
5. `## What will I walk away with?` — the deliverables of the first engagement. `[FIRM POLICY]`

**Key numbers (2026) — items:**

| Item | Source | Note |
|---|---|---|
| onboarding timeline, meeting cadence, the fee already published on the fees page | none | `[FIRM POLICY — fictional, skip fact-check]` — figures identical to `how-we-work-and-what-we-charge.md` |
| the date by which your employer must furnish Form 3922 (ESPP) and Form 3921 (ISO exercise) | Instructions for Forms 3921 and 3922 | `[STATUTORY]` |
| that the firm's brochure (Form ADV Part 2A) is delivered before or at the time you sign | SEC Rule 204-3 / Form ADV Part 2A instructions | rule, no number |

**`## Sources`:** Instructions for Forms 3921 and 3922 · SEC Form ADV Part 2A instructions /
Rule 204-3. The fictional timeline and fees are **not** sourced.

---

## Eval questions — append verbatim to `seed/eval_questions.yaml`

Append after batch A's rows, preceded by this comment line:

```yaml
# --- phase-9 wave 1, batch B (task 11): ISO/NSO · AMT + credit · 83(b) · onboarding ---
```

Per article (DESIGN §C2: "every article ships with its 2–4 eval questions"): rows 1–3 → **B1**,
rows 4–6 → **B2**, rows 7–9 → **B3** (row 8 is B3's planted-gap near-miss, authored with it but
citing nothing), rows 10–11 → **B4**. Classes within the batch: 6 `answerable`, 2 `multi_source`,
1 `near_miss`, 1 `threshold`, 1 `stale_number`.

Then exactly these 11 rows, in this order, unedited:

```yaml
- question: "What is the difference between an ISO and an NSO when I exercise?"
  expected_slugs: ["isos-and-nsos-how-each-one-is-taxed"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks:
    - "isos-and-nsos-how-each-one-is-taxed#what-is-the-difference-between-an-iso-and-an-nso"
    - "isos-and-nsos-how-each-one-is-taxed#what-do-i-owe-when-i-exercise-an-nso"
  reference_answer: >-
    Exercising an NSO creates ordinary compensation income equal to the spread between your strike
    price and the share value, withheld through payroll. Exercising an ISO creates no regular-tax
    income if you hold the shares, but the same spread is an alternative-minimum-tax item.

- question: "If I exercise my incentive stock options and keep the shares, what do I owe that year?"
  expected_slugs: ["isos-and-nsos-how-each-one-is-taxed"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks: ["isos-and-nsos-how-each-one-is-taxed#what-do-i-owe-when-i-exercise-an-iso"]
  reference_answer: >-
    For regular tax, nothing is due at exercise when you hold the shares. The spread at exercise is
    an AMT adjustment, so an exercise-and-hold can still produce a bill through the alternative
    minimum tax.

- question: "I have ISOs from my startup and RSUs from my old public employer — how is each one taxed?"
  expected_slugs: ["isos-and-nsos-how-each-one-is-taxed", "what-happens-to-your-rsus-at-vest"]
  answerable: true
  class: multi_source
  persona: "Priya"
  expected_chunks:
    - "isos-and-nsos-how-each-one-is-taxed#what-is-the-difference-between-an-iso-and-an-nso"
    - "what-happens-to-your-rsus-at-vest#what-happens-when-my-rsus-vest"
  reference_answer: >-
    RSUs are taxed as ordinary wage income when they vest and settle, with no timing choice. ISOs
    are not taxed at grant and, for regular tax, not at exercise; the tax depends on when you
    exercise and when you sell, and an exercise can create an AMT item.

- question: "Why would exercising my ISOs create an alternative minimum tax bill?"
  expected_slugs: ["amt-after-an-iso-exercise-and-the-credit-that-follows"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks:
    - "amt-after-an-iso-exercise-and-the-credit-that-follows#why-does-exercising-an-iso-trigger-amt"
  reference_answer: >-
    The spread between your strike price and the share value at exercise is not regular-tax income,
    but it is added back when you compute the alternative minimum tax. If the AMT result exceeds
    your regular tax, you pay the difference.

- question: "If I pay AMT because of an ISO exercise, do I ever get that money back?"
  expected_slugs: ["amt-after-an-iso-exercise-and-the-credit-that-follows"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks:
    - "amt-after-an-iso-exercise-and-the-credit-that-follows#what-is-the-amt-credit-and-when-do-i-get-it-back"
  reference_answer: >-
    The AMT you pay on an ISO exercise creates a minimum tax credit that carries forward. You use
    it in later years where your regular tax exceeds your AMT, claimed on Form 8801, usually
    recovering it over several years rather than all at once.

- question: "What is the AMT exemption for a married couple filing jointly this year?"
  expected_slugs: ["amt-after-an-iso-exercise-and-the-credit-that-follows"]
  answerable: true
  class: stale_number
  persona: "Priya"
  expected_chunks: ["amt-after-an-iso-exercise-and-the-credit-that-follows#key-numbers-2026"]

- question: "What does filing an 83(b) election actually do for me?"
  expected_slugs: ["the-83-b-election-on-restricted-stock"]
  answerable: true
  class: answerable
  persona: "Priya"
  expected_chunks: ["the-83-b-election-on-restricted-stock#what-does-an-83-b-election-actually-do"]
  reference_answer: >-
    An 83(b) election has you taxed on restricted stock at its value when you receive it instead of
    as it vests. You pay ordinary income tax on a small amount up front, and later appreciation is
    capital gain if you hold the shares.

- question: "My divorce is being finalized — how do we split my stock options?"
  expected_slugs: []
  answerable: false
  class: near_miss
  persona: "Priya"

- question: "I bought shares I do not fully own yet and a colleague said I have about a month to tell the IRS something. What is she talking about?"
  expected_slugs: ["the-83-b-election-on-restricted-stock"]
  answerable: true
  class: threshold
  persona: "Priya"
  expected_chunks: ["the-83-b-election-on-restricted-stock#when-does-the-30-day-clock-start-and-end"]
  reference_answer: >-
    She means the 83(b) election, which must be filed within 30 days of the transfer of the
    restricted stock. The deadline runs in calendar days from the transfer date and cannot be
    extended.

- question: "What should I bring to a first meeting with you?"
  expected_slugs: ["onboarding-with-us-and-what-to-bring"]
  answerable: true
  class: answerable
  persona: "Sam"
  expected_chunks:
    - "onboarding-with-us-and-what-to-bring#what-documents-should-i-bring-to-our-first-meeting"
  reference_answer: >-
    Bring your recent pay statements and W-2, your last two tax returns, statements for your
    retirement and brokerage accounts, and your benefits summary. If you have equity, bring the
    grant agreements, the plan document and any Form 3921 or 3922 you received.

- question: "What paperwork do you need from me to look at an ISO exercise?"
  expected_slugs: ["onboarding-with-us-and-what-to-bring", "isos-and-nsos-how-each-one-is-taxed"]
  answerable: true
  class: multi_source
  persona: "Priya"
  expected_chunks:
    - "onboarding-with-us-and-what-to-bring#what-do-you-need-from-my-equity-paperwork"
    - "isos-and-nsos-how-each-one-is-taxed#what-do-i-owe-when-i-exercise-an-iso"
  reference_answer: >-
    The firm asks for your grant agreement, the plan document, your exercise history, any Form 3921
    and your last two tax returns. Those show the strike price, the exercise dates and the holding
    periods that decide whether an exercise is an AMT item or ordinary income.
```

**The one row the implementer completes:** the `stale_number` row ships from this brief *without*
`reference_answer`, because its answer is a 2026 figure this brief must not invent. After the
fact-check report lands, the implementer appends a two-sentence `reference_answer` stating (a) the
verified 2026 AMT exemption for married filing jointly and (b) the income level at which it starts
to phase out, both exactly as the IRS source states them. The figures must be byte-identical to B2's
`## Key numbers (2026)` lines and to the `verified` rows in
`factcheck-amt-after-an-iso-exercise-and-the-credit-that-follows.md`. No other authored row may be
edited.

**Why the near_miss row is where it is:** it points at the "stock options in a divorce" planted gap
while sitting beside three high-similarity option articles — the geometry task 15's classifier needs.

## Steps (TDD)

- [ ] **RED — test-author, 1/3.** In `apps/api/tests/test_seed.py`, bump the two corpus counts
      batch A introduced:

```python
_EXPECTED_SEED_FILE_COUNT = 29
_EXPECTED_PUBLISHED_COUNT = 25
_EXPECTED_DRAFT_COUNT = 4
```

  and add batch B's four entries to `_WAVE1_ARTICLES` (keep batch A's four, in file order):

```python
    "isos-and-nsos-how-each-one-is-taxed": (
        "ISOs and NSOs: How Each One Is Taxed",
        frozenset({"equity-compensation", "tax-planning"}),
    ),
    "amt-after-an-iso-exercise-and-the-credit-that-follows": (
        "AMT After an ISO Exercise, and the Credit That Follows",
        frozenset({"equity-compensation", "tax-planning"}),
    ),
    "the-83-b-election-on-restricted-stock": (
        "The 83(b) Election on Restricted Stock",
        frozenset({"equity-compensation", "tax-planning"}),
    ),
    "onboarding-with-us-and-what-to-bring": (
        "Onboarding With Us and What to Bring",
        frozenset({"our-firm"}),
    ),
```

  and update the class-count totals (batch B adds 6 answerable + 2 multi_source + 1 near_miss +
  1 threshold + 1 stale_number):

```python
_EXPECTED_CLASS_COUNTS = {
    "answerable": 29,
    "multi_source": 4,
    "near_miss": 2,
    "off_domain": 4,
    "threshold": 2,
    "stale_number": 2,
}
_EXPECTED_QUESTION_TOTAL = 43
```

- [ ] **RED — test-author, 2/3.** Add the wave-1 tag-usage pin (now earnable: `our-firm` reaches two
      articles with B4, `equity-compensation` has seven). Place it directly after
      `test_seed_corpus_each_of_the_six_tags_is_used_at_least_twice`, which stays untouched:

```python
def test_seed_corpus_each_wave_1_tag_is_used_at_least_twice() -> None:
    """The PRD-six pin above does not cover the wave-1 additions (INDEX Global Constraints). A tag
    used once is a typo risk and a useless filter facet, so each wave-1 tag earns its place the
    same way: at least two articles."""
    counts: dict[str, int] = dict.fromkeys(_WAVE1_TAGS, 0)
    for record in _all_seed_records():
        for tag in record["frontmatter"].get("tags") or []:
            if tag in counts:
                counts[tag] += 1
    under_used = {tag: n for tag, n in counts.items() if n < 2}
    assert not under_used, f"wave-1 tags used fewer than 2 times: {under_used}"
```

- [ ] **RED — test-author, 3/3. Run RED and record the evidence.** From the repo root, exporting
      only `TEST_DATABASE_URL`:

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
[ -n "$TEST_DATABASE_URL" ] && echo "TEST_DATABASE_URL: set"
cd apps/api && uv run pytest tests/test_seed.py -q
```

  Expected RED: the file-count pin fails (25 ≠ 29), the published-count pin fails (21 ≠ 25),
  `_wave1_records()` asserts batch B's four files are missing, and the class-count pin fails
  (43 expected vs 32 present). Paste those failure lines. The new tag-usage pin fails too
  (`our-firm` used once) — note it: it turns green only when B4 lands.

- [ ] **RED commit:** `git commit -m "test(api): pin wave-1 batch B corpus shape + eval class counts (p9 t11)"`

- [ ] **GREEN — drafter (Sonnet), 1/3.** Write the four articles per their briefs and the shape
      contract. B2 must not restate B1's mechanics and B1 must not explain AMT — each section
      answers its own heading, because each section is a separate retrieval unit.

- [ ] **GREEN — fact-check agent (Sonnet, a DIFFERENT agent), 2/3.** WebFetch every primary source
      named in each brief, then write
      `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md`:

```markdown
# Fact-check — <slug>

Fetched <date>. Sources are primary only (irs.gov / sec.gov / ecfr.gov / uscode.house.gov).

| # | Claim (verbatim from the article) | Source + URL fetched | Source's own words | Verdict |
|---|---|---|---|---|
| 1 | ... | IRC §422(d) — https://... | "..." | verified |
| 2 | ... | — | — | unverifiable |

## Unverifiable claims (each must be removed or reduced to the rule before the article ships)
- ...

## Firm-policy lines skipped (fictional, per the brief)
- ...
```

  One row per number **and** per stated rule. Any `unverifiable` row fails the article: hand it back,
  the drafter removes the number (keeping the rule), re-check. Repeat until clean. For B2 the report
  must name the exact revenue procedure the IRS 2026 release links — "the newsroom page said so" is
  not a primary-source line on its own.

- [ ] **GREEN — drafter, 3/3.** Append the comment line and the 11 eval rows verbatim, then write the
      `stale_number` row's `reference_answer` from the verified AMT figures.

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
export SCRATCH_DB=advisordesk_p9wave1b
export DATABASE_URL="${TEST_DATABASE_URL%/*}/$SCRATCH_DB"   # db-name substitution only
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY: set"
docker exec advisordesk-test-db psql -U postgres -c "DROP DATABASE IF EXISTS $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -c "CREATE DATABASE $SCRATCH_DB;"
docker exec advisordesk-test-db psql -U postgres -d "$SCRATCH_DB" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed
uv run python -m app.eval.groundedness --label wave1-b --no-persist \
  | tee ../../.superpowers/sdd/phase-9-eval-data-loop/task-11-harness-capture.txt
```

  Expected seed line: 29 created, 25 published. Paste into the implementer report: the seed line,
  the **per-class table**, the summary line, the failure-cause distribution, and the
  `unresolved expected_chunks refs` count (must be 0). Compare the per-class table with task 10's
  capture and note any class that moved.

- [ ] **Gates:** `pnpm gates:api`.

- [ ] **GREEN commit:**
      `git commit -m "feat(seed): wave-1 batch B — ISO/NSO, AMT credit, 83(b), onboarding (p9 t11)"`

- [ ] **Opus batch review** (reviewer ≠ drafter ≠ fact-checker): the four articles against their
      briefs and the shape contract, the four fact-check reports (every number traced to a fetched
      URL), the 11 YAML rows against the authored block, the harness capture.

## Verify

```bash
cd /home/ak/Documents/github_akanksha/AdvisorDesk
export TEST_DATABASE_URL="$(grep -m1 '^TEST_DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r\n')"
cd apps/api && uv run pytest tests/test_seed.py tests/test_eval_questions_v2.py -q
pnpm gates:api
git diff --stat main -- ../../seed/sample_content   # 8 files added (batches A+B), 0 modified
```

## Acceptance

- Four new files at the pinned paths with the pinned titles, tags and `status: published`; batch A's
  four and the 21 basics are untouched.
- Every article matches the shape contract: H2-only, 4–6 question sections of 150–350 tokens,
  `## Key numbers (2026)` then `## Sources` last, `_Current as of 2026-09_` closing Key numbers, the
  verbatim footer last.
- **Every number in every article has a `verified` line in that article's fact-check report naming
  the fetched primary-source URL and quoting the source**, including the exact revenue procedure
  behind B2's AMT figures. No `unverifiable` rows remain.
- B4's fictional figures match `how-we-work-and-what-we-charge.md` exactly and are absent from
  `## Sources`.
- No article states a rule or number for any of the five planted gaps — in particular nothing about
  options in a divorce.
- `seed/eval_questions.yaml` ends with the comment line and the 11 rows exactly as authored, plus
  the one `reference_answer` added to the `stale_number` row.
- Class counts are `{answerable: 29, multi_source: 4, near_miss: 2, off_domain: 4, threshold: 2,
  stale_number: 2}`, total 43 rows; `test_seed_corpus_each_wave_1_tag_is_used_at_least_twice` passes.
- The DB resolver pin passes; a real seed on a scratch DB reports 29 created / 25 published; the
  `--label wave1-b --no-persist` run prints a per-class table with 0 unresolved refs.
- Nothing was published to prod.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-11-test-author.md`
- Implementer (drafter): `.superpowers/sdd/phase-9-eval-data-loop/reports/task-11-implementer.md`
- Fact-check: `.superpowers/sdd/phase-9-eval-data-loop/reports/factcheck-<slug>.md` (four files)
- Reviewer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-11-review.md`
