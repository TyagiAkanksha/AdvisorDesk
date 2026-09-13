"""Traffic-replay pins (phase-9 task-18, DESIGN §C4). No network, no DB: a fake SSE server.

`httpx.MockTransport` (same idiom as `tests/test_embeddings_client.py`) stands in for the deployed
API, and `sleep` is injected, so the rate-limit pacing is asserted without any test actually
waiting.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import yaml
from app.eval.replay import (
    _QUESTIONS_PER_SESSION,  # test-author addition: the budget-pin's seam
    REPLAY_KINDS,
    ReplayQuestion,
    _parse_args,  # the CLI surface is a pinned seam of this task
    load_replay_questions,
    replay_question,
    run_replay,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BASE_URL = "https://api.example.test"


def _sse(*frames: tuple[str, object]) -> str:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in frames)


_ANSWER_BODY = _sse(
    ("token", {"text": "RSUs are taxed "}),
    ("token", {"text": "as ordinary income at vest."}),
    ("citations", {"citations": [{"content_id": "c-1", "title": "RSUs", "slug": "rsus"}]}),
    ("done", {"session_id": "s-1", "message_id": "m-1"}),
)

_REFUSAL_BODY = _sse(
    ("token", {"text": "I don't have published guidance on that."}),
    ("citations", {"citations": []}),
    ("done", {"session_id": "s-1", "message_id": "m-2"}),
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """A client whose "server" is `handler` — no network (same idiom as
    `tests/test_embeddings_client.py`)."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def _question(text: str = "When do my RSUs vest?", *, kind: str = "answerable") -> ReplayQuestion:
    return ReplayQuestion(question=text, persona="sam", kind=kind)


# ---------------------------------------------------------------------------
# The committed question set
# ---------------------------------------------------------------------------


def test_the_committed_replay_set_is_forty_questions_with_the_planted_gaps() -> None:
    questions = load_replay_questions(_REPO_ROOT / "seed" / "replay_questions.yaml")

    assert len(questions) == 40
    assert len({question.question for question in questions}) == 40
    by_kind: dict[str, int] = {}
    for question in questions:
        by_kind[question.kind] = by_kind.get(question.kind, 0) + 1
    assert by_kind == {"answerable": 26, "near_miss": 10, "off_domain": 4}
    assert {question.persona for question in questions} <= {"sam", "priya", "marcus", None}
    # Every planted gap (DESIGN §C2) is actually aimed at.
    near_miss_text = " ".join(q.question.lower() for q in questions if q.kind == "near_miss")
    for gap in ("outside the united states", "crypto", "divorce", "401(k)", "qsbs"):
        assert gap in near_miss_text, gap


@pytest.mark.parametrize(
    "item, fragment",
    [
        ({"persona": "sam"}, "question"),
        ({"question": "   "}, "question"),
        ({"question": "q", "kind": "bogus"}, "kind"),
        ({"question": "q", "persona": "dave"}, "persona"),
        ({"question": "q", "expected": "yes"}, "expected"),
    ],
)
def test_invalid_replay_records_raise_value_error(
    tmp_path: Path, item: dict[str, object], fragment: str
) -> None:
    path = tmp_path / "replay_questions.yaml"
    path.write_text(yaml.safe_dump([item], sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_replay_questions(path)

    assert fragment in str(excinfo.value)


def test_a_duplicate_question_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "replay_questions.yaml"
    path.write_text(
        yaml.safe_dump([{"question": "same"}, {"question": "same"}], sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_replay_questions(path)


def test_kind_defaults_to_answerable(tmp_path: Path) -> None:
    path = tmp_path / "replay_questions.yaml"
    path.write_text(yaml.safe_dump([{"question": "q"}], sort_keys=False), encoding="utf-8")

    loaded = load_replay_questions(path)

    assert loaded[0].kind == "answerable"
    assert loaded[0].kind in REPLAY_KINDS
    assert loaded[0].persona is None


# ---------------------------------------------------------------------------
# One question
# ---------------------------------------------------------------------------


def test_replay_question_records_the_event_histogram_and_message_id() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.url.path == "/api/v1/public/chat"
        return httpx.Response(200, text=_ANSWER_BODY, headers={"content-type": "text/event-stream"})

    with _client(handler) as client:
        outcome = replay_question(client, base_url=_BASE_URL, question=_question(), session_id=None)

    assert outcome.events == {"token": 2, "citations": 1, "done": 1}
    assert outcome.message_id == "m-1"
    assert outcome.session_id == "s-1"
    assert outcome.citation_count == 1
    assert outcome.error is None
    assert seen == [{"message": "When do my RSUs vest?"}]


def test_replay_question_sends_a_known_session_id_so_no_new_session_is_charged() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text=_ANSWER_BODY, headers={"content-type": "text/event-stream"})

    with _client(handler) as client:
        replay_question(client, base_url=_BASE_URL, question=_question(), session_id="s-1")

    assert bodies == [{"message": "When do my RSUs vest?", "session_id": "s-1"}]


def test_a_refusal_is_recorded_as_zero_citations_not_as_a_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=_REFUSAL_BODY, headers={"content-type": "text/event-stream"}
        )

    with _client(handler) as client:
        outcome = replay_question(
            client,
            base_url=_BASE_URL,
            question=_question("Does QSBS apply to me?", kind="near_miss"),
            session_id=None,
        )

    assert outcome.citation_count == 0
    assert outcome.error is None
    assert outcome.message_id == "m-2"


def test_an_error_event_is_recorded_and_does_not_raise() -> None:
    body = _sse(("error", {"error": {"code": "rate_limited", "message": "Slow down."}}))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    with _client(handler) as client:
        outcome = replay_question(client, base_url=_BASE_URL, question=_question(), session_id=None)

    assert outcome.error == "Slow down."
    assert outcome.message_id is None
    assert outcome.events == {"error": 1}


def test_a_non_2xx_response_is_recorded_and_does_not_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "rate_limited", "message": "Nope."}})

    with _client(handler) as client:
        outcome = replay_question(client, base_url=_BASE_URL, question=_question(), session_id=None)

    assert outcome.error is not None
    assert "429" in outcome.error
    assert outcome.message_id is None


# ---------------------------------------------------------------------------
# The whole run: session batching + pacing
# ---------------------------------------------------------------------------


def test_run_replay_opens_one_session_per_batch_and_reuses_it_within_the_batch() -> None:
    bodies: list[dict[str, object]] = []
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        counter["n"] += 1
        body = _sse(
            ("token", {"text": "ok"}),
            ("citations", {"citations": []}),
            ("done", {"session_id": f"s-{counter['n'] // 3}", "message_id": f"m-{counter['n']}"}),
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    questions = [_question(f"Question {index}?") for index in range(6)]
    slept: list[float] = []

    with _client(handler) as client:
        report = run_replay(
            client,
            base_url=_BASE_URL,
            questions=questions,
            questions_per_session=3,
            rate_per_min=60.0,
            sleep=slept.append,
        )

    # Requests 1 and 4 start a session; 2, 3, 5, 6 resend the id their batch's `done` returned.
    assert [("session_id" in body) for body in bodies] == [False, True, True, False, True, True]
    assert report.sessions_used == 2
    assert len(report.outcomes) == 6
    assert report.event_totals == {"token": 6, "citations": 6, "done": 6}
    assert report.refusals == 6
    assert report.failures == 0
    # Paced BETWEEN requests only: five gaps for six questions, 60/60 = 1.0s each.
    assert slept == [1.0, 1.0, 1.0, 1.0, 1.0]


def test_run_replay_starts_a_fresh_session_after_a_turn_that_returned_no_id() -> None:
    """A failed turn leaves the batch with no session id to resend — the next request must omit it
    rather than send `None`."""
    bodies: list[dict[str, object]] = []
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": {"code": "x", "message": "boom"}})
        body = _sse(("done", {"session_id": "s-9", "message_id": "m-9"}))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    with _client(handler) as client:
        report = run_replay(
            client,
            base_url=_BASE_URL,
            questions=[_question("a?"), _question("b?")],
            questions_per_session=10,
            rate_per_min=60.0,
            sleep=lambda _seconds: None,
        )

    assert [("session_id" in body) for body in bodies] == [False, False]
    assert report.failures == 1


def test_rate_is_requests_per_minute_and_the_cli_refuses_to_exceed_the_public_cap() -> None:
    args = _parse_args(["--base-url", _BASE_URL])
    assert args.rate == pytest.approx(8.0)
    assert args.base_url == _BASE_URL

    with pytest.raises(SystemExit):
        _parse_args(["--base-url", _BASE_URL, "--rate", "60"])
    with pytest.raises(SystemExit):
        _parse_args(["--base-url", _BASE_URL, "--rate", "0"])
    with pytest.raises(SystemExit):
        _parse_args([])


# ---------------------------------------------------------------------------
# Test-author additions — gaps in the task file's own authored-test block above (controller
# dispatch for task-18 test-author, three explicit pins the block did not yet cover). Kept in
# their own section, below the verbatim block, so the two are easy to tell apart on review.
# ---------------------------------------------------------------------------


def test_a_stream_that_ends_without_done_is_recorded_as_incomplete_not_an_error() -> None:
    """A stream that stops (e.g. a dropped connection) after some `token` events but never sends
    `done` — and never sends an `error` event either — must not crash the run and must not be
    confused with a genuine `error` event: `QuestionOutcome.error` is populated only by an
    `error` event's message or a transport failure's text (module docstring), neither of which
    happened here. It is simply incomplete: no `message_id`, no `session_id`, no citations.
    """
    body = _sse(("token", {"text": "partial answer, then the connection drops"}))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    with _client(handler) as client:
        outcome = replay_question(client, base_url=_BASE_URL, question=_question(), session_id=None)

    assert outcome.events == {"token": 1}
    assert outcome.message_id is None
    assert outcome.session_id is None
    assert outcome.citation_count is None
    assert outcome.error is None


def test_the_cli_accepts_a_questions_path_override() -> None:
    """`--questions` (the task file's Interfaces section, CLI block) must actually be wired to
    `argparse`, not merely documented — pinned separately from the `--rate`/`--base-url` coverage
    above."""
    args = _parse_args(["--base-url", _BASE_URL, "--questions", "/tmp/q.yaml"])

    assert args.questions == Path("/tmp/q.yaml")
    assert args.base_url == _BASE_URL


def test_the_committed_batch_size_keeps_session_creates_within_the_public_daily_caps() -> None:
    """The task file's traffic-budget ruling: the public per-IP caps are RATE_LIMIT_PER_DAY=50 and
    SESSION_CREATE_PER_DAY=20 (`infra/deploy/VERIFY.md` §"Before you start"), and the replay must
    stay inside both **by construction** — the committed 40-question set, batched
    `_QUESTIONS_PER_SESSION` (10) at a time, needs only 4 session-creates. Assert the exact
    numbers, not a vague "comfortably under the cap": if a future edit changed the batch size or
    grew the committed question count past the caps, this fails with the arithmetic that broke.
    """
    questions = load_replay_questions(_REPO_ROOT / "seed" / "replay_questions.yaml")
    sessions_needed = math.ceil(len(questions) / _QUESTIONS_PER_SESSION)

    assert len(questions) == 40
    assert _QUESTIONS_PER_SESSION == 10
    assert sessions_needed == 4
    assert sessions_needed <= 20  # SESSION_CREATE_PER_DAY
    assert len(questions) <= 50  # RATE_LIMIT_PER_DAY
