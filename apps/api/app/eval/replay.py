"""Traffic replay against a DEPLOYED AdvisorDesk (phase-9 DESIGN §C4).

Streams `seed/replay_questions.yaml` through `POST /api/v1/public/chat` as an ordinary client
would, recording each question's SSE event histogram, its `message_id` and how many citations came
back — so the weak-query report (`report_weak_queries`, task 15) is built from real traffic before
the 2026-09-24 talk instead of questions typed live on stage.

It is an HTTP CLIENT, not a test double: no `TestClient`, no DB access, no `Settings`. The only
seam is the `httpx.Client` (so the unit test drives a fake SSE transport with no network).

RATE SAFETY (task file ruling, corrected against the real limiter — see
`apps/api/app/routes/ratelimit.py`'s own docstring): the task file's traffic-budget ruling frames
all three public §9 caps as "per IP", but only two of the three actually are.
`RATE_LIMIT_PER_MIN` (10) and `SESSION_CREATE_PER_DAY` (20) are per IP; `RATE_LIMIT_PER_DAY` (50)
is scoped per SESSION, not per IP (confirmed by `infra/deploy/VERIFY.md`'s "Before you start"
section too, which documents only the two per-IP caps by name and never mentions the third). A 429
writes no `chat_messages` row, so tripping any cap would silently under-report exactly the data
this script exists to create. Hence, by construction:

- `--rate` is requests per MINUTE and refuses anything above `_MAX_RATE_PER_MIN` (9.0), safely
  under the per-IP `RATE_LIMIT_PER_MIN` cap of 10.
- Questions are batched `_QUESTIONS_PER_SESSION` (10) at a time, with only the first of each batch
  omitting `session_id` — every later request resends the id the `done` event returned, which is
  what keeps session-creates low instead of one per question (`will_mint` ->
  `reserve_session_create` in `app/routes/public_routes.py`). The committed 40-question set needs
  only 4 session-creates, safely under the per-IP `SESSION_CREATE_PER_DAY` cap of 20.
- What actually keeps a run inside `RATE_LIMIT_PER_DAY` (50, per SESSION) is that no single
  session's batch size (10) comes close to it — not that a whole run's question count stays under
  50, which would be reasoning about a per-IP daily bucket that does not exist in the real limiter.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

from app.seed_paths import seed_data_dir

_DEFAULT_QUESTIONS_PATH = seed_data_dir() / "replay_questions.yaml"
_QUESTIONS_PER_SESSION = 10
_MAX_RATE_PER_MIN = 9.0
_DEFAULT_RATE_PER_MIN = 8.0
_REQUEST_TIMEOUT_SECONDS = 90.0  # matches probe.yml's `--max-time 90` for one grounded answer
_CHAT_PATH = "/api/v1/public/chat"

REPLAY_KINDS: frozenset[str] = frozenset({"answerable", "near_miss", "off_domain"})
REPLAY_PERSONAS: frozenset[str] = frozenset({"sam", "priya", "marcus"})
REQUIRED_KEYS: frozenset[str] = frozenset({"question"})
OPTIONAL_KEYS: frozenset[str] = frozenset({"persona", "kind"})


@dataclass(frozen=True)
class ReplayQuestion:
    """One parsed, validated `seed/replay_questions.yaml` record."""

    question: str
    persona: str | None
    kind: str


@dataclass(frozen=True)
class QuestionOutcome:
    """What one replayed question actually did."""

    question: str
    kind: str
    persona: str | None
    session_id: str | None  # the id the server used for this turn (from `done`)
    message_id: str | None  # None iff no `done` event arrived
    events: dict[str, int]  # SSE event histogram, e.g. {"token": 42, "citations": 1, "done": 1}
    citation_count: int | None  # None iff no `citations` event arrived
    error: str | None  # an `error` event's message, or a transport failure's text


@dataclass(frozen=True)
class ReplayReport:
    outcomes: list[QuestionOutcome]
    sessions_used: int
    event_totals: dict[str, int]

    @property
    def refusals(self) -> int:
        """Turns that answered with zero citations — PRD §7.5's refusal shape."""
        return sum(
            1 for outcome in self.outcomes if outcome.error is None and outcome.citation_count == 0
        )

    @property
    def failures(self) -> int:
        """Turns that hit an `error` event or a transport failure."""
        return sum(1 for outcome in self.outcomes if outcome.error is not None)


def load_replay_questions(path: Path) -> list[ReplayQuestion]:
    """Load and validate the replay set.

    Raises:
        ValueError: not a top-level list; an item is not a mapping; `question` missing/blank;
            an unknown key; `kind` not in `REPLAY_KINDS`; `persona` not in `REPLAY_PERSONAS`;
            duplicate question text. Every message names the file and the item index, exactly like
            `app.eval.questions.load_questions`.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: replay questions file must parse to a top-level list")

    questions: list[ReplayQuestion] = []
    seen_questions: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{path}[{index}]: item is not a mapping: {item!r}")

        keys = set(item.keys())
        missing = REQUIRED_KEYS - keys
        if missing:
            raise ValueError(
                f"{path}[{index}]: item is missing required key(s) {missing}: {item!r}"
            )
        unknown = keys - REQUIRED_KEYS - OPTIONAL_KEYS
        if unknown:
            raise ValueError(f"{path}[{index}]: item has unknown key(s) {unknown}: {item!r}")

        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{path}[{index}]: 'question' must be a non-blank string")
        if question in seen_questions:
            raise ValueError(f"{path}[{index}]: duplicate question: {question!r}")
        seen_questions.add(question)

        persona = item.get("persona")
        if persona is not None and persona not in REPLAY_PERSONAS:
            raise ValueError(
                f"{path}[{index}]: 'persona' {persona!r} is not one of "
                f"{sorted(REPLAY_PERSONAS)}: {item!r}"
            )

        kind = item.get("kind", "answerable")
        if kind not in REPLAY_KINDS:
            raise ValueError(
                f"{path}[{index}]: 'kind' {kind!r} is not one of {sorted(REPLAY_KINDS)}: {item!r}"
            )

        questions.append(ReplayQuestion(question=question, persona=persona, kind=kind))
    return questions


def _strip_sse_field(line: str, prefix: str) -> str:
    """Strip `prefix` and at most one leading space — the same SSE rule the client's parser
    documents (`app/routes/sse.py`)."""
    value = line[len(prefix) :]
    return value[1:] if value.startswith(" ") else value


def _iter_sse_frames(lines: Iterable[str]) -> Iterator[tuple[str, str]]:
    """Yield `(event_name, data)` for each complete SSE frame in `lines`.

    A blank line is a frame boundary (the SSE wire format); only the `event:`/`data:` fields are
    collected — the shapes `app/routes/public_routes.py` actually sends have no `id:`/`retry:`
    lines to handle. A frame with an `event:` line but no `data:` line yields `data=""`. A trailing
    frame with no closing blank line (a stream that stops mid-frame) is still yielded once the
    iterable ends.
    """
    event_name: str | None = None
    data_lines: list[str] = []
    for line in lines:
        if line == "":
            if event_name is not None:
                yield event_name, "\n".join(data_lines)
            event_name = None
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = _strip_sse_field(line, "event:")
        elif line.startswith("data:"):
            data_lines.append(_strip_sse_field(line, "data:"))
    if event_name is not None:
        yield event_name, "\n".join(data_lines)


def _get_str(data: Mapping[str, object], key: str) -> str | None:
    """Read `data[key]` as a `str`, or `None` if absent or a different type — a malformed payload
    is ignored, never crashes the replay (module docstring)."""
    value = data.get(key)
    return value if isinstance(value, str) else None


def replay_question(
    client: httpx.Client,
    *,
    base_url: str,
    question: ReplayQuestion,
    session_id: str | None,
) -> QuestionOutcome:
    """Stream ONE question through `POST {base_url}/api/v1/public/chat`.

    Never raises for a failed turn: a non-2xx response, a transport error, or an `error` SSE event
    all come back as a `QuestionOutcome` with `error` set, so one bad question cannot abandon the
    other 39 (and the report still shows what happened).
    """
    payload: dict[str, object] = {"message": question.question}
    if session_id is not None:
        payload["session_id"] = session_id

    def _outcome(
        *,
        result_session_id: str | None = None,
        message_id: str | None = None,
        events: dict[str, int] | None = None,
        citation_count: int | None = None,
        error: str | None = None,
    ) -> QuestionOutcome:
        return QuestionOutcome(
            question=question.question,
            kind=question.kind,
            persona=question.persona,
            session_id=result_session_id,
            message_id=message_id,
            events=events if events is not None else {},
            citation_count=citation_count,
            error=error,
        )

    try:
        response = client.post(f"{base_url.rstrip('/')}{_CHAT_PATH}", json=payload)
    except httpx.HTTPError as exc:
        return _outcome(error=f"{type(exc).__name__}: {exc}")

    if not (200 <= response.status_code < 300):
        detail = response.text
        try:
            parsed_body = response.json()
        except ValueError:
            parsed_body = None
        if isinstance(parsed_body, dict):
            body_error = parsed_body.get("error")
            if isinstance(body_error, dict) and isinstance(body_error.get("message"), str):
                detail = str(body_error["message"])
        return _outcome(error=f"HTTP {response.status_code}: {detail}")

    events: dict[str, int] = {}
    result_session_id: str | None = None
    message_id: str | None = None
    citation_count: int | None = None
    error: str | None = None

    for event_name, raw_data in _iter_sse_frames(response.iter_lines()):
        events[event_name] = events.get(event_name, 0) + 1
        data: object = None
        if raw_data:
            try:
                data = json.loads(raw_data)
            except ValueError:
                data = None

        if event_name == "done" and isinstance(data, dict):
            result_session_id = _get_str(data, "session_id")
            message_id = _get_str(data, "message_id")
        elif event_name == "citations" and isinstance(data, dict):
            citations = data.get("citations")
            if isinstance(citations, list):
                citation_count = len(citations)
        elif event_name == "error" and isinstance(data, dict):
            body_error = data.get("error")
            if isinstance(body_error, dict):
                error = _get_str(body_error, "message") or "error event with no message"

    return _outcome(
        result_session_id=result_session_id,
        message_id=message_id,
        events=events,
        citation_count=citation_count,
        error=error,
    )


def run_replay(
    client: httpx.Client,
    *,
    base_url: str,
    questions: Sequence[ReplayQuestion],
    questions_per_session: int = _QUESTIONS_PER_SESSION,
    rate_per_min: float = _DEFAULT_RATE_PER_MIN,
    sleep: Callable[[float], None] = time.sleep,
) -> ReplayReport:
    """Replay `questions` in order, batching sessions and pacing requests.

    A new session starts every `questions_per_session` questions (the first question of a batch
    sends no `session_id`); inside a batch, each request resends the id the previous `done` event
    reported — and if a turn returned none (an error), the next request in that batch falls back to
    starting a new session rather than sending a `None` it does not have.

    `sleep` is injected (defaults to `time.sleep`) so the pacing is unit-testable without a test
    that actually waits: the delay between requests is `60.0 / rate_per_min`, applied BETWEEN
    requests only (never before the first or after the last).
    """
    outcomes: list[QuestionOutcome] = []
    event_totals: dict[str, int] = {}
    sessions_used = 0
    current_session_id: str | None = None
    delay_seconds = 60.0 / rate_per_min

    total = len(questions)
    for index, question in enumerate(questions):
        if index % questions_per_session == 0:
            sessions_used += 1
            current_session_id = None

        outcome = replay_question(
            client, base_url=base_url, question=question, session_id=current_session_id
        )
        outcomes.append(outcome)
        for name, count in outcome.events.items():
            event_totals[name] = event_totals.get(name, 0) + count
        current_session_id = outcome.session_id

        if index < total - 1:
            sleep(delay_seconds)

    return ReplayReport(outcomes=outcomes, sessions_used=sessions_used, event_totals=event_totals)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the replay CLI's flags (task file "CLI" section).

    `--base-url` is REQUIRED, with no default: this sends real traffic to whatever it names, and a
    default would invite an accidental prod run. `--rate` is requests per MINUTE and refuses
    anything above `_MAX_RATE_PER_MIN` (task file ruling: the public endpoint's
    `RATE_LIMIT_PER_MIN` caps at 10/minute per IP, and this replay must never be the thing that
    trips it).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Replay seed/replay_questions.yaml through the deployed public chat endpoint "
            "(phase-9 DESIGN §C4)."
        )
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help=(
            "Base URL of the deployed API, e.g. https://api.advisordesk.tyagiakanksha.com. "
            "Required, no default — this sends real traffic to whatever it names."
        ),
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=_DEFAULT_QUESTIONS_PATH,
        help="Path to a replay_questions.yaml-shaped file (default: the committed replay set).",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=_DEFAULT_RATE_PER_MIN,
        help=f"Requests per minute (default {_DEFAULT_RATE_PER_MIN}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Replay only the first N questions (a smoke run before the full replay).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the whole report as JSON to this path.",
    )
    args = parser.parse_args(argv)
    if args.rate <= 0 or args.rate > _MAX_RATE_PER_MIN:
        parser.error(
            f"--rate must be > 0 and <= {_MAX_RATE_PER_MIN}: the public endpoint's "
            "RATE_LIMIT_PER_MIN caps at 10/minute per IP, and this replay refuses to run within "
            "1/minute of that cap."
        )
    return args


def _format_events(events: Mapping[str, int]) -> str:
    """Render an event histogram as `token=2 citations=1 done=1`, in first-seen order."""
    return " ".join(f"{name}={count}" for name, count in events.items())


def _print_outcome_line(index: int, outcome: QuestionOutcome) -> None:
    """One line per question (task file CLI section): index, kind, event histogram, citation
    count, and the question text truncated to 60 chars."""
    events_summary = _format_events(outcome.events)
    citations = "-" if outcome.citation_count is None else str(outcome.citation_count)
    print(
        f"{index:>3} {outcome.kind:<11} {events_summary:<34} citations={citations} "
        f"{outcome.question[:60]}"
    )
    if outcome.error is not None:
        print(f"    error: {outcome.error}")


def _report_to_json(report: ReplayReport) -> dict[str, object]:
    """`--out`'s JSON artifact: `outcomes`, `sessions_used`, `event_totals` (task file CLI
    section)."""
    return {
        "outcomes": [
            {
                "question": outcome.question,
                "kind": outcome.kind,
                "persona": outcome.persona,
                "session_id": outcome.session_id,
                "message_id": outcome.message_id,
                "events": outcome.events,
                "citation_count": outcome.citation_count,
                "error": outcome.error,
            }
            for outcome in report.outcomes
        ],
        "sessions_used": report.sessions_used,
        "event_totals": report.event_totals,
    }


def _run_from_cli(argv: list[str] | None = None) -> None:
    """`python -m app.eval.replay`: build a real `httpx.Client`, replay `--questions` against
    `--base-url`, print one line per question plus a summary, and optionally write `--out`.
    """
    args = _parse_args(argv)
    questions = load_replay_questions(args.questions)
    if args.limit is not None:
        questions = questions[: args.limit]

    client = httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        report = run_replay(
            client, base_url=args.base_url, questions=questions, rate_per_min=args.rate
        )
    finally:
        client.close()

    for index, outcome in enumerate(report.outcomes, start=1):
        _print_outcome_line(index, outcome)
    print(
        f"replay: {len(report.outcomes)} questions, {report.sessions_used} sessions, "
        f"{report.refusals} refusals, {report.failures} failures"
    )
    print(f"event totals: {report.event_totals}")

    if args.out is not None:
        args.out.write_text(json.dumps(_report_to_json(report), indent=2), encoding="utf-8")


if __name__ == "__main__":
    _run_from_cli()
