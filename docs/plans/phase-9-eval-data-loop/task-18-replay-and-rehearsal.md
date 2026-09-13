---
id: p9-t18
phase: phase-9-eval-data-loop
depends_on: [p9-t13, p9-t14, p9-t16, p9-t17]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 18 — Traffic replay, the rehearsed "rejected its own fix", and the run sheet

## Goal

The last task is about **evidence on the day**. Three deliverables:

1. **Replay** (DESIGN §C4) — `python -m app.eval.replay` streams ~40 persona questions (a subset
   deliberately aimed at the planted gaps) through the real public chat endpoint, recording each
   question's SSE event histogram and `message_id`, so `report_weak_queries` on prod has **real
   rows** instead of a demo typed live. It respects the §9 per-IP caps by construction.
2. **The owner-gated prod steps** — publish wave 1 through MCP, verify the published count, run the
   replay, and see the near-misses come back out of `report_weak_queries` on prod. A checklist the
   owner executes; no code.
3. **The rehearsal + run sheet** — `docs/plans/phase-9-eval-data-loop/rehearsal.md`, a repeatable
   scratch-DB script that walks the whole loop twice (a clean fix that is **accepted**, and a bad
   fix that regresses two questions and is **rejected**), and
   `docs/plans/phase-9-eval-data-loop/run-sheet.md`, what the owner actually says and does on
   2026-09-24, with timings and a fallback per beat.

Demo beat 4's variant is the payload of the whole phase: *"the harness said no, so the system
rejected its own fix."* This task is where that stops being a claim.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §C4 (traffic replay), §D6 (the five beats), §"Part
  D" (the acceptance gates the rehearsal exercises), §"Verification" (the Loop and Prod bullets),
  §"Execution order" step 9.
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` §"Global Constraints", §"Whole-branch final
  review" (this task precedes it; the PR/deploy/publish order lives there).
- `docs/plans/phase-9-eval-data-loop/task-15-weak-queries.md` §Interfaces — the
  `report_weak_queries` payload (`normalized_question`, `kinds`, `worst_top_similarity`,
  `examples[].asked_at`) the prod check reads, and the four weak-query kinds.
- `docs/plans/phase-9-eval-data-loop/task-16-proposals.md` §Interfaces — `propose_content_fix` /
  `accept_proposal` / `reject_proposal` signatures, the six gates and their `blocked_by` names.
- `apps/api/app/eval/agent_suite.py:646-760` — the CLI shape to mirror (`_parse_args` with
  `required=True` flags, `_run_from_cli` building real seams, one printed line per item, a summary
  line) and its `--database-url`-is-required safety rationale.
- `apps/api/app/eval/questions.py:77-120` — `load_questions`' strict-validation style (top-level
  list, per-item mapping, required/optional key sets, `ValueError` naming the index and key) that
  `load_replay_questions` copies.
- `apps/api/app/seed_paths.py` — `seed_data_dir()`; the replay questions file resolves through it,
  never through a `parents[...]` walk.
- `apps/api/app/routes/public_routes.py` — the SSE event names and payloads the parser must handle
  (`token {text}`, `citations {citations:[...]}`, `done {session_id, message_id}`,
  `error {error:{code,message}}`) and the `will_mint` → `reserve_session_create` rule (a request
  that sends a known `session_id` does **not** charge a session-create slot).
- `apps/api/tests/test_embeddings_client.py:58-90` — the `httpx.MockTransport` idiom (a handler
  function + `httpx.Client(transport=...)`) this task's test uses for a zero-network SSE server.
- `.github/workflows/probe.yml:54-68` — the prod chat-stream probe: the exact curl flags
  (`-sS -N --max-time 90`, `Accept: text/event-stream`) and the `grep -o '^event: [a-z_]*' | sort |
  uniq -c` histogram this task's script reproduces in Python; also the env block with the three
  prod URLs.
- `infra/deploy/VERIFY.md` §"Before you start" (the three §9 caps in detail: `RATE_LIMIT_PER_MIN=10`
  sliding 60s per IP, `RATE_LIMIT_PER_DAY=50` per IP per UTC day, `SESSION_CREATE_PER_DAY=20` per IP
  per UTC day, and the "restart the api container clears the in-memory buckets" escape hatch) and
  §5 (the MCP `initialize` / bearer-token curl shapes — **never** paste a token into a file). Also
  its section numbering (`grep -n '^## ' infra/deploy/VERIFY.md` → 0 · 1 · 2 · 2b · 3 · 4 · 5 · 5a ·
  6 · 7), since this task appends the next free number, §8.
- `apps/api/app/eval/groundedness.py:1062-1175` — `_run_from_cli`: it reads `settings.database_url`
  (so the rehearsal sets `DATABASE_URL` inline per command), persists by default, and prints the
  `compare …` line for `--compare-to`.
- `apps/api/app/seed.py:260-302` — `python -m app.seed`'s requirements (`DATABASE_URL`, a real
  embedder) and its printed `seed_all: created=… published=… skipped=… chunk_count=…` line.
- `.superpowers/sdd/phase-9-eval-data-loop/global-constraints.md` — the env-extraction pattern every
  command in the docs this task writes must use.

## Files

**Create**
- `seed/replay_questions.yaml`
- `apps/api/app/eval/replay.py`
- `apps/api/tests/test_replay.py`
- `docs/plans/phase-9-eval-data-loop/rehearsal.md`
- `docs/plans/phase-9-eval-data-loop/run-sheet.md`

**Modify**
- `infra/deploy/VERIFY.md` — **one new pointer section only** (controller ruling, 2026-09-12: that
  file stays the index of deployed checks, while the steps themselves live with the phase plan).
  Append after the existing §7 (`chat_latency` visible in service logs), using the next free number
  — the file currently runs 0 · 1 · 2 · 2b · 3 · 4 · 5 · 5a · 6 · 7, so this is **§8**, not §7:

  ```markdown
  ## 8. Phase 9 loop on prod (publish wave 1 → replay → weak queries)

  The deployed steps for phase 9's evaluated/self-improving loop — publish the 16 wave-1 articles
  via MCP, verify the published count, run the traffic replay, and read `report_weak_queries` back
  — are an owner-gated checklist kept with the phase plan, not duplicated here:
  **see `docs/plans/phase-9-eval-data-loop/rehearsal.md` §4.**
  ```

  Nothing else in that file is touched (no existing section renumbered, no recorded output edited).

(No route, tool or DTO changes: the replay is an HTTP *client*. `openapi.json`, `mcp-tools.json` and
both `schema.d.ts` must be byte-identical at the end of this task.)

## Interfaces

### Ruling — the replay's traffic budget (decide-and-justify)

The public API caps per IP (`infra/deploy/VERIFY.md`): **10/minute** (sliding),
**50/day** (UTC), **20 session-creates/day**. The replay must never be the thing that trips them —
a 429 would poison exactly the data the replay exists to create (a rate-limited turn writes no
`chat_messages` rows, so the weak-query report would silently under-report), and a tripped
per-minute bucket also breaks the prod-probe workflow running on a schedule.

Therefore, by construction:

- **40 questions, batched 10 per session** → 4 session-creates (cap 20). Only the first question of
  each batch omits `session_id`; the rest resend the id the `done` event returned, which is what
  keeps session-creates at 4 instead of 40 (`will_mint` → `reserve_session_create`).
- **`--rate` is requests per MINUTE, default `8.0`**, and `_parse_args` **errors above 9.0**. The
  brief's shorthand `1/s` would be 60/min — six times the cap. A whole 40-question replay is
  therefore ~5 minutes.
- **40 of the day's 50 requests**, so the replay is run the **day before** the talk, from the
  owner's workstation, leaving demo-day budget for the demo itself. The run sheet repeats this.

### `seed/replay_questions.yaml` — schema

Top-level list; each item:

| Key | Type | Required | Meaning |
|---|---|---|---|
| `question` | str | yes | asked verbatim, exactly as a client would type it |
| `persona` | `sam` \| `priya` \| `marcus` | no (default `null`) | DESIGN §C2's personas — whose voice it is |
| `kind` | `answerable` \| `near_miss` \| `off_domain` | no (default `answerable`) | what we EXPECT; recorded, never asserted (the point is to observe what the live system does) |

26 `answerable` · 10 `near_miss` (two per planted gap: RSU/ESPP for non-US employees · crypto
compensation · options in divorce · 401(k) loans against employer stock · QSBS) · 4 `off_domain`.

### `seed/replay_questions.yaml` — write this file verbatim

```yaml
# Traffic replay set (phase-9 DESIGN §C4). ~40 realistic persona questions replayed against the
# DEPLOYED public chat endpoint before the 2026-09-24 talk, so `report_weak_queries` has real rows.
# `kind` records what we EXPECT, for reading the report afterwards — nothing asserts it: the whole
# point is to see what the live system actually does. The ten `near_miss` questions aim at DESIGN
# §C2's deliberately-unwritten planted gaps.

# --- Sam: new-grad engineer, first RSU grant, first ESPP window ----------------
- question: "My first RSU tranche vested and the tax withheld looked low. Why?"
  persona: sam
- question: "Should I sell my RSUs as soon as they vest or hold them?"
  persona: sam
- question: "My offer says my RSUs are double-trigger. What does that actually mean?"
  persona: sam
- question: "What happens to my RSUs if the company goes public?"
  persona: sam
- question: "How is the ESPP discount taxed when I sell the shares?"
  persona: sam
- question: "What makes an ESPP sale qualifying instead of disqualifying?"
  persona: sam
- question: "What is the difference between ISOs and NSOs on my grant?"
  persona: sam
- question: "How is exercising an NSO taxed?"
  persona: sam
- question: "What should I do with my 401(k) when I change jobs?"
  persona: sam
- question: "How do you charge for financial planning?"
  persona: sam

# --- Priya: senior IC at a pre-IPO startup, ISOs, tender offer, AMT ------------
- question: "Will exercising my ISOs this year trigger AMT?"
  persona: priya
- question: "If I pay AMT on an ISO exercise, do I ever get that money back?"
  persona: priya
- question: "Should I file an 83(b) election on my restricted stock?"
  persona: priya
- question: "What is the deadline for filing an 83(b) election?"
  persona: priya
- question: "Our investors are running a tender offer. Should I sell some shares?"
  persona: priya
- question: "How does an IPO lock-up period affect when I can sell?"
  persona: priya
- question: "I am early exercising my options. What are the risks?"
  persona: priya
- question: "How much of my net worth should be in my employer's stock?"
  persona: priya

# --- Marcus: staff engineer, public company, concentrated stock, maxed 401(k) --
- question: "How do I unwind a concentrated position in my employer's stock without a huge tax bill?"
  persona: marcus
- question: "What is a mega-backdoor Roth and does it work with my 401(k)?"
  persona: marcus
- question: "How much can I put into after-tax 401(k) contributions this year?"
  persona: marcus
- question: "Why would I use my HSA as a retirement account instead of spending it?"
  persona: marcus
- question: "Is it better to donate appreciated stock than to donate cash?"
  persona: marcus
- question: "I am now considered an insider. What is a 10b5-1 plan?"
  persona: marcus
- question: "If I leave before my next vest, what happens to my unvested RSUs?"
  persona: marcus
- question: "Can the wash-sale rule apply across my RSU and ESPP lots?"
  persona: marcus

# --- Planted gaps (DESIGN §C2): expected near-misses, deliberately unwritten ---
- question: "I am transferring to our Berlin office. How are my RSUs taxed once I am not a US employee?"
  persona: marcus
  kind: near_miss
- question: "Does your equity compensation guidance apply to employees outside the United States?"
  persona: sam
  kind: near_miss
- question: "Part of my compensation is paid in USDC. How is that taxed?"
  persona: priya
  kind: near_miss
- question: "My startup wants to pay my bonus in crypto. What should I watch out for?"
  persona: priya
  kind: near_miss
- question: "I am getting divorced. How are my unvested stock options split?"
  persona: marcus
  kind: near_miss
- question: "Can stock options be divided in a divorce settlement?"
  persona: marcus
  kind: near_miss
- question: "Can I borrow from my 401(k) if most of it is employer stock?"
  persona: marcus
  kind: near_miss
- question: "What happens to my 401(k) loan if my employer's stock price drops?"
  persona: marcus
  kind: near_miss
- question: "Does my startup stock qualify for QSBS?"
  persona: priya
  kind: near_miss
- question: "How long do I have to hold QSBS shares before the gain is excluded?"
  persona: priya
  kind: near_miss

# --- Off-domain: the refusal beat ---------------------------------------------
- question: "What is the weather in Charlotte tomorrow?"
  kind: off_domain
- question: "Can you recommend a good Italian restaurant near your office?"
  kind: off_domain
- question: "Who won the basketball game last night?"
  kind: off_domain
- question: "Write me a Python script that scrapes job listings."
  kind: off_domain
```

### `apps/api/app/eval/replay.py`

```python
"""Traffic replay against a DEPLOYED AdvisorDesk (phase-9 DESIGN §C4).

Streams `seed/replay_questions.yaml` through `POST /api/v1/public/chat` as an ordinary client
would, recording each question's SSE event histogram, its `message_id` and how many citations came
back — so the weak-query report (`report_weak_queries`, task 15) is built from real traffic before
the 2026-09-24 talk instead of questions typed live on stage.

It is an HTTP CLIENT, not a test double: no `TestClient`, no DB access, no `Settings`. The only
seam is the `httpx.Client` (so the unit test drives a fake SSE transport with no network).

RATE SAFETY (task file ruling): the public endpoint caps per IP at 10/minute (sliding),
50/day and 20 session-creates/day (`infra/deploy/VERIFY.md`). A 429 writes no `chat_messages` row,
so tripping a cap would silently under-report exactly the data this script exists to create.
Hence: `--rate` is requests per MINUTE and refuses anything above 9.0; questions are batched
`_QUESTIONS_PER_SESSION` at a time, with only the first of each batch omitting `session_id`
(every later request resends the id the `done` event returned, which avoids charging a
session-create slot).
"""


_DEFAULT_QUESTIONS_PATH = seed_data_dir() / "replay_questions.yaml"
_QUESTIONS_PER_SESSION = 10
_MAX_RATE_PER_MIN = 9.0
_DEFAULT_RATE_PER_MIN = 8.0
_REQUEST_TIMEOUT_SECONDS = 90.0   # matches probe.yml's `--max-time 90` for one grounded answer

REPLAY_KINDS: frozenset[str] = frozenset({"answerable", "near_miss", "off_domain"})
REPLAY_PERSONAS: frozenset[str] = frozenset({"sam", "priya", "marcus"})
REQUIRED_KEYS: frozenset[str] = frozenset({"question"})
OPTIONAL_KEYS: frozenset[str] = frozenset({"persona", "kind"})


@dataclass(frozen=True)
class ReplayQuestion:
    question: str
    persona: str | None
    kind: str


@dataclass(frozen=True)
class QuestionOutcome:
    """What one replayed question actually did."""

    question: str
    kind: str
    persona: str | None
    session_id: str | None    # the id the server used for this turn (from `done`)
    message_id: str | None    # None iff no `done` event arrived
    events: dict[str, int]    # SSE event histogram, e.g. {"token": 42, "citations": 1, "done": 1}
    citation_count: int | None   # None iff no `citations` event arrived
    error: str | None         # an `error` event's message, or a transport failure's text


@dataclass(frozen=True)
class ReplayReport:
    outcomes: list[QuestionOutcome]
    sessions_used: int
    event_totals: dict[str, int]

    @property
    def refusals(self) -> int:
        """Turns that answered with zero citations — PRD §7.5's refusal shape."""

    @property
    def failures(self) -> int:
        """Turns that hit an `error` event or a transport failure."""


def load_replay_questions(path: Path) -> list[ReplayQuestion]:
    """Load and validate the replay set.

    Raises:
        ValueError: not a top-level list; an item is not a mapping; `question` missing/blank;
            an unknown key; `kind` not in `REPLAY_KINDS`; `persona` not in `REPLAY_PERSONAS`;
            duplicate question text. Every message names the file and the item index, exactly like
            `app.eval.questions.load_questions`.
    """


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
```

**SSE parsing.** One small private helper, not a dependency: iterate `response.iter_lines()`,
treat a blank line as a frame boundary, collect `event:`/`data:` fields (strip at most one leading
space after the colon, the same SSE rule the client's parser documents), and on each completed frame
increment `events[name]` and, for `done`/`citations`/`error`, read the payload. A malformed `data:`
payload is counted in the histogram and otherwise ignored — the histogram is the primary evidence.

**CLI** — `python -m app.eval.replay --base-url https://api.advisordesk.tyagiakanksha.com
[--questions seed/replay_questions.yaml] [--rate 8] [--limit N] [--out replay-2026-09-23.json]`:

- `--base-url` is **required, no default** (this sends real traffic to whatever it names; a
  default would invite an accidental prod run).
- `--rate` is a float, requests per minute; `parser.error` when `<= 0` or `> 9.0`, with a message
  naming `RATE_LIMIT_PER_MIN`.
- `--limit` truncates the question list (a 3-question smoke run before the real one).
- `--out` writes the whole report as JSON (`outcomes`, `sessions_used`, `event_totals`) — the
  artifact pasted into the implementer report and the run sheet.
- Prints one line per question:
  `f"{index:>3} {outcome.kind:<11} {events_summary:<34} citations={...} {question[:60]}"`, then a
  summary: `replay: {n} questions, {sessions_used} sessions, {refusals} refusals, {failures}
  failures` and the event totals.
- Builds `httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS, follow_redirects=True)` itself and closes
  it in a `finally`.

## Steps (TDD)

- [ ] **RED — test-author.** Create `apps/api/tests/test_replay.py`:

```python
"""Traffic-replay pins (phase-9 task-18, DESIGN §C4). No network, no DB: a fake SSE server.

`httpx.MockTransport` (same idiom as `tests/test_embeddings_client.py`) stands in for the deployed
API, and `sleep` is injected, so the rate-limit pacing is asserted without any test actually
waiting.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import yaml

from app.eval.replay import (
    REPLAY_KINDS,
    ReplayQuestion,
    load_replay_questions,
    replay_question,
    run_replay,
)
from app.eval.replay import _parse_args  # the CLI surface is a pinned seam of this task

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
        return httpx.Response(
            200, text=_ANSWER_BODY, headers={"content-type": "text/event-stream"}
        )

    with _client(handler) as client:
        outcome = replay_question(
            client, base_url=_BASE_URL, question=_question(), session_id=None
        )

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
        return httpx.Response(
            200, text=_ANSWER_BODY, headers={"content-type": "text/event-stream"}
        )

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
        outcome = replay_question(
            client, base_url=_BASE_URL, question=_question(), session_id=None
        )

    assert outcome.error == "Slow down."
    assert outcome.message_id is None
    assert outcome.events == {"error": 1}


def test_a_non_2xx_response_is_recorded_and_does_not_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "rate_limited", "message": "Nope."}})

    with _client(handler) as client:
        outcome = replay_question(
            client, base_url=_BASE_URL, question=_question(), session_id=None
        )

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
```

- [ ] **Run RED:**
  ```sh
  export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r')"
  cd apps/api && uv run pytest tests/test_replay.py -q
  ```
  Fails at collection (`ModuleNotFoundError: app.eval.replay`), then on the missing
  `seed/replay_questions.yaml`. Paste the evidence.

- [ ] **GREEN — implementer, 1/2.** Write `seed/replay_questions.yaml` verbatim from Interfaces,
  then `app/eval/replay.py`. `uv run pytest tests/test_replay.py -q`, then `uv run pytest -q`
  (the whole suite — `tests/test_seed.py` globs only `sample_content/*.md`, so the new YAML must not
  disturb it; confirm rather than assume).

- [ ] **GREEN — implementer, 2/2.** Gates: `pnpm gates:api` (incl. `lint-imports` — `app.eval` may
  import `httpx`; it must NOT import `app.routes`/`app.factory` to reach the API).

- [ ] **Smoke run (no prod traffic yet):** three questions against prod is the cheapest proof the
  parser matches the real wire:
  ```sh
  cd apps/api && uv run python -m app.eval.replay \
    --base-url https://api.advisordesk.tyagiakanksha.com --limit 3 --out /tmp/replay-smoke.json
  ```
  Expect three lines each showing `token=…  citations=1  done=1` and `replay: 3 questions,
  1 sessions, 0 refusals, 0 failures`. Paste it. (Budget: 3 of the day's 50.)

- [ ] **Commit (code):**
  `git add apps/api/app/eval/replay.py apps/api/tests/test_replay.py seed/replay_questions.yaml`
  `git commit -m "feat(api): traffic replay against a deployed AdvisorDesk (p9 t18)"`

- [ ] **Write `docs/plans/phase-9-eval-data-loop/rehearsal.md`** — the content is specified below;
  then **run it end to end** on a scratch DB and paste the real outputs into it (every
  `(recorded …)` placeholder filled). A rehearsal nobody ran is not a rehearsal.

- [ ] **Write `docs/plans/phase-9-eval-data-loop/run-sheet.md`** — content specified below.

- [ ] **Add the `infra/deploy/VERIFY.md` pointer section** (§8, text verbatim from §Files). Confirm
      with `git diff -- infra/deploy/VERIFY.md` that the diff is purely additive at the end of the
      file: no existing section renumbered, no recorded output changed.

- [ ] **Commit (docs):**
  `git add docs/plans/phase-9-eval-data-loop/rehearsal.md docs/plans/phase-9-eval-data-loop/run-sheet.md infra/deploy/VERIFY.md`
  `git commit -m "docs(p9): loop rehearsal + 2026-09-24 run sheet (p9 t18)"`

- [ ] **Owner-gated prod steps** — the checklist below is executed by the OWNER, after the
  whole-branch review and deploy (INDEX §"Whole-branch final review"). The implementer writes the
  checklist into `rehearsal.md` §4 and stops; it is NOT run from an agent session.

## Deliverable 2 — the owner-gated prod checklist (goes in `rehearsal.md` §4)

Preconditions: PR merged, `0009` migrated, all three images deployed, `prod-probe` green.

- [ ] **0. List the 16 titles to publish.** They are whatever tasks 10-13's frontmatter says — not
      guessable at plan time, so enumerate them instead of transcribing a stale list, and paste the
      output here as the publish worklist:
      ```sh
      cd /home/ak/Documents/github_akanksha/AdvisorDesk
      git diff --name-only main...feat/eval-data-loop -- seed/sample_content \
        | sort | xargs grep -h '^title:'
      ```
      Expect 16 lines (12 equity + 4 firm, DESIGN §C2 wave 1). If the count differs, stop: the
      corpus tasks are not complete.
- [ ] **1. Publish wave 1 (16 articles).** Primary path — claude.ai's connector (verified working
      2026-09-09): open the AdvisorDesk connector and, for each file from step 0, ask it to
      `create_draft` with that file's frontmatter `title`/`tags` and body, then `publish` the
      returned id. Do it in batches of four (one per authoring task) and read back the ids.
      Fallback path — bearer token, from a workstation shell (VERIFY.md §5's shapes; **never paste
      the token into any file**):
      ```sh
      export MCP_TOKEN=<minted per infra/deploy/env-checklist.md — shell only>
      export API=https://api.advisordesk.tyagiakanksha.com
      # one tools/call per article; repeat with "publish" and the returned id
      curl -s -X POST $API/api/v1/mcp \
        -H "Authorization: Bearer $MCP_TOKEN" \
        -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
        -d @/tmp/create-draft-01.json
      ```
      where `/tmp/create-draft-01.json` is
      `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"create_draft","arguments":{"title":"…","body_md":"…","tags":["equity-compensation"]}}}`
      built from the seed file (a `python - <<'PY'` heredoc that reads the file, splits the
      frontmatter, and writes that JSON is the safe way — markdown in a shell argument is not).
      **Seeding is idempotent by TITLE and these titles are new**, so nothing existing is touched.
- [ ] **2. Verify the published count.** Expect **44** = 28 already live + 16 new:
      ```sh
      curl -fsS https://api.advisordesk.tyagiakanksha.com/api/v1/public/content \
        | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))'
      ```
      Record the number. If it is not 44, stop and reconcile before replaying — a partial publish
      makes every weak-query row below ambiguous.
- [ ] **3. Run the replay — the day BEFORE the talk** (budget ruling above: 40 of 50 daily
      requests):
      ```sh
      cd apps/api && uv run python -m app.eval.replay \
        --base-url https://api.advisordesk.tyagiakanksha.com \
        --out ~/replay-$(date +%F).json
      ```
      Expect ~5 minutes, `40 questions, 4 sessions`, `0 failures`, and roughly 14 refusals
      (10 near-miss + 4 off-domain). Paste the summary line and the event totals.
- [ ] **4. See the near-misses come back out** — `report_weak_queries` on prod (connector, or the
      bearer fallback with `{"name":"report_weak_queries","arguments":{"days":7,"limit":20}}`).
      Expect: the ten planted-gap questions grouped, `kinds` containing `near_miss` for the ones
      whose closest source scored within 0.15 of 0.5 and `refused` for the rest, each with its
      `worst_top_similarity`. **Record the actual kinds and similarities** — they are beat 3's
      script, and which gap lands in which class is a fact about the live corpus, not something to
      predict.
- [ ] **5. Optional (beat 5).** Open the client, ask one question, click 👎, and confirm the turn
      shows up in the next `report_weak_queries` as `negative_feedback`.

## Deliverable 3a — `rehearsal.md` (required structure and commands)

A document the owner can run top to bottom, twice, in under 30 minutes. Required sections:

**§0 What this proves** — the loop DESIGN §"Verification" describes: a gap becomes a proposal
becomes a draft becomes a published change the harness measures, and acceptance is **gated by
that measurement**; then the same machinery refusing a bad fix.

**§1 Scratch database** (never the dev or prod DB):

```sh
cd /home/ak/Documents/github_akanksha/AdvisorDesk/apps/api
docker exec advisordesk-test-db psql -U postgres -c 'CREATE DATABASE advisordesk_rehearsal'
export DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r' | sed -E 's#^postgresql://#postgresql+psycopg://#; s#/advisordesk_test$#/advisordesk_rehearsal#')"
export OPENAI_API_KEY="$(grep -E '^OPENAI_API_KEY=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r')"
uv run alembic upgrade head
uv run python -m app.seed          # expect: seed_all: created=37 published=33 skipped=0 chunk_count=…
```

(The counts come from the wave-1 corpus; record the real ones. `OPENAI_API_KEY` is extracted
per-variable with the global-constraints pattern — never `source .env`, never echoed.)

**§2 Baseline run** — and how to read the run ids back out (the harness prints the table and the
`groundedness:` line, not the row id):

```sh
uv run python -m app.eval.groundedness --label rehearsal-before
docker exec advisordesk-test-db psql -U postgres -d advisordesk_rehearsal \
  -c "select id, label, pct_fully_supported, corpus_digest, created_at from eval_runs order by created_at desc limit 3"
```

**§3 The clean fix (beat 4)** — a `python - <<'PY'` heredoc per step, each printing what the next
step needs. Pick one `class: near_miss` question from `seed/eval_questions.yaml` that FAILED in §2
(name it in the doc):

1. propose:
   ```sh
   uv run python - <<'PY'
   from app.config import Settings
   from app.db import make_engine, make_session_factory
   from app.services.chat import weak_queries
   from app.services.proposals import propose_content_fix

   settings = Settings()
   session = make_session_factory(make_engine(settings.database_url.get_secret_value()))()
   groups = weak_queries(session, days=30, limit=20, threshold=settings.similarity_threshold)
   print("weak groups:", [(g.normalized, g.kinds, g.worst_top_similarity) for g in groups])
   proposal = propose_content_fix(
       session,
       kind="new_article",
       title="RSUs and ESPP for Employees Outside the United States",
       rationale="Replay shows repeated near-misses on non-US equity questions.",
       evidence=[
           {"normalized_question": g.normalized, "count": g.count, "kinds": g.kinds,
            "worst_top_similarity": g.worst_top_similarity}
           for g in groups
       ],
       actor_id=None,
   )
   session.commit()
   print("proposal", proposal.id, "draft", proposal.draft_content_id, "before", proposal.eval_run_before_id)
   PY
   ```
2. write the real article into that draft (`update_content(..., body_md=…)` in the same heredoc
   style, or the admin UI) — the stub body is a placeholder, and the rehearsal must publish a draft
   that genuinely answers the question;
3. publish it (`publish_content(session, draft_id, actor_id=None, pipeline=EmbeddingChunkPipeline(
   OpenAICompatibleEmbedder.from_settings(settings)))` — a real embedder, or retrieval will never
   see it);
4. after-run + diff in one command:
   `uv run python -m app.eval.groundedness --label rehearsal-after --compare-to latest`
   → expect the printed `compare <before> -> <after>: pct … (+…); regressions 0; improvements 1`;
5. accept, with the after-run id from that line:
   ```sh
   uv run python - <<'PY'
   # accept_proposal(session, proposal_id, eval_run_after_id=...) -> status "accepted"
   PY
   ```
   Record the printed status.

**§4 The prod checklist** — Deliverable 2 above, verbatim.

**§5 The bad fix (beat 4's variant — the one that must be rehearsed most)**

Same machinery, second proposal — this one must be **rejected**:

1. `propose_content_fix` again, for a different planted gap (e.g. crypto compensation), so the bad
   draft hangs off a real proposal and `accept_proposal` has something to refuse. Record the new
   proposal id and note that its `eval_run_before_id` is now §3's *after* run (the latest answer
   run), which is correct: that is the corpus this fix is measured against.
2. Fill **that** draft with a body designed to hijack retrieval for two questions that PASSED in
   §3's after-run: H2 headings copied almost verbatim from two existing golden questions, with thin,
   non-answering prose underneath — so it out-ranks the real article on similarity and then fails
   the faithfulness judge. (Say in the doc which two questions were targeted; they are the ones the
   `compare` line must name.)
3. Publish it, re-run, and show the refusal:

```sh
uv run python -m app.eval.groundedness --label rehearsal-badfix --compare-to <after_id>
# expect: regressions 2, and two `regression: …` lines naming the hijacked questions
uv run python - <<'PY'
# accept_proposal(session, <bad_proposal_id>, eval_run_after_id=<badfix_run_id>)
#   -> ConflictError naming the two regressed questions   <- THE BEAT
# reject_proposal(
#     session, <bad_proposal_id>,
#     reason="Regressed two questions in rehearsal-badfix",
#     actor_id=None,
#     pipeline=EmbeddingChunkPipeline(OpenAICompatibleEmbedder.from_settings(settings)),
# ) -> status "rejected", draft archived (a real pipeline: archiving removes its chunks)
PY
```

Required: the **verbatim** `ConflictError` text, and proof the draft ended `archived` (a psql
`select status from content where id = …`).

**§6 Teardown + re-run** — `DROP DATABASE advisordesk_rehearsal`, and a note that §1-§5 are
re-runnable from scratch in one sitting (they must be: the owner runs this at least twice before
the 24th).

Every command block is followed by a fenced block holding the **real recorded output**, the same
convention `infra/deploy/VERIFY.md` uses.

## Deliverable 3b — `run-sheet.md` (required structure)

One page the owner can hold. Required sections:

1. **Before you go on** — URLs (client `https://advisordesk.tyagiakanksha.com`, API
   `https://api.advisordesk.tyagiakanksha.com`, admin `.../signin`); the replay already run
   **yesterday**; `prod-probe` green this morning; the remaining per-IP budget (50/day − whatever
   the replay used; ~10 questions left, so no live fishing); connector already connected; browser
   tabs pre-opened; one terminal with `$API` exported.
2. **The four beats**, each with: the exact question/command, what the audience sees, the
   number to read out, a **timing** (beat 1: 2 min · beat 2: 1 min · beat 3: 3 min · beat 4: 5 min
   + 3 min for the variant), and a **fallback**:
   - beat 1 (grounded answer the room can verify — an RSU-at-vest question): fallback = the
     recorded `replay-<date>.json` outcome for that same question;
   - beat 2 (off-domain refusal): fallback = a screenshot;
   - beat 3 (planted gap → refusal → `report_weak_queries` shows `near_miss` + the closest source's
     similarity): fallback = the recorded §4 output from `rehearsal.md`, which is why step 4 records
     the real numbers;
   - beat 4 (propose → draft → publish → re-run → `compare_runs` → accept; then the bad-fix variant
     rejected): fallback = run it on the scratch DB from `rehearsal.md` (no live embedding calls,
     no prod writes) — **and the run sheet says to decide in advance whether beat 4 runs against
     prod at all**: a failed live publish costs the talk more than a rehearsed scratch-DB run does.
3. **The line** (say it, don't imply it): *"Nothing here applies itself. The system detects, it
   proposes, it measures — and a human accepts. 'Self-improving' means the loop proposes its own
   fixes and can prove whether they worked; it does not mean unsupervised."*
4. **What to say when a metric moves** — rehearsed answers, not improvisation:
   - a number differs from the slide → "this is a live run; the recorded run is <id>, and the
     3-run spread for this metric was ±X" (the spread is exactly why task 03 prints it);
   - the judge disagrees with the room → the scorecard: κ vs 40 human labels, and
     `judge_disagreement` is a taxonomy cause with no content fix;
   - groundedness looks low → the retired 58.8% story: it was temperature-1.0 sampling noise, fixed
     and re-baselined (task 09), which is why the spread is reported at all;
   - a beat fails live → name the fallback, move on, and come back to it in questions.
5. **After the talk** — the leftovers that belong to the whole-branch review, not to the stage:
   corpus wave 2, the RAGAS cross-check, and any ride items the reviewer ledgered.

## Verify

```sh
export TEST_DATABASE_URL="$(grep -E '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | cut -d= -f2- | tr -d '"'"'"'\r')"
cd apps/api
uv run pytest tests/test_replay.py tests/test_seed.py -q
pnpm gates:api
git diff --exit-code -- openapi.json mcp-tools.json ../../apps/client/src/types/generated/schema.d.ts
```

## Acceptance

- `seed/replay_questions.yaml` holds exactly the 40 questions above (26/10/4), loads under strict
  validation, and every invalid shape in the parametrised test raises `ValueError` naming the key.
- `replay_question` never raises for a failed turn; a refusal is `citation_count == 0` with no
  error; an `error` event and a non-2xx both land in `error`.
- `run_replay` opens one session per batch of 10, resends the returned `session_id` within a batch,
  starts fresh after a turn that returned none, and paces `60 / rate_per_min` seconds **between**
  requests via the injected `sleep`.
- `--base-url` is required; `--rate` is requests/minute, defaults to 8.0 and refuses > 9.0 naming
  `RATE_LIMIT_PER_MIN`; `--out` writes the JSON artifact.
- The unit test uses `httpx.MockTransport` and an injected `sleep`: the whole file runs with no
  network and no real waiting.
- `rehearsal.md` runs top to bottom on a scratch DB with **real recorded outputs** pasted in —
  including the clean accept AND the bad fix's verbatim `ConflictError` plus the archived draft —
  and the prod checklist as §4, marked owner-gated.
- `run-sheet.md` carries all five sections, a timing and a fallback per beat, the
  human-gated-self-improvement line verbatim, and the three "when a metric moves" answers.
- No wire surface moved (`git diff --exit-code` over the three baselines is clean); `pnpm gates:api`
  green.
- `infra/deploy/VERIFY.md` gains exactly one new section — §8, a pointer to `rehearsal.md` §4 — and
  nothing else in that file moves (the deployed-checks doc stays the index; the steps stay with the
  plan).
- The prod steps are **not** executed from an agent session: the implementer report says explicitly
  that they are left to the owner, and `rehearsal.md` §4's checkboxes are unticked.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-18-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-18-implementer.md` — must
  include the 3-question smoke-run output, the full rehearsal transcript's key lines (the two
  `compare` lines, the accept status, the `ConflictError` text), the replay traffic-budget
  arithmetic actually used, and any observation for the whole-branch review ledger (e.g. the
  harness not printing its own `eval_runs` id, which the rehearsal works around with psql — do
  **not** fix it here).
