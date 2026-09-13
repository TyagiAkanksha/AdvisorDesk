"""RED (phase-9 task-05d, test-author): `split_sentences` survives an abbreviation period
(ruling 1) and the answerer's `SYSTEM_PROMPT` gets an "answered question" closer that forbids a
gratuitous advisory-team suggestion (ruling 2).

Task brief: `.superpowers/sdd/phase-9-eval-data-loop/task-05d-brief.md`. Ruling 1's own
"Algorithm" section is the spec under test — this file's expected values were worked out by hand
against that exact algorithm (split on the existing boundary regex, then merge piece *i* into
piece *i-1* when either piece *i-1* ends in an abbreviation/initialism period or piece *i* opens
lowercase/digit, then apply the pre-existing 05b letter-less-fragment drop) and cross-checked with
a standalone script implementing that same algorithm. `split_sentences` (`app/eval/metrics.py`)
does not implement the merge step yet, so every test below marked "genuinely RED" fails now.

Three rows are labelled "regression pin from 05b" in the brief's own table (the `$25,000`/`2026`
row, the `Step 1.` row, and the ordinal-list-marker row) plus the empty-input row — none of these
four exercise the new merge step (no abbreviation/initialism ending, no lowercase/digit-initial
following piece, or the early empty-string guard), so they already pass under the current
splitter and must keep passing once the ruling-1 fix lands; they are authored here as guards, not
as new-behaviour RED cases.

`SYSTEM_PROMPT` (`app/rag/synthesis.py`) does not yet contain ruling 2's closer sentence, so that
test is genuinely RED.
"""

from __future__ import annotations

from app.eval.metrics import split_sentences
from app.rag.synthesis import SYSTEM_PROMPT
from app.services.chat import _DECLINE_PHRASE

# --- Ruling 1: split_sentences survives an abbreviation period ---------------


def test_split_sentences_survives_a_vs_abbreviation() -> None:
    """Table row 1. Evidence (persisted run `wave1-c`): the current splitter cuts "An ISO vs."
    away from "an NSO...", and a fragment like "vs" can never be supported by any chunk. Genuinely
    RED now: the current splitter (no merge step) returns 3 pieces for this input, not 2.
    """
    result = split_sentences("An ISO vs. an NSO is taxed differently. Both are options.")

    assert len(result) == 2
    assert "vs" not in result
    assert "vs." not in result


def test_split_sentences_survives_a_us_initialism() -> None:
    """Table row 2 (the brief gives the exact expected list for this row). Genuinely RED now:
    the current splitter returns `["The U.S.", "rules apply.", "Germany does not."]` (3 pieces),
    not the 2-sentence merge below — "U.S" matches the initialism pattern
    `^(?:[A-Za-z]\\.)+[A-Za-z]$` after its one trailing period is stripped.
    """
    result = split_sentences("The U.S. rules apply. Germany does not.")

    assert result == ["The U.S. rules apply.", "Germany does not."]


def test_split_sentences_survives_an_eg_abbreviation() -> None:
    """Table row 3. Genuinely RED now: the current splitter's first piece is bare "Consider e.g."
    (no "RSUs" in it) — merging requires "e.g" (the brief's `_ABBREVIATIONS` entry) to be
    recognised as piece 0's trailing abbreviation.
    """
    result = split_sentences("Consider e.g. RSUs and ESPP shares. Then decide.")

    assert len(result) == 2
    assert "e.g. RSUs" in result[0]


def test_split_sentences_survives_a_no_abbreviation_before_a_topic_number() -> None:
    """Table row 4 (the `_ABBREVIATIONS` entry `"no"`, from "Topic No. 409" — not the initialism
    branch, since "No" alone has no internal dot to match `^(?:[A-Za-z]\\.)+[A-Za-z]$`). Genuinely
    RED now: the current splitter's first piece is bare "See Topic No." (no "409" in it).
    """
    result = split_sentences("See Topic No. 409 for the holding period. It is one year.")

    assert len(result) == 2
    assert "No. 409" in result[0]


def test_split_sentences_leaves_a_dollar_amount_boundary_alone() -> None:
    """Table row 5, regression pin from 05b: "$25,000" is not an abbreviation/initialism and the
    next piece ("It") is capitalised, so neither merge clause fires — the three sentences must
    stay exactly as 05b already produced them. Passes now and must keep passing after the fix.
    """
    result = split_sentences("The limit is $25,000. It was set in 2026. Next year may differ.")

    assert result == [
        "The limit is $25,000.",
        "It was set in 2026.",
        "Next year may differ.",
    ]


def test_split_sentences_keeps_a_list_marker_attached_to_its_own_sentence() -> None:
    """Table row 6, regression pin from 05b: "Step 1." was never split apart from "Sell." (the
    marker opens its own sentence rather than splitting off into its own fragment) and neither
    merge clause fires ("1" is not an abbreviation/initialism; "Sell" is capitalised). Passes now
    and must keep passing after the fix.
    """
    result = split_sentences("Step 1. Sell.")

    assert result == ["Step 1.", "Sell."]


def test_split_sentences_drops_bare_ordinal_markers_not_abbreviation_fragments() -> None:
    """Table row 7, regression pin from 05b: no returned sentence is the bare marker "1." or
    "2." — "1." stays attached to "Two options:" (never split off on its own), and 05b's
    letter-less-fragment rule already drops the bare "2." the boundary regex splits off by
    itself. Passes now (05b already guarantees this) and must keep passing once ruling 1 is
    layered on top.
    """
    result = split_sentences("Two options: 1. Sell at vest. 2. Hold the shares.")

    assert "1." not in result
    assert "2." not in result


def test_split_sentences_pins_the_digit_initial_merge_case() -> None:
    """Table row 8. Controller ruling (p9 t05d, post-implementation review): the brief's original
    rule 2 had a second clause merging on EITHER a lowercase-initial OR a digit-initial following
    piece; the digit branch was dropped, since it only ever did harm where it could fire -- it
    glued the bare ordinal marker onto its neighbour in table row 7 (breaking the 05b pin that
    "Sell at vest." stays its own sentence), and it swallowed the genuine boundary in this row
    ("Pay it. 0.75% per year applies.", where the brief's own table already called for 2
    sentences). Every case the digit branch was meant for ("vs. 2026", "No. 409") is already
    covered by the abbreviation/initialism clause.

    With the digit branch gone: step 1 splits this input into exactly two pieces (`["Pay it.",
    "0.75% per year applies."]` -- the internal period inside "0.75" has no following whitespace,
    so it is never a boundary). Step 2: piece 0 ("Pay it.") does not end with a known
    abbreviation/initialism ("it" is neither), and piece 1 ("0.75% per year applies.") opens with
    a digit, not a lowercase letter, so the surviving clause does not fire either. No merge --
    the two pieces stay split, matching the table's own "2 sentences" lead-in exactly, with no
    contradiction between the prose and the algorithm's actual output.
    """
    result = split_sentences("Pay it. 0.75% per year applies.")

    assert result == ["Pay it.", "0.75% per year applies."]


def test_split_sentences_returns_empty_list_for_blank_input() -> None:
    """Table row 9 -- unaffected by the ruling-1 merge step (the early `if not stripped: return
    []` guard runs before any splitting/merging). Passes now and must keep passing.
    """
    assert split_sentences("") == []
    assert split_sentences("   ") == []


# --- Ruling 2: the answered-question closer -----------------------------------


def test_system_prompt_stops_after_answering_but_keeps_the_refusal_advisory_line() -> None:
    """Ruling 2 (p9 t05d): >= 3 persisted FAIL rows (batches B and C) end with an appended,
    unsolicited "consult the advisory team"/caveat sentence on an otherwise fully-supported
    ANSWERED question -- PRD Section 7.4 reserves that suggestion for the REFUSAL path.
    `SYSTEM_PROMPT` must gain the brief's exact closer sentence (assertion a) without losing the
    pre-existing refusal instruction (assertion b), so a later edit cannot silently drop either
    clause. Genuinely RED now: assertion (a)'s sentence is not yet in `SYSTEM_PROMPT`.
    """
    assert (
        "When the context DOES answer the question, answer it and stop — do not append "
        "suggestions to contact the advisory team, caveats, or next steps that the sources do "
        "not state."
    ) in SYSTEM_PROMPT
    # Fix wave D5 (M4): imports the reporting heuristic's own constant rather than a duplicated
    # string literal, so the two cannot silently drift apart — a reworded prompt that stops
    # containing `_DECLINE_PHRASE` now fails HERE, not just in a downstream weak_queries surprise.
    assert _DECLINE_PHRASE in SYSTEM_PROMPT
    assert "advisory team" in SYSTEM_PROMPT
