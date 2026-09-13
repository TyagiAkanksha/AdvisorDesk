"""Shared policy constants of the evaluation / improvement loop (phase-9 DESIGN §D).

A dependency-free leaf: it imports nothing, so BOTH layers that need these values may have them.
That is the whole reason it exists. `app.services.chat.weak_queries` classifies live chat rows with
the bands and `app.services.proposals` turns a diagnosed cause into a proposal kind, while
`app.eval.taxonomy.classify_failure` classifies eval rows with the same band and the same mapping —
and the import-linter contract "app.services imports only app.models and app.config"
(`apps/api/pyproject.toml`) forbids `app.services` from importing `app.eval`, while the reverse
direction (`app.eval` -> `app.services`) is the declared-legal one (DESIGN §B1). So the constants
live at the bottom, in `app.services`, and `app.eval.taxonomy` imports them up — rather than each
layer re-typing `0.15` and drifting apart, which is exactly what task 06's own comment warned
against.

Deliberately NOT `Settings` fields (CONVENTIONS.md §5): these are definitions, not deployment
knobs. An operator who retuned the near-miss band per environment would change what "near miss"
MEANS between a recorded eval run and the weak-query report read off the same rows.
"""

from __future__ import annotations

# DESIGN §D: a refusal whose best chunk scored within this much of `similarity_threshold` is a
# `near_miss` ("the corpus almost had it"), not a `refused` ("nothing close exists"). Also row 5 of
# `app.eval.taxonomy.classify_failure`'s decision table (`corpus_gap` vs `threshold_refusal`) — the
# same boundary, by construction, because it is the same number.
NEAR_MISS_BAND: float = 0.15

# DESIGN §D: an answer that DID clear the threshold, but only just (`< threshold +
# LOW_CONFIDENCE_BAND`), is a `low_confidence` weak query — the class that makes "a bad answer is
# undetectable" (DESIGN's "Where we actually stand" table) false. Not a taxonomy input: the eval
# harness judges answers directly instead of guessing from retrieval scores.
LOW_CONFIDENCE_BAND: float = 0.10

# DESIGN "Diagnosis" row: the failure taxonomy maps 1:1 onto `content_proposals.kind`, so this
# mapping is the seam between a diagnosed eval failure (`app.eval.taxonomy.classify_failure`) and
# the proposal that fixes it (`app.services.proposals.kind_for_cause`, task 16) — two layers that
# cannot import each other, which is why it sits here. Keys are written as literals rather than
# importing `app.eval.taxonomy`'s cause constants (the same contract that put this module here
# forbids that import); `tests/test_failure_taxonomy.py`'s existing
# `set(PROPOSAL_KIND_BY_CAUSE) == set(FAILURE_CAUSES)` pin (line 104) is what keeps the two from
# drifting. `judge_disagreement` maps to `None`: the fix is judge calibration (task 08), not
# content.
PROPOSAL_KIND_BY_CAUSE: dict[str, str | None] = {
    "retrieval_miss": "retune",
    "corpus_gap": "new_article",
    "threshold_refusal": "retune",
    "generation_unfaithful": "expand_article",
    "judge_disagreement": None,
}

#: `content_proposals.kind`'s CHECK constraint, in Python (DESIGN §D / `app.models.eval`) — used by
#: task 16's `propose_content_fix` to reject a bad kind before the DB does.
PROPOSAL_KINDS: tuple[str, ...] = ("new_article", "expand_article", "retune")

#: `content_proposals.status`'s CHECK constraint, in Python.
PROPOSAL_STATUSES: tuple[str, ...] = ("proposed", "accepted", "rejected")
