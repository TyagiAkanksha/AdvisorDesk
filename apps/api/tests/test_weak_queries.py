"""`weak_queries` + `report_weak_queries` pins (phase-9 task-15, DESIGN §D).

Seeding mirrors `tests/test_content_gaps.py`'s helpers: every `chat_messages` row gets an EXPLICIT
`created_at`, so the §6 "next assistant reply by created_at" pairing and the `days` window are
both deterministic instead of racing the server clock. Each question gets its OWN `ChatSession`
unless a test is specifically about several turns in one session, so "next reply" is never
ambiguous.

`top_similarity` is Postgres `REAL` (single precision). Every similarity assertion below still
uses `pytest.approx` as a defensive habit, but the two exact band-edge VALUES (`0.35`, `0.60`) are
now pinned directly, not merely approached: fix round 1 (Opus review of `0c5b509`, finding M-1)
found that an earlier version of this paragraph's claim — that a stored `0.4` reads back as
`0.4000000059604645`, offered as the reason to never assert a boundary exactly — was factually
wrong. Measured against this file's own `db_session` throwaway-schema fixture: Postgres `REAL`
round-trips `0.35`/`0.4`/`0.6` through psycopg EXACTLY (shortest-round-trip text representation),
so the two boundary tests below are a real regression guard, not an approximation.

Controller addition (2026-09-12, folded into this RED pass by the test-author per dispatch
brief): `retrieval_found` alone cannot see the case where retrieval cleared the threshold but the
ANSWERER declined anyway (task 05c eval data's most interesting weak query). `weak_queries` must
also read the stored assistant answer text: a row whose answer DECLINES (a documented REPORTING
heuristic — casefolded substring match on the canonical refusal phrasing, PRD §7.4 / `app.rag.
synthesis.SYSTEM_PROMPT`; NOT a judge call, which stays in the eval harness) is classified
`near_miss` when `retrieval_found` is `True` and `refused` when it is `False` — ahead of
`low_confidence`, behind `negative_feedback`. `_ask`'s new `content` parameter (default `"reply"`,
so every pin above this addition is unaffected) lets the declining-answer tests below pass
`_DECLINE_TEXT` as the stored answer text.

Fix round 1 (Opus review of `0c5b509`, findings I-2/I-3) narrowed WHERE and WHAT that substring
probe matches, after the review found the original ("no published guidance covers this", anywhere
in the answer) both under- and over-matched real recorded output: two of three refusal sentences
task 14 actually recorded from the real answerer did not contain that exact phrase (I-2), and a
substantive, well-cited answer that only HEDGES with the phrase as a closer matched anyway (I-3,
"prompt bleed"). The probe now matches the shorter phrase "no published guidance" against only the
answer's FIRST SENTENCE (see `app.services.chat._first_sentence_prefix`) — every recorded refusal
OPENS with the phrase, while a hedging closer never does. `_DECLINE_TEXT_*` constants below cover
the recorded refusal shapes; `_HEDGING_CLOSER_TEXT` covers the prompt-bleed shape.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.agent.loop import SYSTEM_PROMPT
from app.mcp.runtime import call_tool, list_tool_schemas
from app.models import ChatMessage, ChatSession, User
from app.services.chat import (
    LOW_CONFIDENCE,
    NEAR_MISS,
    NEGATIVE_FEEDBACK,
    REFUSED,
    WEAK_QUERY_KINDS,
    content_gaps,
    weak_queries,
)
from app.services.errors import ToolInputError
from app.services.eval_policy import (
    LOW_CONFIDENCE_BAND,
    NEAR_MISS_BAND,
    PROPOSAL_KIND_BY_CAUSE,
    PROPOSAL_KINDS,
    PROPOSAL_STATUSES,
)

_THRESHOLD = 0.5

# Controller addition: the canonical refusal phrasing, verbatim as the real answerer emits it
# (PRD §7.4, `app.rag.synthesis.SYSTEM_PROMPT`, and every `ScriptedChatLLM` fixture across
# `tests/test_groundedness.py`/`tests/test_eval_refusal_semantics.py`/etc.). Detection is a
# casefolded SUBSTRING match against this text's first sentence — see the module docstring.
_DECLINE_TEXT = "No published guidance covers this. Please ask the advisory team."

# Fix round 1 (Opus review I-2): two of the three refusal sentences task 14's persisted harness
# run actually recorded from the real answerer, verbatim (`task-14-implementer.md:273-274,279`) —
# neither contains the old, longer phrase ("no published guidance covers this"), which is exactly
# the recall gap that made rung 2 miss 2 of 3 recorded refusals before this fix round.
_DECLINE_TEXT_CONTEXT_VARIANT = (
    "No published guidance in the provided context covers how much cash to set aside for "
    "taxes on stock comp."
)
_DECLINE_TEXT_WHETHER_VARIANT = (
    "No published guidance covers whether exercising early is right for you."
)

# Fix round 1 (Opus review I-3): a real, substantive, well-cited answer (task-12-review.md:224,
# "prompt bleed") that only HEDGES with the refusal phrase as its CLOSING sentence — never its
# opening. Before this fix round this false-positived as `near_miss`; scoping the probe to the
# first sentence excludes it while still catching every recorded refusal above (all of which OPEN
# with the phrase).
_HEDGING_CLOSER_TEXT = (
    "Your long-term disability policy generally replaces a portion of your base salary, "
    "subject to the policy's own cap. For more specific details about how much of your income "
    "would be replaced, it would be best to consult the advisory team, as no published "
    "guidance covers this aspect in detail."
)


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` `call_tool` takes (PRD §4.1)."""
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


def _ask(
    session: Session,
    question: str,
    *,
    found: bool | None,
    top_similarity: float | None,
    feedback: int | None = None,
    ago: timedelta = timedelta(minutes=1),
    content: str = "reply",
) -> ChatSession:
    """Seed one user question + its next assistant reply, asked `ago` before now.

    `content` is the stored assistant ANSWER text (controller addition) — defaults to a neutral
    placeholder, matching every pin authored before that addition; the declining-answer tests
    below pass `_DECLINE_TEXT` here instead.
    """
    chat_session = ChatSession()
    session.add(chat_session)
    session.flush()
    asked_at = datetime.now(UTC) - ago
    session.add(
        ChatMessage(session_id=chat_session.id, role="user", content=question, created_at=asked_at)
    )
    session.add(
        ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=content,
            created_at=asked_at + timedelta(seconds=1),
            citations=[],
            retrieval_found=found,
            top_similarity=top_similarity,
            feedback=feedback,
        )
    )
    session.flush()
    return chat_session


# ---------------------------------------------------------------------------
# The shared constants (the import-linter ruling, Interfaces)
# ---------------------------------------------------------------------------


def test_the_shared_loop_constants_live_in_one_place_and_the_taxonomy_re_exports_them() -> None:
    """`app.eval.taxonomy` must not own a second copy of the near-miss band or the cause -> kind
    mapping: `app.services` may not import `app.eval` (import-linter), so both live in the leaf and
    the taxonomy imports them up — the same objects, not equal ones. The old import path keeps
    working, which is what leaves task 06's tests untouched."""
    from app.eval import taxonomy

    assert NEAR_MISS_BAND == pytest.approx(0.15)
    assert LOW_CONFIDENCE_BAND == pytest.approx(0.10)
    assert taxonomy.NEAR_MISS_BAND is NEAR_MISS_BAND
    assert taxonomy.PROPOSAL_KIND_BY_CAUSE is PROPOSAL_KIND_BY_CAUSE
    # The literal-keys-in-the-leaf choice is only safe because the taxonomy's own pin
    # (`tests/test_failure_taxonomy.py:104`) compares this key set to `FAILURE_CAUSES`.
    assert set(PROPOSAL_KIND_BY_CAUSE) == set(taxonomy.FAILURE_CAUSES)
    assert PROPOSAL_KINDS == ("new_article", "expand_article", "retune")
    assert PROPOSAL_STATUSES == ("proposed", "accepted", "rejected")


def test_weak_query_kinds_is_the_classification_ladder_in_order() -> None:
    assert WEAK_QUERY_KINDS == (NEGATIVE_FEEDBACK, REFUSED, NEAR_MISS, LOW_CONFIDENCE)


# ---------------------------------------------------------------------------
# Classification — one test per rung, plus the precedence
# ---------------------------------------------------------------------------


def test_thumbs_down_outranks_every_inferred_signal(db_session: Session) -> None:
    """Rule 1 beats rule 4: a well-grounded, high-similarity answer a human disliked is
    `negative_feedback`, never `low_confidence`/not-weak."""
    _ask(db_session, "Was this answer any good?", found=True, top_similarity=0.92, feedback=-1)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.kinds for group in groups] == [[NEGATIVE_FEEDBACK]]


def test_thumbs_down_on_a_refusal_is_still_negative_feedback(db_session: Session) -> None:
    """Rule 1 beats rule 2 as well — first match wins, and the human signal is first."""
    _ask(db_session, "Do you cover crypto comp?", found=False, top_similarity=0.2, feedback=-1)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEGATIVE_FEEDBACK]


def test_thumbs_up_is_not_a_weak_query(db_session: Session) -> None:
    _ask(db_session, "Great answer?", found=True, top_similarity=0.9, feedback=1)

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


def test_refusal_with_nothing_close_is_refused(db_session: Session) -> None:
    """Rule 2: 0.30 is below `threshold - NEAR_MISS_BAND` (0.35)."""
    _ask(db_session, "What about QSBS?", found=False, top_similarity=0.30)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [REFUSED]
    assert groups[0].worst_top_similarity == pytest.approx(0.30, abs=1e-6)


def test_refusal_with_no_similarity_at_all_is_refused(db_session: Session) -> None:
    """Rule 2's `None` half — an empty index reports no similarity."""
    _ask(db_session, "Anything on divorce and options?", found=False, top_similarity=None)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [REFUSED]
    assert groups[0].worst_top_similarity is None


def test_refusal_inside_the_band_is_a_near_miss(db_session: Session) -> None:
    """Rule 3 — demo beat 3: the corpus ALMOST had it, and the report says by how much."""
    _ask(db_session, "Do RSUs work differently outside the US?", found=False, top_similarity=0.40)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]
    assert groups[0].worst_top_similarity == pytest.approx(0.40, abs=1e-6)


def test_answered_just_above_the_threshold_is_low_confidence(db_session: Session) -> None:
    """Rule 4: 0.55 cleared 0.5 but not `threshold + LOW_CONFIDENCE_BAND` (0.60)."""
    _ask(db_session, "How is my ESPP discount taxed?", found=True, top_similarity=0.55)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [LOW_CONFIDENCE]


def test_a_confidently_answered_question_is_not_weak(db_session: Session) -> None:
    _ask(db_session, "When do my RSUs vest?", found=True, top_similarity=0.80)

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


def test_a_row_with_no_recorded_outcome_is_weak_only_through_feedback(
    db_session: Session,
) -> None:
    """A NULL `retrieval_found` (pre-0009 row) is neither found nor not-found — the same
    deliberate NULL handling `content_gaps` documents. Without feedback it is not weak; with a
    thumbs-down it is."""
    _ask(db_session, "An old untracked turn", found=None, top_similarity=None)
    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []

    _ask(db_session, "An old disliked turn", found=None, top_similarity=None, feedback=-1)
    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.normalized for group in groups] == ["an old disliked turn"]


def test_a_question_with_no_reply_at_all_is_never_weak(db_session: Session) -> None:
    """Same §6 pairing rule `content_gaps` relies on: no following assistant row, no row."""
    chat_session = ChatSession()
    db_session.add(chat_session)
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=chat_session.id,
            role="user",
            content="Nobody answered me",
            created_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


# ---------------------------------------------------------------------------
# Band edges (fix round 1, Opus review of `0c5b509`, finding M-1): both boundaries round-trip
# through Postgres `REAL` EXACTLY (see the module docstring) — pinned directly, not approached.
# ---------------------------------------------------------------------------


def test_the_near_miss_band_edge_is_inclusive_at_exactly_threshold_minus_band(
    db_session: Session,
) -> None:
    """Rule 3 requires `< threshold - NEAR_MISS_BAND` to be `refused`; AT exactly that value
    (0.35, not merely approaching it) the row must fall through to rule 4's `near_miss` instead —
    the `>=` in rule 4 is inclusive of this exact boundary."""
    _ask(db_session, "Exactly on the near-miss boundary?", found=False, top_similarity=0.35)

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]
    assert groups[0].worst_top_similarity == pytest.approx(0.35, abs=1e-6)


def test_the_low_confidence_band_edge_is_exclusive_at_exactly_threshold_plus_band(
    db_session: Session,
) -> None:
    """Rule 5 requires `< threshold + LOW_CONFIDENCE_BAND` to be `low_confidence`; AT exactly that
    value (0.60, not merely approaching it) the row is no longer weak at all — the `<` in rule 5
    excludes this exact boundary."""
    _ask(db_session, "Exactly on the low-confidence boundary?", found=True, top_similarity=0.60)

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


# ---------------------------------------------------------------------------
# Declining-answer detection (controller addition, 2026-09-12): `retrieval_found` alone cannot
# see the case where retrieval cleared the threshold but the ANSWERER declined anyway. See the
# module docstring for the exact rule and its ladder position.
# ---------------------------------------------------------------------------


def test_declining_answer_with_high_similarity_is_a_near_miss(db_session: Session) -> None:
    """The motivating case (task 05c eval data): retrieval fully cleared the threshold on a
    nearly-relevant chunk (0.92 — comfortably above `threshold + LOW_CONFIDENCE_BAND` = 0.60, so
    not weak AT ALL under the plain four-rung table) and the answerer declined anyway. Without
    reading the answer text this is invisible; `weak_queries` must surface it as `near_miss`."""
    _ask(
        db_session,
        "Does the firm's guidance cover crypto-funded RSU loans?",
        found=True,
        top_similarity=0.92,
        content=_DECLINE_TEXT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]
    assert groups[0].worst_top_similarity == pytest.approx(0.92, abs=1e-6)


def test_declining_answer_beats_the_low_confidence_rule(db_session: Session) -> None:
    """Same similarity as `test_answered_just_above_the_threshold_is_low_confidence` (0.55) —
    only the answer text differs. The declining-answer rule sits ahead of `low_confidence` in the
    ladder, so this is `near_miss`, not `low_confidence`."""
    _ask(
        db_session,
        "How is my ESPP discount taxed if I moved abroad?",
        found=True,
        top_similarity=0.55,
        content=_DECLINE_TEXT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]


def test_a_non_declining_answer_at_the_same_similarity_is_still_low_confidence(
    db_session: Session,
) -> None:
    """Negative control for the test above: ordinary answer text (no decline phrase) at the
    IDENTICAL similarity falls through to the unchanged rule 4 — the new check must not
    false-positive on a real answer."""
    _ask(
        db_session,
        "How is my ESPP discount taxed?",
        found=True,
        top_similarity=0.55,
        content="Your ESPP discount is taxed as ordinary income at purchase.",
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [LOW_CONFIDENCE]


def test_declining_answer_with_nothing_retrieved_is_refused(db_session: Session) -> None:
    """The `retrieval_found=False` half of the new rule, with nothing retrieved at all."""
    _ask(
        db_session,
        "Anything on Puerto Rico Act 60 and RSUs?",
        found=False,
        top_similarity=None,
        content=_DECLINE_TEXT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [REFUSED]


def test_a_declining_answer_does_not_override_the_not_found_band_rules(
    db_session: Session,
) -> None:
    """CONTROLLER RULING (2026-09-12), amending this pin: the declining-answer rule applies ONLY
    when `retrieval_found` is `True` — retrieval cleared the threshold and the answerer still
    declined, which is the case `retrieval_found` alone cannot see (the demo beat). When
    `retrieval_found` is `False`, the plain similarity-band rules stand UNCHANGED: "something was
    close" (or wasn't) is information about RETRIEVAL, and a decline adds nothing there. 0.40 is
    inside the near-miss band — `test_refusal_inside_the_band_is_a_near_miss` gives `near_miss`
    for this exact (not-found) similarity via `content="reply"` — and a declining answer on the
    SAME not-found/0.40 row does not change that verdict."""
    _ask(
        db_session,
        "Do RSUs work differently outside the US?",
        found=False,
        top_similarity=0.40,
        content=_DECLINE_TEXT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]


def test_negative_feedback_still_beats_a_declining_answer(db_session: Session) -> None:
    """Rule 1 outranks the new rule too — `behind negative_feedback` per the controller
    addition."""
    _ask(
        db_session,
        "Was this refusal even correct?",
        found=True,
        top_similarity=0.92,
        content=_DECLINE_TEXT,
        feedback=-1,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEGATIVE_FEEDBACK]


def test_declining_text_on_a_null_retrieval_found_row_is_still_not_weak_without_feedback(
    db_session: Session,
) -> None:
    """Guards the Python-truthiness trap: `retrieval_found is None` is falsy, so a careless
    `near_miss if retrieval_found else refused` would wrongly catch a NULL row here too. The base
    ladder's own invariant (`test_a_row_with_no_recorded_outcome_is_weak_only_through_feedback`)
    must hold even when the stored text happens to decline."""
    _ask(
        db_session,
        "An old untracked declining turn",
        found=None,
        top_similarity=None,
        content=_DECLINE_TEXT,
    )

    assert weak_queries(db_session, days=30, threshold=_THRESHOLD) == []


def test_declining_answer_detection_is_case_insensitive(db_session: Session) -> None:
    """The substring match is casefolded, not exact-case (module docstring / controller
    addition's own wording: "casefolded substring")."""
    _ask(
        db_session,
        "Mixed-case decline probe?",
        found=True,
        top_similarity=0.55,
        content="NO PUBLISHED GUIDANCE COVERS THIS. Please ask the advisory team.",
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]


# ---------------------------------------------------------------------------
# Fix round 1 (Opus review of `0c5b509`, I-2 recall / I-3 precision): the four recorded answer
# strings the review's boundary probe and evidence table are built from. `found=True`/`sim=0.92`
# throughout — comfortably clear of every band on its own — so a `near_miss` verdict below can
# only come from decline detection, never from the similarity bands.
# ---------------------------------------------------------------------------


def test_a_recorded_refusal_missing_the_canonical_wording_is_still_a_decline(
    db_session: Session,
) -> None:
    """I-2: task 14's persisted harness run recorded this refusal sentence verbatim
    (`task-14-implementer.md:273-274`) — it does NOT contain the old, longer phrase ("no published
    guidance covers this"), which was rung 2's recall gap before this fix round."""
    _ask(
        db_session,
        "How much cash should I set aside for taxes on my stock comp?",
        found=True,
        top_similarity=0.92,
        content=_DECLINE_TEXT_CONTEXT_VARIANT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]


def test_another_recorded_refusal_missing_the_canonical_wording_is_still_a_decline(
    db_session: Session,
) -> None:
    """I-2: a second recorded real refusal sentence (`task-14-implementer.md:279`), also missing
    the old, longer phrase."""
    _ask(
        db_session,
        "Everyone at work says to exercise early. Is that right for me?",
        found=True,
        top_similarity=0.92,
        content=_DECLINE_TEXT_WHETHER_VARIANT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]


def test_the_canonical_decline_text_is_still_a_decline_after_the_first_sentence_narrowing(
    db_session: Session,
) -> None:
    """Regression pin: narrowing the probe to the first sentence (and shortening the matched
    phrase) must not stop catching the canonical wording it already caught."""
    _ask(
        db_session,
        "Does the firm's guidance cover crypto-funded RSU loans?",
        found=True,
        top_similarity=0.92,
        content=_DECLINE_TEXT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [NEAR_MISS]


def test_a_hedging_closer_later_in_the_answer_is_not_a_decline(db_session: Session) -> None:
    """I-3 ("prompt bleed", task-12-review.md:224): a real, substantive answer whose FIRST
    sentence answers the question, and whose LAST sentence merely hedges with the refusal phrase,
    must classify by the band rules — same as any other non-declining answer at this similarity
    (`test_declining_answer_beats_the_low_confidence_rule`'s negative twin,
    `test_a_non_declining_answer_at_the_same_similarity_is_still_low_confidence`) — not as a
    decline. Before this fix round the phrase alone (found anywhere in the answer) forced
    `near_miss` here; scoping the probe to the first sentence excludes it."""
    _ask(
        db_session,
        "How does long-term disability insurance work?",
        found=True,
        top_similarity=0.55,
        content=_HEDGING_CLOSER_TEXT,
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert groups[0].kinds == [LOW_CONFIDENCE]


# ---------------------------------------------------------------------------
# Grouping, ordering, limits, window
# ---------------------------------------------------------------------------


def test_grouping_folds_case_whitespace_and_trailing_punctuation(db_session: Session) -> None:
    _ask(db_session, "What about QSBS?", found=False, top_similarity=0.30, ago=timedelta(hours=3))
    _ask(db_session, "what about   qsbs", found=False, top_similarity=0.40, ago=timedelta(hours=2))
    _ask(db_session, "What about QSBS!!", found=True, top_similarity=0.55, ago=timedelta(hours=1))

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert len(groups) == 1
    group = groups[0]
    assert group.normalized == "what about qsbs"
    assert group.count == 3
    assert group.kinds == [REFUSED, NEAR_MISS, LOW_CONFIDENCE]
    assert group.worst_top_similarity == pytest.approx(0.30, abs=1e-6)
    assert [example.question for example in group.examples] == [
        "What about QSBS!!",
        "what about   qsbs",
        "What about QSBS?",
    ]
    assert [example.kind for example in group.examples] == [LOW_CONFIDENCE, NEAR_MISS, REFUSED]


def test_examples_are_capped_at_three_newest_first(db_session: Session) -> None:
    for hours in (1, 2, 3, 4):
        _ask(
            db_session,
            "Crypto comp?",
            found=False,
            top_similarity=0.2,
            ago=timedelta(hours=hours),
        )

    group = weak_queries(db_session, days=30, threshold=_THRESHOLD)[0]

    assert group.count == 4
    assert len(group.examples) == 3
    timestamps = [example.created_at for example in group.examples]
    assert timestamps == sorted(timestamps, reverse=True)


def test_groups_are_ordered_by_count_then_by_worst_similarity(db_session: Session) -> None:
    # Two asks of the same question -> highest count, listed first.
    _ask(db_session, "Mega backdoor Roth?", found=True, top_similarity=0.58, ago=timedelta(hours=5))
    _ask(db_session, "Mega backdoor Roth?", found=True, top_similarity=0.57, ago=timedelta(hours=4))
    # Single asks: the lower worst-similarity sorts first.
    _ask(db_session, "Crypto comp?", found=False, top_similarity=0.41, ago=timedelta(hours=3))
    _ask(db_session, "QSBS?", found=False, top_similarity=0.22, ago=timedelta(hours=2))
    # No similarity at all sorts first of the single asks — nothing was retrieved.
    _ask(
        db_session,
        "401k loan on employer stock?",
        found=False,
        top_similarity=None,
        ago=timedelta(hours=1),
    )

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.normalized for group in groups] == [
        "mega backdoor roth",
        "401k loan on employer stock",
        "qsbs",
        "crypto comp",
    ]


def test_limit_caps_groups_not_rows(db_session: Session) -> None:
    _ask(db_session, "QSBS?", found=False, top_similarity=0.2, ago=timedelta(hours=4))
    _ask(db_session, "QSBS?", found=False, top_similarity=0.2, ago=timedelta(hours=3))
    _ask(db_session, "Crypto comp?", found=False, top_similarity=0.3, ago=timedelta(hours=2))
    _ask(
        db_session, "Divorce and options?", found=False, top_similarity=0.4, ago=timedelta(hours=1)
    )

    groups = weak_queries(db_session, days=30, limit=2, threshold=_THRESHOLD)

    assert len(groups) == 2
    assert groups[0].normalized == "qsbs"
    assert groups[0].count == 2


def test_the_days_window_reads_on_when_the_question_was_asked(db_session: Session) -> None:
    _ask(db_session, "Old question?", found=False, top_similarity=0.2, ago=timedelta(days=40))
    _ask(db_session, "Recent question?", found=False, top_similarity=0.2, ago=timedelta(days=3))

    groups = weak_queries(db_session, days=30, threshold=_THRESHOLD)

    assert [group.normalized for group in groups] == ["recent question"]


def test_a_higher_threshold_moves_rows_up_the_ladder(db_session: Session) -> None:
    """The threshold is an argument, not a constant: the same 0.40 refusal that is a `near_miss`
    at 0.5 is a plain `refused` at 0.6 (0.40 < 0.6 - 0.15)."""
    _ask(db_session, "Non-US RSUs?", found=False, top_similarity=0.40)

    assert weak_queries(db_session, days=30, threshold=0.5)[0].kinds == [NEAR_MISS]
    assert weak_queries(db_session, days=30, threshold=0.6)[0].kinds == [REFUSED]


# ---------------------------------------------------------------------------
# `content_gaps` stayed frozen (its own 12 tests are the real guard)
# ---------------------------------------------------------------------------


def test_content_gaps_still_sees_only_uncovered_turns_after_the_extraction(
    db_session: Session,
) -> None:
    _ask(db_session, "Refused one?", found=False, top_similarity=0.2, ago=timedelta(hours=2))
    _ask(db_session, "Answered one?", found=True, top_similarity=0.55, ago=timedelta(hours=1))

    gaps = content_gaps(db_session, days=30, limit=20)

    assert [gap.question for gap in gaps] == ["Refused one?"]
    # ...while the weak-query report sees BOTH, which is the point of this task.
    assert len(weak_queries(db_session, days=30, threshold=_THRESHOLD)) == 2


# ---------------------------------------------------------------------------
# The MCP tool
# ---------------------------------------------------------------------------


def test_report_weak_queries_tool_returns_classified_groups(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """Happy path through `call_tool`, with the default `Settings.similarity_threshold` (0.5):
    JSON-able payload, ISO `asked_at`, the threshold it classified against."""
    _ask(db_session, "Non-US RSUs?", found=False, top_similarity=0.40)

    result = call_tool("report_weak_queries", {}, session=db_session, actor_id=actor_id)

    assert result["count"] == 1
    assert result["threshold"] == pytest.approx(0.5)
    group = result["weak_queries"][0]
    assert group["normalized_question"] == "non-us rsus"
    assert group["count"] == 1
    assert group["kinds"] == [NEAR_MISS]
    assert group["worst_top_similarity"] == pytest.approx(0.40, abs=1e-6)
    example = group["examples"][0]
    assert example["question"] == "Non-US RSUs?"
    assert example["kind"] == NEAR_MISS
    assert isinstance(example["asked_at"], str)
    datetime.fromisoformat(example["asked_at"])


def test_report_weak_queries_tool_rejects_bad_arguments(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """§9 floor, same as `report_content_gaps`: a negative window and an unknown argument both
    fail as a named `ToolInputError` before the service is reached."""
    with pytest.raises(ToolInputError, match="days"):
        call_tool("report_weak_queries", {"days": 0}, session=db_session, actor_id=actor_id)
    with pytest.raises(ToolInputError, match="threshold"):
        call_tool("report_weak_queries", {"threshold": 0.9}, session=db_session, actor_id=actor_id)


def test_report_weak_queries_is_registered_with_a_description_and_schema() -> None:
    """Needs no DB: the registry is module state."""
    by_name = {entry["name"]: entry for entry in list_tool_schemas()}

    assert "report_weak_queries" in by_name
    assert "report_content_gaps" in by_name
    assert len(by_name) == 10
    entry = by_name["report_weak_queries"]
    assert "near_miss" in entry["description"]
    assert set(entry["inputSchema"]["properties"]) == {"days", "limit"}


def test_system_prompt_tells_the_agent_the_weak_query_report_exists() -> None:
    """Keyword-based, like `tests/test_agent_loop.py`'s own prompt pins — and true by
    construction now: the tool is registered (the clause the final review removed was a lie only
    because no such tool existed then)."""
    lower = SYSTEM_PROMPT.lower()

    assert "report_weak_queries" in lower
    assert "report_content_gaps" in lower
