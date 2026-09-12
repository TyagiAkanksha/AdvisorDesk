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

Phase-9 task-05 (metrics v2): `GroundednessJudge`, `_split_sentences`, retrieval recall@k/
precision@k/MRR, and the three new rubric judges (answer relevance, context precision, context
recall) all now live in — or are re-exported from — `app.eval.metrics`, a pure leaf module with no
DB/network/`Settings` dependency (task file Interfaces: "simpler and preferred" option). This
module still owns everything that touches the DB, an LLM, or `Settings`: `OpenAIJudge` (the real
judge, now also implementing the three rubric methods), `_evaluate_question`'s wiring of
`app.eval.metrics`'s pure functions around the real `retrieve()`/`resolve_expected_chunks()`
calls, and the CLI.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.eval.metrics import (
    GroundednessJudge,
    MetricsJudge,
    context_precision,
    context_recall,
    retrieval_metrics,
    split_sentences,
)
from app.eval.questions import EvalQuestion, load_questions, resolve_expected_chunks
from app.models import EvalRun
from app.rag.embeddings import Embedder, OpenAICompatibleEmbedder
from app.rag.retrieval import retrieve
from app.rag.synthesis import SYSTEM_PROMPT, ChatLLM, OpenAICompatibleChatLLM
from app.seed_paths import seed_data_dir
from app.services.eval_runs import compare_runs, latest_runs, record_run

logger = logging.getLogger(__name__)

__all__ = [
    "ClassRollup",
    "EvalReport",
    "EvalRow",
    "GroundednessJudge",
    "MetricsJudge",
    "OpenAIJudge",
    "run_eval",
]

# Resolved via `app.seed_paths.seed_data_dir()` so both host dev and the container image find the
# corpus without this module doing a `parents[...]` walk (which went out of range under the
# container's `/app/app/eval/...` layout and crashed on import). On host, `seed_data_dir()` resolves
# to the repo-root `seed/`; in the container it reads `$SEED_DATA_DIR=/app/seed`. Computing this at
# module scope is safe now — `seed_data_dir()` never does path math when the env var is set.
_DEFAULT_QUESTIONS_PATH: Path = seed_data_dir() / "eval_questions.yaml"

# Fix round 1, M4: named once so `_evaluate_question`'s `retrieve()` call and `_run_from_cli`'s
# `record_run(..., retrieval_k=...)` can never silently drift apart — before this constant,
# `_evaluate_question` relied on `retrieve()`'s own default `k` while `_run_from_cli` recorded a
# separate hard-coded `6`; the two agreed only by coincidence.
_RETRIEVAL_K = 6


@dataclass(frozen=True)
class ClassRollup:
    """One `EvalQuestion.question_class`'s rollup over a run's rows (task-05 Interfaces)."""

    question_class: str
    count: int
    passed: int
    pct_fully_supported: float  # over that class's answerable rows; 0.0 if none
    mean_recall_at_k: float | None  # mean over rows whose recall_at_k is not None


@dataclass(frozen=True)
class EvalRow:
    """One eval question's outcome (task-02 brief Interfaces; `top_similarity`/`answer_text`/
    `question_class`/`persona`/`metrics` added phase-9 task-03 so `app.services.eval_runs.
    record_run` has a full row to persist). `metrics` is filled in by task 05's
    `_evaluate_question` — see its own docstring for the dict shape.
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
    """The whole eval run's rows plus the §9.1/§10 summary numbers (task-02 brief Interfaces).

    `by_class`/`unresolved_expected_chunks` are task-05 additions, both defaulted so task-03's
    existing four-argument `EvalReport(...)` constructions (`tests/test_groundedness_cli.py`)
    keep working unchanged.
    """

    rows: list[EvalRow]
    pct_fully_supported: float
    refusal_correct: int
    refusal_total: int
    by_class: dict[str, ClassRollup] = field(default_factory=dict)
    # Controller ruling (task-04 review, Minor 1 — `.superpowers/sdd/phase-9-eval-data-loop/
    # progress.md`): `resolve_expected_chunks` silently skips a ref that resolves to no chunk
    # (task-04's own documented decision); this counts those refs, across every row, instead of
    # only falling back to slug-level scoring with no trace.
    unresolved_expected_chunks: int = 0


# The judge's own system prompt — deliberately separate from `app.rag.synthesis.SYSTEM_PROMPT`
# (that one instructs the ANSWERING model; this one instructs a fact-checking model judging an
# already-produced answer sentence against source text).
_JUDGE_SYSTEM_PROMPT = (
    "You are a strict fact-checking judge. You are given SOURCE passages and one CLAIM (one "
    "sentence from an answer that was supposed to be grounded in those sources). Reply with "
    "exactly one word: YES if the claim is fully and directly supported by the sources (no "
    "unsupported addition, no contradiction), or NO otherwise."
)

# The three new rubric judges (task-05 Interfaces). Each ends with the same YES/NO + reason
# instruction, parsed by `OpenAIJudge._ask_yes_no` below — unlike `_JUDGE_SYSTEM_PROMPT` above
# (unchanged: still a bare one-word "YES"/"NO" reply, its own pinned wire format from phase-7).
_YES_NO_SUFFIX = "Reply with YES or NO on the first line, then one short line giving your reason."

_ANSWER_RELEVANCE_PROMPT = (
    "You judge whether an ANSWER actually addresses the QUESTION asked. Ignore whether it is "
    "factually correct — that is judged separately. Answer NO if it answers a different "
    "question, or is a refusal to a question that was asked in good faith. " + _YES_NO_SUFFIX
)
_CONTEXT_PRECISION_PROMPT = (
    "You judge whether one SOURCE passage is relevant to answering the QUESTION. Relevant means "
    "a correct answer would plausibly draw on it. " + _YES_NO_SUFFIX
)
_CONTEXT_RECALL_PROMPT = (
    "You judge whether one CLAIM from a reference answer is covered by the SOURCE passages. "
    "Covered means the sources state it or directly entail it. " + _YES_NO_SUFFIX
)


class OpenAIJudge:
    """The real `GroundednessJudge`/`MetricsJudge`, built from `Settings` (task-02 brief
    Interfaces; task-05 Interfaces for the three rubric methods).

    Mirrors `app.rag.synthesis.OpenAICompatibleChatLLM`'s client construction exactly
    (`from_settings`, `settings.llm_api_key`/`settings.llm_base_url`, the same reused
    `embedding_timeout_seconds`/`embedding_max_retries` budgets) — but the model is
    `settings.judge_model` (DESIGN D7: `"gpt-4o"`, a STRONGER model than the answerer's
    `settings.chat_model`/`"gpt-4o-mini"`), not `chat_model` itself. This moves the recorded
    groundedness number relative to every run before this task (see the implementer report).
    Judges at `temperature=0` (deterministic verdicts). Only exercised in the real recorded run
    (`_run_from_cli`) — never in unit tests, which inject `ScriptedJudge`/`FakeMetricsJudge`
    instead.
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
        return cls(client=client, model=settings.judge_model)

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

    def _ask(self, system: str, user: str) -> str:
        """One `chat.completions.create` call at `temperature=0`; returns the stripped content."""
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    def _ask_yes_no(self, system: str, user: str) -> bool:
        """Call `_ask`, parse its first line as the YES/NO verdict, and log the reason line at
        DEBUG (no schema stores it — DESIGN does not ask for one).
        """
        content = self._ask(system, user)
        first_line, _, rest = content.partition("\n")
        reason = rest.strip()
        if reason:
            logger.debug("judge reason: %s", reason)
        return first_line.strip().upper().startswith("YES")

    def is_answer_relevant(self, question: str, answer_text: str) -> bool:
        """Ask the judge model whether `answer_text` actually addresses `question`."""
        user_message = f"QUESTION: {question}\n\nANSWER: {answer_text}\n\nIs the answer relevant?"
        return self._ask_yes_no(_ANSWER_RELEVANCE_PROMPT, user_message)

    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool:
        """Ask the judge model whether `chunk_text` is relevant to answering `question`."""
        user_message = f"QUESTION: {question}\n\nSOURCE: {chunk_text}\n\nIs the source relevant?"
        return self._ask_yes_no(_CONTEXT_PRECISION_PROMPT, user_message)

    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        """Ask the judge model whether `claim_text` is covered by `chunk_texts`."""
        sources = (
            "\n\n".join(f"[{i + 1}] {text}" for i, text in enumerate(chunk_texts))
            if chunk_texts
            else "(no source passages)"
        )
        user_message = f"SOURCES:\n{sources}\n\nCLAIM: {claim_text}\n\nIs the claim covered?"
        return self._ask_yes_no(_CONTEXT_RECALL_PROMPT, user_message)


def _dedupe_preserve_order(texts: Iterable[str]) -> list[str]:
    """The union of `texts`, deduped, in first-occurrence order (`dict.fromkeys` trick)."""
    return list(dict.fromkeys(texts))


def _evaluate_question(
    session: Session,
    *,
    embedder: Embedder,
    chat_llm: ChatLLM,
    judge: GroundednessJudge,
    settings: Settings,
    question: EvalQuestion,
    metrics_judge: MetricsJudge | None = None,
) -> tuple[EvalRow, int]:
    """Drive one question through retrieval + synthesis and score the result (see module
    docstring, rulings I.1-I.4; task-05 for the `EvalRow.metrics` dict).

    Returns the `EvalRow` plus this question's own unresolved-`expected_chunks`-ref count (task-05
    controller ruling) — `max(0, len(question.expected_chunks) - len(resolved))` — so `run_eval`
    can sum it into `EvalReport.unresolved_expected_chunks` without a second DB round-trip.
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

    # Moved OUT of the `if question.answerable` branch below (task-05): the rubric judges
    # (context precision/recall) need the same union of retrieved chunk texts regardless of
    # whether the question is answerable, unlike the faithfulness judge which only ever ran on
    # answerable rows. Computing it unconditionally is a pure, cheap Python operation and changes
    # no v1 (pre-task-05) number — `is_supported`'s own call below is unchanged.
    chunk_texts = _dedupe_preserve_order(chunk.text for chunk in retrieval.chunks)

    fully_supported: bool | None
    if question.answerable:
        fully_supported = all(
            judge.is_supported(sentence, chunk_texts) for sentence in split_sentences(answer_text)
        )
        verdict = "PASS" if slugs_hit and fully_supported else "FAIL"
    else:
        # I.3: not applicable to an uncovered row — no answer-support claim to score.
        fully_supported = None
        verdict = "PASS" if (refused and not retrieval_found and not cited_slugs) else "FAIL"

    # Task-05: recall@k/precision@k/MRR, preferring `expected_chunks` (resolved against the LIVE
    # corpus) over the coarser slug-level fallback whenever a resolvable ref exists (task file
    # Interfaces, mode-selection rule).
    resolved_chunk_ids = resolve_expected_chunks(session, question.expected_chunks)
    retrieved_chunk_ids = [str(chunk.chunk_id) for chunk in retrieval.chunks]
    if question.expected_chunks and resolved_chunk_ids:
        retrieval_mode = "chunk"
        expected_ids = [str(chunk_id) for chunk_id in sorted(resolved_chunk_ids, key=str)]
        ir_metrics = retrieval_metrics(expected_ids, retrieved_chunk_ids, mode=retrieval_mode)
    else:
        retrieval_mode = "slug"
        ir_metrics = retrieval_metrics(question.expected_slugs, cited_slugs, mode=retrieval_mode)
    unresolved = max(0, len(question.expected_chunks) - len(resolved_chunk_ids))

    # Task-05: the three rubric judges, only when a `metrics_judge` was supplied — `None` leaves
    # all three `None` so pure retrieval metrics still land without ever reaching an LLM (this is
    # what keeps `tests/test_groundedness.py`'s `ScriptedJudge`-only tests green: it implements
    # only `is_supported`, never `MetricsJudge`'s three extra methods).
    answer_relevance: bool | None = None
    context_precision_value: float | None = None
    context_recall_value: float | None = None
    if metrics_judge is not None:
        answer_relevance = metrics_judge.is_answer_relevant(question.question, answer_text)
        context_precision_value = context_precision(metrics_judge, question.question, chunk_texts)
        context_recall_value = context_recall(metrics_judge, question.reference_answer, chunk_texts)

    row = EvalRow(
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
        question_class=question.question_class,
        persona=question.persona,
        metrics={
            "retrieval_mode": ir_metrics.mode,
            "recall_at_k": ir_metrics.recall_at_k,
            "precision_at_k": ir_metrics.precision_at_k,
            "mrr": ir_metrics.mrr,
            "expected_chunk_hits": ir_metrics.hits,
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "answer_relevance": answer_relevance,
            "context_precision": context_precision_value,
            "context_recall": context_recall_value,
        },
    )
    return row, unresolved


def _class_rollup(question_class: str, rows: Sequence[EvalRow]) -> ClassRollup:
    """One class's rollup (task-05 Interfaces): `passed` counts `verdict == "PASS"` rows;
    `pct_fully_supported` is computed over the class's ANSWERABLE rows only (mirroring `_build_
    report`'s corpus-wide I.3 split), `0.0` when the class has none; `mean_recall_at_k` averages
    `metrics["recall_at_k"]` over rows where it is not `None`, else `None`.
    """
    class_rows = [row for row in rows if row.question_class == question_class]
    passed = sum(1 for row in class_rows if row.verdict == "PASS")

    answerable_rows = [row for row in class_rows if row.answerable]
    pct_fully_supported = (
        100.0 * sum(1 for row in answerable_rows if row.fully_supported) / len(answerable_rows)
        if answerable_rows
        else 0.0
    )

    # `EvalRow.metrics` is a `dict[str, object] | None` (an open JSONB-shaped bucket, per
    # `app.models.eval.EvalResult.metrics`'s own docstring) — narrow each `recall_at_k` value to
    # `float` explicitly rather than trusting the dict's value type, so mypy strict can verify the
    # `sum(...)` below.
    recall_values: list[float] = []
    for row in class_rows:
        recall_at_k = row.metrics.get("recall_at_k") if row.metrics is not None else None
        if isinstance(recall_at_k, int | float):
            recall_values.append(float(recall_at_k))
    mean_recall_at_k = sum(recall_values) / len(recall_values) if recall_values else None

    return ClassRollup(
        question_class=question_class,
        count=len(class_rows),
        passed=passed,
        pct_fully_supported=pct_fully_supported,
        mean_recall_at_k=mean_recall_at_k,
    )


def _build_report(rows: list[EvalRow], *, unresolved_expected_chunks: int = 0) -> EvalReport:
    """Aggregate `rows` into the §9.1/§10 summary numbers (I.3: split by `answerable`) plus the
    task-05 per-class rollups.
    """
    answerable_rows = [row for row in rows if row.answerable]
    uncovered_rows = [row for row in rows if not row.answerable]

    pct_fully_supported = (
        100.0 * sum(1 for row in answerable_rows if row.fully_supported) / len(answerable_rows)
        if answerable_rows
        else 0.0
    )
    refusal_total = len(uncovered_rows)
    refusal_correct = sum(1 for row in uncovered_rows if row.verdict == "PASS")

    # First-occurrence order (mirrors `rows`' own "in file order" contract) rather than sorted —
    # a `by_class` iteration order that matches the eval file's own class grouping reads more
    # naturally in the printed rollup block than an alphabetical resort would.
    class_names = dict.fromkeys(
        row.question_class for row in rows if row.question_class is not None
    )
    by_class = {name: _class_rollup(name, rows) for name in class_names}

    return EvalReport(
        rows=rows,
        pct_fully_supported=pct_fully_supported,
        refusal_correct=refusal_correct,
        refusal_total=refusal_total,
        by_class=by_class,
        unresolved_expected_chunks=unresolved_expected_chunks,
    )


def run_eval(
    session: Session,
    *,
    embedder: Embedder,
    chat_llm: ChatLLM,
    judge: GroundednessJudge,
    questions_path: Path,
    metrics_judge: MetricsJudge | None = None,
) -> EvalReport:
    """Run every question in `questions_path` through the real retrieval + synthesis path and
    score it (task-02 brief Interfaces; task-05 adds the optional `metrics_judge`).

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
        metrics_judge: the optional `MetricsJudge` seam (task-05) the three rubric metrics
            (answer relevance, context precision, context recall) are scored through. `None`
            (the default) leaves those three `EvalRow.metrics` keys `None` and computes only the
            pure-math retrieval metrics — this is what keeps every pre-task-05 caller (including
            `tests/test_groundedness.py`'s `ScriptedJudge`-only tests) working unchanged.

    Returns:
        An `EvalReport` with one `EvalRow` per question, in file order, plus the §9.1/§10 summary
        numbers and the task-05 per-class rollups/unresolved-ref count.
    """
    settings = Settings()
    questions = load_questions(Path(questions_path))
    evaluations = [
        _evaluate_question(
            session,
            embedder=embedder,
            chat_llm=chat_llm,
            judge=judge,
            settings=settings,
            question=question,
            metrics_judge=metrics_judge,
        )
        for question in questions
    ]
    rows = [row for row, _unresolved in evaluations]
    unresolved_expected_chunks = sum(unresolved for _row, unresolved in evaluations)
    return _build_report(rows, unresolved_expected_chunks=unresolved_expected_chunks)


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


def _print_class_rollups(by_class: dict[str, ClassRollup]) -> None:
    """Print the task-05 per-class rollup block (task file Interfaces, exact format)."""
    print("by class:")
    print(f"  {'class':<14} {'n':>3} {'pass':>5} {'supported%':>11} {'recall@k':>9}")
    for rollup in by_class.values():
        recall = "-" if rollup.mean_recall_at_k is None else f"{rollup.mean_recall_at_k:.2f}"
        print(
            f"  {rollup.question_class:<14} {rollup.count:>3} {rollup.passed:>5} "
            f"{rollup.pct_fully_supported:>11.1f} {recall:>9}"
        )


def _print_report(report: EvalReport) -> None:
    """Print one run's per-question table plus the phase-7 summary line (byte-identical to the
    phase-7 stdout — `docs/plans/phase-7-evaluation/verification-record.md` §1 and task-09 both
    depend on this exact line), then the task-05 per-class rollup block when `report.by_class` is
    non-empty (a pre-task-05 `EvalReport(...)` construction — `tests/test_groundedness_cli.py`'s
    `_row`/`_report` helpers — defaults it to `{}`, so nothing extra prints for those).
    """
    _print_table(report.rows)
    print(
        f"groundedness: {report.pct_fully_supported:.1f}% fully supported; "
        f"refusals {report.refusal_correct}/{report.refusal_total} correct"
    )
    if report.by_class:
        _print_class_rollups(report.by_class)


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

    Task-05: the same `OpenAIJudge` instance built from `settings.judge_model` is passed as BOTH
    `judge` (faithfulness) and `metrics_judge` (the three rubric methods) — one object structurally
    satisfies both seams — and `record_run` is told `judge_model=settings.judge_model` (the model
    that ACTUALLY judged this run), not `settings.chat_model`.
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
                metrics_judge=judge,
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
                    judge_model=settings.judge_model,
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
