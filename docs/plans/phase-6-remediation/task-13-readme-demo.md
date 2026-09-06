# Task 6R-13 — README demo walkthrough (WR-18)

WR-id: WR-18. Effort M. Closes PRD §10's definition-of-done: "a stranger can follow the README, run
the demo script end to end." This is a DOCS/WRITING task — author → reviewer (no test-author; the
"tests" are the live-verified commands the author must actually run). Independent of all other work.

## Goal

A `## Demo` section in `README.md` (placed after "Dev quickstart", before "Gates") that walks a
newcomer through the actual product end-to-end, anchored on the REAL seeded corpus and eval
questions — not invented examples. Every copy-pasteable command must be verified to actually work.

## What the demo must cover (maps to PRD §2.2 user stories)

**Client story (public, no auth — fully scriptable):**
1. Browse published content: `GET /api/v1/public/content` returns the 17 published articles.
2. Ask a grounded question and get a cited, streamed answer. Use a REAL answerable eval question from
   `seed/eval_questions.yaml`, e.g. "What is a Roth IRA conversion and how is it taxed?" (expected
   source slug `roth-ira-conversion-basics`). Show the SSE `POST /api/v1/public/chat` call and that
   the response streams token events + a citation to that article.
3. Ask an UNANSWERABLE question (pick a real `answerable: false` entry from eval_questions.yaml) and
   show the refusal + empty citations (`retrieval_found=false`) — the "does not answer from general
   knowledge" guarantee.

**Admin story (needs allowlisted Google sign-in — UI steps, not curl):**
4. Sign in (allowlisted Google email), see the content dashboard (status/tags/updated).
5. Open the agent panel and issue the three §2.2 example commands verbatim — at minimum
   "How many published pieces do we have on tax planning?" (agent calls `count_content`, reports 8)
   and "Draft an article on Roth IRA conversion basics and tag it retirement." (agent calls
   `create_draft`; dashboard refreshes, draft count goes up). Note the panel renders each tool call live.

## Two run paths — make both explicit

- **Run it yourself (local):** builds on the existing "Dev quickstart" (compose up + migrate + seed).
  Note the prerequisites the demo actually needs: `NVIDIA_API_KEY` for the client chat path (required),
  and Google OAuth + an allowlisted `ADMIN_EMAILS` for the admin story (point back at quickstart step 1;
  be honest that a stranger must supply their own OAuth app for the admin half).
- **See it live:** the deployed site (client `https://advisordesk.tyagiakanksha.com`, admin
  `https://admin.advisordesk.tyagiakanksha.com`). The client browse+ask path is public and works
  against the live site; the admin story needs an allowlisted account (owner's).

## Constraints

- The client-path commands (browse, answerable ask, unanswerable ask) MUST be run and verified —
  against the live client origin (public, easiest) OR a local compose bring-up. Paste real (trimmed)
  output as evidence in the report. Do NOT invent SSE output — capture it.
- Use only questions/slugs that exist in `seed/eval_questions.yaml` + `seed/sample_content/` (verify
  the slug is a published seed file). Cross-check the tax-planning count (8) against the seed tags
  before asserting it.
- Keep it copy-paste-runnable and honest about auth barriers; no secret values.
- Do not touch app code. Path-scoped `git add` of exactly `README.md` (+ a `scripts/demo.sh` ONLY if
  you add one for the client-path curls — optional, keep it simple). Owner's tree is otherwise clean now.
- Commit `docs(readme): end-to-end demo walkthrough closing PRD §10 definition-of-done (6R-13, WR-18)`
  + the standard Co-Authored-By/Claude-Session trailer.

## Acceptance

The `## Demo` section exists, is anchored on real seeded content, covers both user stories and both
run paths, and every client-path command has been executed with captured output. A reviewer confirms
a stranger could follow it end-to-end and that no example is fabricated.
