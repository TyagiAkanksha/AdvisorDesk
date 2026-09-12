"""Groundedness harness: run every `seed/eval_questions.yaml` question through the real
retrieval + synthesis path and report answer-support/refusal metrics (phase-7 task-02).

Spec: `advisordesk-prd.md` §8.1 (file shape + expected outcomes), §10 Phase 7 (report contents),
§9.1 (the groundedness metric). Task brief:
`.superpowers/sdd/phase-7-evaluation/task-02-brief.md`.

`run_eval` drives the SAME two seams the real `/public/chat` route uses
(`app.rag.retrieval.retrieve` / the `ChatLLM` Protocol, `app.rag.synthesis`) rather than a parallel
implementation, so the harness measures exactly what production does — never HTTP/SSE, the service
path directly (task brief Context). `embedder`/`chat_llm`/`judge` are all injectable seams
(`tests/test_groundedness.py` exercises `run_eval` with scripted fakes; the real OpenAI-backed
wiring lives only in `_run_from_cli`/`__main__`, below).

Controller rulings this module builds to (see the task-02 report for the full rationale):

  I.1 `cited_slugs` = the slug of EVERY chunk `retrieve()` returned for the question — mirroring
      `app.services.chat.record_assistant_message`'s chunk-level DB citations, NOT filtered by
      which `[n]` brackets the model's answer text happens to cite.
  I.2 `refused` is derived from the same `retrieval_found` signal
      `record_assistant_message` writes to the DB (`app.services.chat`) — a chunk-level
      "did retrieval find anything" fact, not a parallel heuristic over the answer's own wording.
  I.3 `pct_fully_supported` is computed over ANSWERABLE rows only; `refusal_correct`/
      `refusal_total` are computed over UNCOVERED (`answerable=False`) rows only.
      `fully_supported` is `None` for uncovered rows (not applicable — no answer-support claim to
      score when the row's entire question is whether the assistant refused).
  I.4 `verdict` holds the literal strings `"PASS"`/`"FAIL"`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.models import EvalRun
from app.rag.embeddings import Embedder, OpenAICompatibleEmbedder
from app.rag.retrieval import retrieve
from app.rag.synthesis import SYSTEM_PROMPT, ChatLLM, OpenAICompatibleChatLLM
from app.seed_paths import seed_data_dir
from app.services.eval_runs import compare_runs, latest_runs, record_run

__all__ = [
    "EvalReport",
    "EvalRow",
    "GroundednessJudge",
    "OpenAIJudge",
    "run_eval",
]

# Resolved via `app.seed_paths.seed_data_dir()` so both host dev and the container image find the
# corpus without this module doing a `parents[...]` walk (which went out of range under the
# container's `/app/app/eval/...` layout and crashed on import). On host, `seed_data_dir()` resolves
# to the repo-root `seed/`; in the container it reads `$SEED_DATA_DIR=/app/seed`. Computing this at
# module scope is safe now — `seed_data_dir()` never does path math when the env var is set.
_DEFAULT_QUESTIONS_PATH: Path = seed_data_dir() / "eval_questions.yaml"

# A dependency-free sentence splitter: `.`/`!`/`?` followed by whitespace. Good enough for the
# short, single-paragraph answers this harness judges sentence-by-sentence (brief: "call the judge
# per sentence") — the exact tokenizer is explicitly unspecified by the brief
# (`tests/test_groundedness.py` module docstring, judgment call 3): `ScriptedJudge` pins outcomes
# by MARKER CONTENT, never by call count/order, so no test depends on this regex's exact behavior
# beyond "splits on sentence-ending punctuation."
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")

# Fix round 1, M4: named once so `_evaluate_question`'s `retrieve()` call and `_run_from_cli`'s
# `record_run(..., retrieval_k=...)` can never silently drift apart — before this constant,
# `_evaluate_question` relied on `retrieve()`'s own default `k` while `_run_from_cli` recorded a
# separate hard-coded `6`; the two agreed only by coincidence.
_RETRIEVAL_K = 6


@dataclass(frozen=True)
class EvalRow:
    """One eval question's outcome (task-02 brief Interfaces; `top_similarity`/`answer_text`/
    `question_class`/`persona`/`metrics` added phase-9 task-03 so `app.services.eval_runs.
    record_run` has a full row to persist). The three defaulted fields stay `None` here — tasks
    04/05/06 fill them in.
    """

    question: str
    answerable: bool
    expected_slugs: list[str]
    cited_slugs: list[str]
    slugs_hit: bool
    fully_supported: bool | None
    refused: bool
    verdict: str
    top_similarity: float | None
    answer_text: str
    question_class: str | None = None
    persona: str | None = None
    metrics: dict[str, object] | None = None


@dataclass(frozen=True)
class EvalReport:
    """The whole eval run's rows plus the §9.1/§10 summary numbers (task-02 brief Interfaces)."""

    rows: list[EvalRow]
    pct_fully_supported: float
    refusal_correct: int
    refusal_total: int


@dataclass(frozen=True)
class _EvalQuestion:
    """One parsed, validated `seed/eval_questions.yaml` record (PRD §8.1)."""

    question: str
    expected_slugs: list[str]
    answerable: bool


class GroundednessJudge(Protocol):
    """The judge seam `run_eval` scores each answer sentence through (task-02 brief Interfaces).

    Structurally implemented by `OpenAIJudge` (the real judge) and by
    `tests/test_groundedness.py`'s `ScriptedJudge` — a `Protocol`, not an ABC, mirroring
    `app.rag.embeddings.Embedder`/`app.rag.synthesis.ChatLLM`'s own seam shape
    (CONVENTIONS.md §10: external seams are injectable, never reached in tests).
    """

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        """Return whether `claim_text` (one answer sentence) is supported by `chunk_texts`.

        Args:
            claim_text: one sentence of the model's answer.
            chunk_texts: the union of the row's cited chunk texts (I.1) — every chunk
                `retrieve()` returned for this question, deduped, in retrieval order.

        Returns:
            `True` iff `claim_text` is fully supported by `chunk_texts`.
        """
        ...


# The judge's own system prompt — deliberately separate from `app.rag.synthesis.SYSTEM_PROMPT`
# (that one instructs the ANSWERING model; this one instructs a fact-checking model judging an
# already-produced answer sentence against source text).
_JUDGE_SYSTEM_PROMPT = (
    "You are a strict fact-checking judge. You are given SOURCE passages and one CLAIM (one "
    "sentence from an answer that was supposed to be grounded in those sources). Reply with "
    "exactly one word: YES if the claim is fully and directly supported by the sources (no "
    "unsupported addition, no contradiction), or NO otherwise."
)


class OpenAIJudge:
    """The real `GroundednessJudge`, built from `Settings` (task-02 brief Interfaces).

    Mirrors `app.rag.synthesis.OpenAICompatibleChatLLM`'s client construction exactly
    (`from_settings`, `settings.llm_api_key`/`settings.llm_base_url`/`settings.chat_model`, the
    same reused `embedding_timeout_seconds`/`embedding_max_retries` budgets) — `settings.
    chat_model` defaults to `"gpt-4o-mini"` (`app/config.py`), which is this class's judge model
    under that default. Judges at `temperature=0` (deterministic verdicts). Only exercised in the
    real recorded run (`_run_from_cli`, deferred to task-03) — never in unit tests, which inject
    `ScriptedJudge` instead.
    """

    def __init__(self, *, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIJudge:
        """Build the real client from `Settings` — the one non-test constructor."""
        api_key = settings.llm_api_key.get_secret_value() or "unset"
        client = OpenAI(
            api_key=api_key,
            base_url=settings.llm_base_url,
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )
        return cls(client=client, model=settings.chat_model)

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        """Ask the judge model whether `claim_text` is supported by `chunk_texts`."""
        sources = (
            "\n\n".join(f"[{i + 1}] {text}" for i, text in enumerate(chunk_texts))
            if chunk_texts
            else "(no source passages)"
        )
        user_message = f"SOURCES:\n{sources}\n\nCLAIM: {claim_text}\n\nIs the claim supported?"
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        content = response.choices[0].message.content or ""
        return content.strip().upper().startswith("YES")


def _split_sentences(text: str) -> list[str]:
    """Split `text` into sentences on `.`/`!`/`?` followed by whitespace (see module-level regex
    docstring for why the exact tokenizer is unpinned).
    """
    stripped = text.strip()
    if not stripped:
        return []
    return [sentence for sentence in _SENTENCE_BOUNDARY_RE.split(stripped) if sentence]


def _dedupe_preserve_order(texts: Iterable[str]) -> list[str]:
    """The union of `texts`, deduped, in first-occurrence order (`dict.fromkeys` trick)."""
    return list(dict.fromkeys(texts))


def _load_questions(questions_path: Path) -> list[_EvalQuestion]:
    """Load and validate `questions_path` against the PRD §8.1 shape (task-02 brief Step 1: "YAML
    loading validates the §8.1 shape").

    Mirrors `tests/test_seed.py`'s own §8.1 shape checks: a top-level list of mappings, each with
    exactly `question` (non-blank str), `expected_slugs` (list), `answerable` (bool).

    Raises:
        ValueError: `questions_path` does not parse to a top-level list, or an item is not a
            mapping, or is missing/mistypes one of the three required keys, or two items share
            the same `question` text (fix round 1, reviewer finding I2 — the `(run_id, question)`
            unique constraint (`app/models/eval.py`) would otherwise reject the whole run at
            `record_run`'s final `flush()`, discarding every row after the run already paid for
            its embedder/chat/judge calls).
    """
    raw = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{questions_path}: eval questions file must parse to a top-level list")

    questions: list[_EvalQuestion] = []
    seen_questions: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{questions_path}[{index}]: item is not a mapping: {item!r}")
        question = item.get("question")
        expected_slugs = item.get("expected_slugs")
        answerable = item.get("answerable")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{questions_path}[{index}]: 'question' must be a non-blank string")
        if question in seen_questions:
            raise ValueError(f"{questions_path}[{index}]: duplicate question: {question!r}")
        seen_questions.add(question)
        if not isinstance(expected_slugs, list):
            raise ValueError(f"{questions_path}[{index}]: 'expected_slugs' must be a list")
        if not isinstance(answerable, bool):
            raise ValueError(f"{questions_path}[{index}]: 'answerable' must be a bool")
        questions.append(
            _EvalQuestion(
                question=question,
                expected_slugs=[str(slug) for slug in expected_slugs],
                answerable=answerable,
            )
        )
    return questions


def _evaluate_question(
    session: Session,
    *,
    embedder: Embedder,
    chat_llm: ChatLLM,
    judge: GroundednessJudge,
    settings: Settings,
    question: _EvalQuestion,
) -> EvalRow:
    """Drive one question through retrieval + synthesis and score the result (see module
    docstring, rulings I.1-I.4).
    """
    retrieval = retrieve(
        session,
        embedder,
        question.question,
        k=_RETRIEVAL_K,
        threshold=settings.similarity_threshold,
    )
    retrieval_found = bool(retrieval.chunks)

    # I.1: chunk-level citations — every chunk `retrieve()` returned, mirroring
    # `app.services.chat.record_assistant_message`'s DB citation shape (never deduped/filtered by
    # the model's own `[n]` bracket usage, unlike the wire-level `dedupe_citations`).
    cited_slugs = [chunk.slug for chunk in retrieval.chunks]
    slugs_hit = set(question.expected_slugs) <= set(cited_slugs)

    # I.2: `refused` mirrors the same `retrieval_found` fact `record_assistant_message` writes to
    # the DB — the natural production refusal signal — rather than a parallel heuristic parsing
    # the model's answer text.
    refused = not retrieval_found

    answer_text = "".join(
        chat_llm.stream_answer(SYSTEM_PROMPT, question.question, retrieval.chunks)
    )

    fully_supported: bool | None
    if question.answerable:
        chunk_texts = _dedupe_preserve_order(chunk.text for chunk in retrieval.chunks)
        fully_supported = all(
            judge.is_supported(sentence, chunk_texts) for sentence in _split_sentences(answer_text)
        )
        verdict = "PASS" if slugs_hit and fully_supported else "FAIL"
    else:
        # I.3: not applicable to an uncovered row — no answer-support claim to score.
        fully_supported = None
        verdict = "PASS" if (refused and not retrieval_found and not cited_slugs) else "FAIL"

    return EvalRow(
        question=question.question,
        answerable=question.answerable,
        expected_slugs=question.expected_slugs,
        cited_slugs=cited_slugs,
        slugs_hit=slugs_hit,
        fully_supported=fully_supported,
        refused=refused,
        verdict=verdict,
        top_similarity=retrieval.top_similarity,
        answer_text=answer_text,
    )


def _build_report(rows: list[EvalRow]) -> EvalReport:
    """Aggregate `rows` into the §9.1/§10 summary numbers (I.3: split by `answerable`)."""
    answerable_rows = [row for row in rows if row.answerable]
    uncovered_rows = [row for row in rows if not row.answerable]

    pct_fully_supported = (
        100.0 * sum(1 for row in answerable_rows if row.fully_supported) / len(answerable_rows)
        if answerable_rows
        else 0.0
    )
    refusal_total = len(uncovered_rows)
    refusal_correct = sum(1 for row in uncovered_rows if row.verdict == "PASS")

    return EvalReport(
        rows=rows,
        pct_fully_supported=pct_fully_supported,
        refusal_correct=refusal_correct,
        refusal_total=refusal_total,
    )


def run_eval(
    session: Session,
    *,
    embedder: Embedder,
    chat_llm: ChatLLM,
    judge: GroundednessJudge,
    questions_path: Path,
) -> EvalReport:
    """Run every question in `questions_path` through the real retrieval + synthesis path and
    score it (task-02 brief Interfaces).

    Drives `app.rag.retrieval.retrieve`/the `ChatLLM` seam directly (not HTTP/SSE) — the exact
    same two calls `app.routes.public_routes._generate_chat_stream` makes for `POST /public/chat`,
    so this harness measures what production actually does. `Settings()` supplies
    `similarity_threshold` (`retrieve()`'s own caller-supplied-threshold contract) — the same
    runtime default the real chat route reads, never overridden here.

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first) — the corpus `retrieve()`
            searches.
        embedder: the `Embedder` seam (real or scripted) each question is embedded through.
        chat_llm: the `ChatLLM` seam (real or scripted) each answer is generated through.
        judge: the `GroundednessJudge` seam (real or scripted) each answer sentence is scored
            through.
        questions_path: path to a PRD §8.1-shaped YAML file (`seed/eval_questions.yaml` in
            production).

    Returns:
        An `EvalReport` with one `EvalRow` per question, in file order, plus the §9.1/§10 summary
        numbers.
    """
    settings = Settings()
    questions = _load_questions(Path(questions_path))
    rows = [
        _evaluate_question(
            session,
            embedder=embedder,
            chat_llm=chat_llm,
            judge=judge,
            settings=settings,
            question=question,
        )
        for question in questions
    ]
    return _build_report(rows)


def _print_table(rows: Sequence[EvalRow]) -> None:
    """Print the per-question table `__main__` reports (task-02 brief: "prints the per-question
    table + summary line").
    """
    header = (
        f"{'answerable':<11} {'slugs_hit':<10} {'supported':<10} {'refused':<8} "
        f"{'verdict':<7} question"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        supported = "-" if row.fully_supported is None else str(row.fully_supported)
        print(
            f"{str(row.answerable):<11} {str(row.slugs_hit):<10} {supported:<10} "
            f"{str(row.refused):<8} {row.verdict:<7} {row.question}"
        )


def _git_sha() -> str:
    """The current commit's full SHA, or `""` when it can't be determined (phase-9 task-03).

    Never raises: `check=False` means a non-zero exit (e.g. a container/tarball checkout with no
    `.git`) is reported via `returncode`, not an exception. Fix round 1, I1: `check=False` alone
    does NOT stop `subprocess.run` from raising `FileNotFoundError` when the `git` binary itself
    is absent (exactly the "container … with no `.git`" case this function's own docstring
    names — slim Python images ship no git at all) or `subprocess.TimeoutExpired` past the 5s
    budget; both are now caught here too, alongside any other `OSError`, so a genuinely
    never-raises contract holds even after `run_eval` has already spent the whole question set on
    real API calls.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the harness CLI's flags (phase-9 task-03 Interfaces).

    `--runs` doesn't use `choices=range(1, 11)` — it just validates `>= 1` itself via
    `parser.error` (an explicit, un-numerically-capped floor beats an arbitrary ceiling).

    Note (fix round 1, M1 — deliberately NOT fixed here): `--no-persist` together with
    `--compare-to` parses cleanly and is left to `_run_from_cli` to silently skip the comparison
    (`last_run` stays `None`) — the authored test `test_parse_args_accepts_every_flag`
    (`tests/test_groundedness_cli.py`) pins EXACTLY this flag combination succeeding at parse
    time, so rejecting it here would break an authored test. Ledgered for the whole-branch review
    instead (see the fix-round-1 report).
    """
    parser = argparse.ArgumentParser(
        description="Run seed/eval_questions.yaml through the real retrieval + synthesis path."
    )
    parser.add_argument("--label", default="adhoc", help="Run family label (default: adhoc).")
    parser.add_argument(
        "--questions",
        type=Path,
        default=_DEFAULT_QUESTIONS_PATH,
        help="Path to a PRD §8.1-shaped questions YAML file.",
    )
    parser.add_argument(
        "--no-persist", action="store_true", help="Don't write EvalRun/EvalResult rows."
    )
    parser.add_argument(
        "--compare-to",
        default=None,
        help="A run-id UUID, or the literal 'latest', to diff the last run against.",
    )
    parser.add_argument(
        "--runs", type=int, default=1, help="How many times to run the eval (default: 1)."
    )
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    return args


def _print_report(report: EvalReport) -> None:
    """Print one run's per-question table plus the phase-7 summary line (byte-identical to the
    phase-7 stdout — `docs/plans/phase-7-evaluation/verification-record.md` §1 and task-09 both
    depend on this exact line).
    """
    _print_table(report.rows)
    print(
        f"groundedness: {report.pct_fully_supported:.1f}% fully supported; "
        f"refusals {report.refusal_correct}/{report.refusal_total} correct"
    )


def _print_stability(reports: Sequence[EvalReport], *, label: str) -> None:
    """Print a `--runs N` (`N > 1`) family's mean/spread block for `pct_fully_supported` and
    `refusal_correct` (phase-9 task-03 Interfaces).

    `mean` is the arithmetic mean formatted `.1f` for both rows; `spread` is `max - min`,
    formatted `.1f` for the percentage row and left as a plain `int` for the count row.

    Fix round 1, I4: the printed PER-RUN `pct_fully_supported` values are rounded to one decimal
    (`round(value, 1)`) — a real run's raw float (e.g. `76.47058823529412`, `100 * 13 / 17`) is
    otherwise printed at full precision, which is illegible on the phase's headline stability
    line. `mean`/`spread` were already `.1f`-formatted and are unaffected; the count row's values
    are exact integers, so no rounding applies there.
    """
    print(f"stability over {len(reports)} runs (label={label}):")

    pct_values = [report.pct_fully_supported for report in reports]
    pct_mean = sum(pct_values) / len(pct_values)
    pct_spread = max(pct_values) - min(pct_values)
    pct_display = [round(value, 1) for value in pct_values]
    print(
        f"  {'pct_fully_supported':<21}mean {pct_mean:.1f}  spread {pct_spread:.1f}  {pct_display}"
    )

    refusal_values = [report.refusal_correct for report in reports]
    refusal_mean = sum(refusal_values) / len(refusal_values)
    refusal_spread = max(refusal_values) - min(refusal_values)
    print(
        f"  {'refusal_correct':<21}mean {refusal_mean:.1f}  spread {refusal_spread}  "
        f"{refusal_values}"
    )


def _run_from_cli(
    argv: list[str] | None = None,
    *,
    run_eval_fn: Callable[..., EvalReport] = run_eval,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """`python -m app.eval.groundedness`: wire the REAL embedder/chat LLM/judge from `Settings`,
    run `args.runs` real recorded eval(s) against the seeded local-db stack, persist by default,
    and optionally print a stability block and a `compare_runs` diff (phase-9 task-03).

    Fix round 1, I3: `argv`/`run_eval_fn`/`session_factory` are injectable seams (reviewer finding
    I3 — this orchestration, the task's headline behaviour, had zero test coverage because it
    built its own seams internally). Defaults reproduce the exact previous behaviour byte for
    byte: `argv=None` parses `sys.argv` as before, `run_eval_fn` defaults to the real `run_eval`,
    and a `None` `session_factory` builds the real engine/session from `Settings()` exactly as
    this function always has (mirrors `app/seed.py::_run_from_cli`'s same self-contained CLI
    wiring pattern — `app.eval` is a standalone script, not a FastAPI route, so it has no
    `app.state` to read `app.routes.deps.get_session`/`get_embedder`/`get_chat_llm` from). Tests
    inject a canned `run_eval_fn` (no network) and a `session_factory` returning the `db_session`
    fixture; ownership follows who built the session — this function only closes/disposes the
    session/engine it built itself, never a caller-supplied one.

    `--compare-to latest` resolves to the most recent `kind="answer"` run EXCLUDING the run(s)
    this invocation is about to write — resolved once, up front, before any `record_run` call in
    this invocation can appear in `latest_runs`' own result. `_git_sha()` is computed ONCE, before
    the run loop (fix round 1, I1/M8 — one subprocess call and one value for the whole family,
    not one per run).
    """
    args = _parse_args(argv)
    settings = Settings()
    embedder = OpenAICompatibleEmbedder.from_settings(settings)
    chat_llm = OpenAICompatibleChatLLM.from_settings(settings)
    judge = OpenAIJudge.from_settings(settings)

    owns_session = session_factory is None
    engine = None
    if session_factory is None:
        engine = make_engine(settings.database_url.get_secret_value())
        session_factory = make_session_factory(engine)

    session = session_factory()
    try:
        # Resolved BEFORE any run in this invocation is written, so `latest` never sees a run
        # this same invocation just persisted. An explicit, unknown compare-to id is left to
        # `compare_runs`'s own `NotFoundError` below rather than silently skipped here.
        before_id: uuid.UUID | None = None
        if args.compare_to == "latest":
            previous = latest_runs(session, kind="answer", limit=1)
            before_id = previous[0].id if previous else None
        elif args.compare_to is not None:
            before_id = uuid.UUID(args.compare_to)

        git_sha = _git_sha()

        reports: list[EvalReport] = []
        last_run: EvalRun | None = None
        for _ in range(args.runs):
            report = run_eval_fn(
                session,
                embedder=embedder,
                chat_llm=chat_llm,
                judge=judge,
                questions_path=args.questions,
            )
            _print_report(report)
            reports.append(report)
            if not args.no_persist:
                last_run = record_run(
                    session,
                    report,
                    label=args.label,
                    embedding_model=settings.embedding_model,
                    chat_model=settings.chat_model,
                    judge_model=settings.chat_model,
                    similarity_threshold=settings.similarity_threshold,
                    retrieval_k=_RETRIEVAL_K,
                    git_sha=git_sha,
                )

        if not args.no_persist:
            session.commit()

        if args.runs > 1:
            _print_stability(reports, label=args.label)

        if before_id is not None and last_run is not None:
            diff = compare_runs(session, before_id, last_run.id)
            before_run = session.get(EvalRun, before_id)
            assert before_run is not None  # compare_runs already proved this id exists
            print(
                f"compare {diff.before_id} -> {diff.after_id}: "
                f"pct {before_run.pct_fully_supported:.1f} -> "
                f"{last_run.pct_fully_supported:.1f} ({diff.pct_delta:+.1f}); "
                f"regressions {len(diff.regressions)}; improvements {len(diff.improvements)}; "
                f"added {len(diff.added)}; removed {len(diff.removed)}"
            )
            for question in diff.regressions:
                print(f"  regression: {question}")
    finally:
        if owns_session:
            session.close()
    if engine is not None:
        engine.dispose()


if __name__ == "__main__":
    _run_from_cli()
