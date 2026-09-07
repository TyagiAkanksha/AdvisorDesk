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

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.rag.embeddings import Embedder, OpenAICompatibleEmbedder
from app.rag.retrieval import retrieve
from app.rag.synthesis import SYSTEM_PROMPT, ChatLLM, OpenAICompatibleChatLLM

__all__ = [
    "EvalReport",
    "EvalRow",
    "GroundednessJudge",
    "OpenAIJudge",
    "run_eval",
]

# `apps/api/app/eval/groundedness.py` -> `app/eval/` -> `app/` -> `apps/api/` -> `apps/` -> repo
# root: mirrors `app/seed.py`'s own `_REPO_ROOT` computation, one `.parent` deeper since this
# module lives one directory below `app/seed.py`'s (`app/eval/` vs `app/`).
_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_DEFAULT_QUESTIONS_PATH: Path = _REPO_ROOT / "seed" / "eval_questions.yaml"

# A dependency-free sentence splitter: `.`/`!`/`?` followed by whitespace. Good enough for the
# short, single-paragraph answers this harness judges sentence-by-sentence (brief: "call the judge
# per sentence") — the exact tokenizer is explicitly unspecified by the brief
# (`tests/test_groundedness.py` module docstring, judgment call 3): `ScriptedJudge` pins outcomes
# by MARKER CONTENT, never by call count/order, so no test depends on this regex's exact behavior
# beyond "splits on sentence-ending punctuation."
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class EvalRow:
    """One eval question's outcome (task-02 brief Interfaces)."""

    question: str
    answerable: bool
    expected_slugs: list[str]
    cited_slugs: list[str]
    slugs_hit: bool
    fully_supported: bool | None
    refused: bool
    verdict: str


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
            mapping, or is missing/mistypes one of the three required keys.
    """
    raw = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{questions_path}: eval questions file must parse to a top-level list")

    questions: list[_EvalQuestion] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{questions_path}[{index}]: item is not a mapping: {item!r}")
        question = item.get("question")
        expected_slugs = item.get("expected_slugs")
        answerable = item.get("answerable")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{questions_path}[{index}]: 'question' must be a non-blank string")
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
        session, embedder, question.question, threshold=settings.similarity_threshold
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


def _run_from_cli() -> None:
    """`python -m app.eval.groundedness`: wire the REAL embedder/chat LLM/judge from `Settings`
    and run the real recorded eval against the seeded local-db stack (task-02 brief Step 5 —
    deferred to task-03's separate real run, not exercised by unit tests, ruling H: DO NOT run a
    full scored eval against the DB from an automated test/import — the local corpus is not
    seeded yet at the time this module is authored).

    Builds its own engine/session (mirrors `app/seed.py::_run_from_cli`'s same self-contained CLI
    wiring pattern — `app.eval` is a standalone script, not a FastAPI route, so it has no
    `app.state` to read `app.routes.deps.get_session`/`get_embedder`/`get_chat_llm` from).
    """
    settings = Settings()
    engine = make_engine(settings.database_url.get_secret_value())
    session_factory = make_session_factory(engine)
    embedder = OpenAICompatibleEmbedder.from_settings(settings)
    chat_llm = OpenAICompatibleChatLLM.from_settings(settings)
    judge = OpenAIJudge.from_settings(settings)

    session = session_factory()
    try:
        report = run_eval(
            session,
            embedder=embedder,
            chat_llm=chat_llm,
            judge=judge,
            questions_path=_DEFAULT_QUESTIONS_PATH,
        )
    finally:
        session.close()
    engine.dispose()

    _print_table(report.rows)
    print(
        f"groundedness: {report.pct_fully_supported:.1f}% fully supported; "
        f"refusals {report.refusal_correct}/{report.refusal_total} correct"
    )


if __name__ == "__main__":
    _run_from_cli()
