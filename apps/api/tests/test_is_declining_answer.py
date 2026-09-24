"""RED (test-author) pins for `app.services.chat.is_declining_answer` (cw t01).

Task brief: docs/plans/chat-warmth/task-01-refusal-flag.md, "RED (test-author)" section.
Global constraints: .superpowers/sdd/chat-warmth/global-constraints.md — a refusal's FIRST
SENTENCE contains "no published guidance" (casefolded substring, `_DECLINE_PHRASE`); "Hi! No
published guidance..." is NOT a refusal (the opener trap task 02's prompt must respect).

`is_declining_answer` does not exist yet — only the private `_is_declining_answer` does
(`apps/api/app/services/chat.py:427`). This import is expected to fail (RED, `ImportError`) until
the implementer renames it to the public name the brief's Interfaces block pins:

    def is_declining_answer(answer: str) -> bool: ...   # same body as today's _is_declining_answer

No fakes/DB needed — pure function, no `TEST_DATABASE_URL` required to run this file.
"""

from __future__ import annotations

from app.services.chat import is_declining_answer


def test_public_heuristic_accepts_the_prompted_refusal_opener() -> None:
    """A realistic, paraphrased refusal opener (still opening with the decline phrase) is a
    decline — the heuristic's core positive case."""
    answer = (
        "No published guidance covers this yet, so I can't answer it here — the advisory team "
        "would be the right people to ask."
    )
    assert is_declining_answer(answer) is True


def test_a_greeting_before_the_decline_phrase_is_not_a_decline() -> None:
    """The decline phrase appearing only in the SECOND sentence (a greeting opens instead) is NOT
    a decline — documents the opener trap task 02's warm-prompt system message must respect."""
    answer = "Hi! No published guidance covers this."
    assert is_declining_answer(answer) is False


def test_small_talk_reply_is_not_a_decline() -> None:
    """A small-talk reply that never mentions the decline phrase at all is NOT a decline."""
    answer = (
        "Hi! I answer questions from the firm's published articles — what would you like to know?"
    )
    assert is_declining_answer(answer) is False
