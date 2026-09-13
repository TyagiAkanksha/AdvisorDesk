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
import json
import logging
import re
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
    context_recall,
    ragas_context_precision,
    retrieval_metrics,
    split_sentences,
    strip_citation_markers,
)
from app.eval.questions import EvalQuestion, load_questions, resolve_expected_chunks
from app.eval.taxonomy import classify_failure, failure_distribution
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
    """One `question_class`'s rollup over a run's rows (task-05 Interfaces), or — as
    `EvalReport.overall` — the whole run's rollup across every class. Fix round 1 (Opus review
    I6) widens this from two metrics to every metric this task records, each a mean over
    APPLICABLE rows, `None` when a rollup has zero applicable rows for that metric (fix round 1
    I4 — printed as `-`, never a false `0.0`).
    """

    question_class: str
    count: int
    # fix round 2 (Opus re-review, N2): how many of `count` rows are chunk-mode — i.e. have a
    # resolved `expected_chunks` ref, so their per-row `recall_at_k`/`mrr` is not `None` and
    # actually feeds `mean_recall_at_k`/`mean_mrr` below. Printed as its own column immediately
    # after `count` so a rollup like "answerable n=40 recall@k=0.83" is never read as "83% recall
    # over all 40 rows" when only a handful were chunk-mode.
    n_scored: int
    passed: int
    # fix round 1 I4: `None` (not `0.0`) when this rollup has no ANSWERABLE rows — a class of all
    # refusals has nothing to say about faithfulness, which reads very differently from "measured
    # 0%".
    pct_fully_supported: float | None
    # fix round 1 C1: the pre-existing per-row `slugs_hit` rate — the coarse "did retrieval
    # surface the right ARTICLE" signal, kept separate from chunk-level recall/precision/MRR so
    # the two granularities never blend. Fix round 2 (N3): averaged over rows with a NON-EMPTY
    # `expected_slugs` only — `slugs_hit` is vacuously `True` by set-inclusion when
    # `expected_slugs == []` (an off-domain/near-miss row has nothing to "hit"), so including
    # those rows inflated this rate toward a false 100%. `None` when no row in the rollup has a
    # non-empty `expected_slugs` (printed as `-`, I4).
    doc_hit_rate: float | None
    # fix round 1 C1: chunk-mode rows ONLY (≥1 resolved `expected_chunks` ref) — a slug-mode or
    # unresolved-ref row's per-row `recall_at_k`/`mrr` is `None` (see `_evaluate_question`) and so
    # never enters this mean; a slug-level number is a different metric on a different scale and
    # must never blend into the same corpus-wide mean as a chunk-mode one (Opus review C1).
    mean_recall_at_k: float | None
    mean_mrr: float | None
    # fix round 1 I2: retained (task-05's own "keep it in the metrics JSON"), but deliberately NOT
    # part of the printed HEADLINE rollup — see `retrieval_metrics`'s docstring for the |E|=1 cap
    # that makes it read as a false floor next to recall@k/MRR.
    mean_precision_at_k: float | None
    # fix round 1 I1/I3: was `mean_answer_relevance`; renamed because RAGAS's own
    # "answer relevancy" names a different metric (mean cosine similarity between the question and
    # back-generated questions) — this is a YES/NO rubric verdict, not that (I3). Answered
    # (non-refused) rows only (I1) — see `_evaluate_question`.
    mean_answer_relevance_rubric: float | None
    # fix round 1 I3: backed by `ragas_context_precision` (the RAGAS rank-aware formula) as of
    # this fix round.
    mean_context_precision: float | None
    mean_context_recall: float | None


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
    # Task-05c brief (the Berlin-payroll-ESPP / divorce-stock-option-split evidence): `True` when
    # a `metrics_judge`-backed `is_refusal` call judged this row's RAW answer text as declining —
    # recorded for every ANSWERED row (`retrieval_found`) regardless of `verdict`/`answerable`,
    # for triage. Defaulted so task-03's shorter constructions (`tests/test_groundedness_cli.py`)
    # keep working unchanged.
    model_declined: bool = False


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
    # Fix round 2 (Opus re-review, N1): how many rows the batched context-precision judge
    # returned a reply for that survived every parse check (`OpenAIJudge._parse_chunk_relevance`)
    # — a reply that is STILL unparsable after fence-stripping falls back to `None` (N/A) rather
    # than a fabricated `0.0`, and this count is the trace that a silent N/A ever happened at all
    # (mirrors `unresolved_expected_chunks`'s own role for the retrieval side). Defaulted so
    # task-03's four-argument `EvalReport(...)` constructions keep working unchanged.
    malformed_judge_replies: int = 0
    # Fix round 1 (Opus review, I6): the whole run's rollup — every `by_class` metric, aggregated
    # once more over EVERY row regardless of class. Defaulted (an empty rollup over zero rows) so
    # task-03's four-argument `EvalReport(...)` constructions keep working unchanged.
    overall: ClassRollup = field(default_factory=lambda: _rollup("overall", []))
    # Task-06: the failure-taxonomy distribution across every row's `metrics["failure_cause"]`
    # (`app.eval.taxonomy.failure_distribution`), ordered by `FAILURE_CAUSES` and omitting
    # zero-count causes. Defaulted so task-03's four-argument `EvalReport(...)` constructions
    # keep working unchanged.
    failure_causes: dict[str, int] = field(default_factory=dict)


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

# Task-05c brief (the Berlin-payroll-ESPP / divorce-stock-option-split evidence, `wave1-b-fix1`):
# a fourth rubric judge, credits a MODEL-level decline as a correct refusal even when retrieval
# cleared the similarity threshold on a near-miss distractor chunk — `refused` (I.2) only ever
# reflects the RETRIEVAL-level signal, so a correct decline over a cleared threshold used to score
# FAIL with no way to tell it apart from a genuine hallucination.
_REFUSAL_PROMPT = (
    "You judge whether an assistant's ANSWER declines to answer the QUESTION. Answer YES if the "
    "answer says the published guidance/sources do not cover the question, refuses, or defers the "
    "reader to a human instead of answering. Answer NO if it attempts an answer, even partially. "
    + _YES_NO_SUFFIX
)

# Fix round 1 (Opus review, Cost ruling): batches what used to be one `is_chunk_relevant` call
# per retrieved chunk into ONE call judging every retrieved chunk at once, replying with a JSON
# array (`OpenAIJudge._parse_chunk_relevance` parses it) rather than the YES/NO + reason format
# the other rubric prompts use. `_CONTEXT_PRECISION_PROMPT` above is untouched and still backs
# `is_chunk_relevant` (kept only for `app.eval.metrics.context_precision`'s own authored-test
# pin — see that function's docstring).
_CONTEXT_PRECISION_BATCH_PROMPT = (
    "You judge whether each SOURCE passage is relevant to answering the QUESTION. Relevant means "
    "a correct answer would plausibly draw on it. Reply with ONLY a JSON array, one object per "
    'SOURCE in the SAME order given, each shaped exactly {"index": <0-based source number>, '
    '"relevant": <true or false>} — no prose, no markdown fences, nothing else.'
)

# Fix round 2 (Opus re-review, N1): the prompt above forbids markdown fences, but nothing enforces
# it — a chat model told to emit JSON commonly wraps it in ``` or ```json anyway. Matches ONE
# leading/trailing fence around the whole reply (optionally tagged `json`, case-insensitive) and
# captures the interior; a reply that isn't fenced simply doesn't match, and `_strip_code_fence`
# falls back to the original (stripped) text unchanged.
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```$", re.DOTALL | re.IGNORECASE)


def _strip_code_fence(content: str) -> str:
    """Strip one leading/trailing markdown code fence (``` or ```json) and surrounding
    whitespace from `content`, if present — otherwise return it merely `.strip()`-ed.
    """
    stripped = content.strip()
    match = _CODE_FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


class OpenAIJudge:
    """The real `GroundednessJudge`/`MetricsJudge`, built from `Settings` (task-02 brief
    Interfaces; task-05 Interfaces for the three rubric methods).

    Mirrors `app.rag.synthesis.OpenAICompatibleChatLLM`'s client construction
    (`from_settings`, `settings.llm_api_key`/`settings.llm_base_url`, the reused
    `embedding_timeout_seconds` request timeout) — but the model is `settings.judge_model`
    (DESIGN D7: a STRONGER model than the answerer's `settings.chat_model`), and the retry budget
    is its OWN dedicated `settings.judge_max_retries` (fix wave D1), not the reused
    `embedding_max_retries` the other two clients share,
    not `chat_model` itself. This moves the recorded groundedness number relative to every run
    before this task (see the implementer report). Judges at `temperature=settings.
    judge_temperature` (`0.0` by default — deterministic verdicts; phase-9 task-05d brief, ruling
    4: `None` omits the request's `temperature` parameter entirely, for a judge model that only
    accepts its own default sampling temperature). Only exercised in the real recorded run
    (`_run_from_cli`) — never in unit tests, which inject `ScriptedJudge`/`FakeMetricsJudge`
    instead.
    """

    def __init__(self, *, client: OpenAI, model: str, temperature: float | None = 0.0) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIJudge:
        """Build the real client from `Settings` — the one non-test constructor.

        Fix wave D1: `max_retries=settings.judge_max_retries` — a DEDICATED retry budget for the
        judge client, not the reused `embedding_max_retries` (task 09's incident needed
        `EMBEDDING_MAX_RETRIES=12` as an env override to survive the judge's own rate limit, which
        only worked because this constructor happened to reuse that setting — the correctly-named
        fix is `judge_max_retries`, config.py's own comment on the field). `timeout` still reuses
        `embedding_timeout_seconds`, which is a per-request budget with no judge-specific reason
        to diverge.
        """
        api_key = settings.llm_api_key.get_secret_value() or "unset"
        client = OpenAI(
            api_key=api_key,
            base_url=settings.llm_base_url,
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.judge_max_retries,
        )
        return cls(
            client=client, model=settings.judge_model, temperature=settings.judge_temperature
        )

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool:
        """Ask the judge model whether `claim_text` is supported by `chunk_texts`.

        Phase-9 task-05d brief, ruling 4: `temperature=self._temperature` is sent only when it is
        not `None` — omitted from the request entirely otherwise, mirroring
        `app.rag.embeddings.OpenAICompatibleEmbedder.embed_texts`'s own two-full-calls style for a
        conditional request parameter (never a sentinel value passed through).
        """
        sources = (
            "\n\n".join(f"[{i + 1}] {text}" for i, text in enumerate(chunk_texts))
            if chunk_texts
            else "(no source passages)"
        )
        user_message = f"SOURCES:\n{sources}\n\nCLAIM: {claim_text}\n\nIs the claim supported?"
        # The message list is a literal at EACH call site (never hoisted into a shared variable)
        # so mypy's bidirectional inference can match it against the SDK's TypedDict union — the
        # same reason `OpenAICompatibleEmbedder.embed_texts` repeats `input=list(texts)` verbatim
        # in both of its own provider branches instead of factoring it out.
        if self._temperature is None:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
        content = response.choices[0].message.content or ""
        return content.strip().upper().startswith("YES")

    def _ask(self, system: str, user: str) -> str:
        """One `chat.completions.create` call — the shared call site for `is_answer_relevant`,
        `is_chunk_relevant`, `is_claim_covered`, `is_refusal` (via `_ask_yes_no`) and
        `rank_chunk_relevance`. `temperature=self._temperature` is sent only when it is not `None`
        (phase-9 task-05d brief, ruling 4 — same rule as `is_supported`'s own call site above);
        returns the stripped content.
        """
        # See `is_supported`'s own comment above: the message list stays a literal at each call
        # site rather than a shared variable, for mypy's benefit.
        if self._temperature is None:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
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

        M5 (Opus review, ledgered as a ride item): a reply that doesn't start with "YES" — a
        genuinely malformed one included — is treated as NO, never raised. Low risk with an
        explicit format instruction and gpt-4o, but this silently biases toward NO with no counter
        for how often a reply is actually malformed versus a real "NO".
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

    def is_refusal(self, question: str, answer_text: str) -> bool:
        """Ask the judge model whether `answer_text` declines to answer `question` (task-05c
        brief: the Berlin-payroll-ESPP / divorce-stock-option-split evidence) instead of
        answering it, even partially.
        """
        user_message = f"QUESTION: {question}\n\nANSWER: {answer_text}\n\nDoes the answer decline?"
        return self._ask_yes_no(_REFUSAL_PROMPT, user_message)

    def rank_chunk_relevance(self, question: str, chunk_texts: Sequence[str]) -> list[bool] | None:
        """One relevance verdict per `chunk_texts`, in order — a SINGLE judge call over every
        retrieved chunk (fix round 1, Cost ruling) rather than the one-call-per-chunk
        `is_chunk_relevant` this replaces operationally. Feeds
        `app.eval.metrics.ragas_context_precision`. Returns `[]` without a call when
        `chunk_texts` is empty (nothing to judge); returns `None` (fix round 2, N1) when the
        reply is unparsable even after fence-stripping — never a fabricated all-`False` verdict
        list, which used to score as a real-looking `0.0` for context precision.
        """
        if not chunk_texts:
            return []
        sources = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(chunk_texts))
        user_message = (
            f"QUESTION: {question}\n\nSOURCES:\n{sources}\n\nJudge all {len(chunk_texts)} sources."
        )
        content = self._ask(_CONTEXT_PRECISION_BATCH_PROMPT, user_message)
        return self._parse_chunk_relevance(content, len(chunk_texts))

    def _parse_chunk_relevance(self, content: str, expected_count: int) -> list[bool] | None:
        """Strictly parse `rank_chunk_relevance`'s `[{"index": int, "relevant": bool}, ...]`
        reply (fix round 1, Cost ruling). `content` is first passed through `_strip_code_fence`
        (fix round 2, N1) so a reply wrapped in a ``` or ```json fence — the single most common
        deviation for a chat model told to emit bare JSON — still parses to the SAME verdicts as
        an unfenced reply. ANYTHING still unexpected after that — invalid JSON, not a list, the
        wrong length, a missing/duplicate/out-of-range `index`, a non-bool `relevant` — returns
        `None` (fix round 2, N1: not-applicable, consistent with ruling I4 — never a fabricated
        `0.0`) plus a WARNING log naming the RAW (unstripped) reply, so a genuinely malformed-
        output rate is visible in logs without ever aborting a whole eval run over one bad reply.
        """
        stripped = _strip_code_fence(content)
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            logger.warning("context-precision judge returned unparseable JSON: %r", content)
            return None
        if not isinstance(parsed, list) or len(parsed) != expected_count:
            logger.warning("context-precision judge returned malformed verdicts: %r", content)
            return None

        verdicts: list[bool | None] = [None] * expected_count
        for entry in parsed:
            if not isinstance(entry, dict):
                logger.warning("context-precision judge returned malformed verdicts: %r", content)
                return None
            index = entry.get("index")
            relevant = entry.get("relevant")
            if not isinstance(index, int) or isinstance(index, bool):
                logger.warning("context-precision judge returned malformed verdicts: %r", content)
                return None
            if not isinstance(relevant, bool):
                logger.warning("context-precision judge returned malformed verdicts: %r", content)
                return None
            if not (0 <= index < expected_count) or verdicts[index] is not None:
                logger.warning("context-precision judge returned malformed verdicts: %r", content)
                return None
            verdicts[index] = relevant

        if any(verdict is None for verdict in verdicts):
            logger.warning("context-precision judge returned malformed verdicts: %r", content)
            return None
        return [bool(verdict) for verdict in verdicts]


def _dedupe_preserve_order(texts: Iterable[str]) -> list[str]:
    """The union of `texts`, deduped, in first-occurrence order (`dict.fromkeys` trick)."""
    return list(dict.fromkeys(texts))


@dataclass(frozen=True)
class _ClassificationSnapshot:
    """A `app.eval.taxonomy.ClassifiableRow` built from `_evaluate_question`'s own already-
    computed local values (task-06 Interfaces) — classified BEFORE the frozen `EvalRow` below is
    constructed, since a frozen row must never be mutated after the fact.
    """

    answerable: bool
    refused: bool
    verdict: str
    fully_supported: bool | None
    top_similarity: float | None
    cited_slugs: Sequence[str]


def _model_declined(metrics_judge: MetricsJudge, question: str, answer_text: str) -> bool:
    """Call `metrics_judge.is_refusal(question, answer_text)` if the seam actually implements it
    (task-05c brief), else `False`.

    This is the SEMANTIC counterpart of `app.services.chat._DECLINE_PHRASE` (fix wave D5, M5) —
    that module's reporting heuristic does a cheap casefolded substring probe (it must not make an
    LLM call on the `weak_queries` reporting path), while this function asks the judge model
    whether `answer_text` is a genuine refusal. `app.services.chat._DECLINE_PHRASE`'s own comment
    names this function as ITS counterpart; this docstring closes the loop the other way so an
    edit to either side is more likely to prompt a look at the other.

    Judgment call (flagged for controller review): `MetricsJudge.is_refusal` is a Protocol member
    as of this task, satisfied by `OpenAIJudge` and by every `MetricsJudge` fake
    `tests/test_eval_refusal_semantics.py` defines — but three PRE-EXISTING `MetricsJudge`-shaped
    fakes this task must not touch (`tests/test_eval_metrics.py::FakeMetricsJudge`,
    `tests/test_eval_metrics_fix_round1.py::RecordingMetricsJudge`/`MalformedReplyMetricsJudge`)
    predate `is_refusal` and are exercised through `run_eval(..., metrics_judge=...)` on ANSWERED
    rows (e.g. `test_eval_metrics.py::test_run_eval_records_chunk_level_metrics_and_class_rollups`
    asserts `answer_relevance_rubric is True`, which only happens for a non-refused row). An
    unconditional `metrics_judge.is_refusal(...)` call would raise `AttributeError` on all three
    and break the "every existing pin stays green" gate. `getattr` falls back to `False` — the
    same value `model_declined` already defaults to — only for a `metrics_judge` that genuinely
    lacks the method; every fake this task itself authors, and the real `OpenAIJudge`, defines it
    and is called exactly as the Interfaces specify.
    """
    is_refusal = getattr(metrics_judge, "is_refusal", None)
    if is_refusal is None:
        return False
    return bool(is_refusal(question, answer_text))


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

    # Task-05c brief (the Berlin-payroll-ESPP / divorce-stock-option-split evidence): one
    # `is_refusal` call, on the RAW answer text, per ANSWERED row (`retrieval_found` — the same
    # boolean as `not refused`) — never for a full miss, never without a `metrics_judge`. Computed
    # here, before the uncovered-row verdict rule below, since that rule now reads it.
    model_declined = False
    if metrics_judge is not None and retrieval_found:
        model_declined = _model_declined(metrics_judge, question.question, answer_text)

    # Moved OUT of the `if question.answerable` branch below (task-05): the rubric judges
    # (context precision/recall) need the same union of retrieved chunk texts regardless of
    # whether the question is answerable, unlike the faithfulness judge which only ever ran on
    # answerable rows. Computing it unconditionally is a pure, cheap Python operation and changes
    # no v1 (pre-task-05) number — `is_supported`'s own call below is unchanged.
    chunk_texts = _dedupe_preserve_order(chunk.text for chunk in retrieval.chunks)

    fully_supported: bool | None
    # Controller addition (p9 t05c): the claim(s) — post `[n]`-marker stripping, exactly what
    # `judge.is_supported` saw — that the faithfulness judge rejected for this row. Two triages
    # this phase could not name which sentence failed.
    unsupported_sentences: list[str]
    if question.answerable:
        # Task-05b (task-10 re-review §3): the judge sees the answer with `[n]` citation markers
        # stripped and letter-less list-marker fragments dropped — the answerer's and judge's
        # bracket-numbering spaces disagree (row 2) and the sentence splitter cuts inside ordinal
        # list markers (row 1), so both artifacts must never reach the judge as "claims". The
        # PERSISTED `answer_text` below stays the raw, un-stripped wire answer.
        judged_sentences = split_sentences(strip_citation_markers(answer_text))
        # Same short-circuit the old `all(genexpr)` had — stop at the FIRST unsupported sentence
        # ("keep it cheap", the controller's own cost constraint: no extra judge calls beyond what
        # already decided `fully_supported`) — so `unsupported_sentences` names that one sentence,
        # not necessarily every failing sentence in a multi-failure answer.
        unsupported_sentences = []
        fully_supported = True
        for sentence in judged_sentences:
            if not judge.is_supported(sentence, chunk_texts):
                fully_supported = False
                unsupported_sentences.append(sentence)
                break
        verdict = "PASS" if slugs_hit and fully_supported else "FAIL"
    else:
        # I.3: not applicable to an uncovered row — no answer-support claim to score, so nothing
        # was judged and nothing was rejected.
        fully_supported = None
        unsupported_sentences = []
        # Task-05c brief (the fix): a retrieval-level refusal (no citations attached) PASSes as
        # before, OR the answerer declined even though retrieval cleared the threshold on a
        # near-miss distractor (Berlin-payroll-ESPP / divorce-stock-option-split evidence) —
        # citations may be attached in that case, so "no citations" must never gate this branch.
        verdict = "PASS" if (refused and not cited_slugs) or model_declined else "FAIL"

    # Task-05: recall@k/precision@k/MRR, preferring `expected_chunks` (resolved against the LIVE
    # corpus) over the coarser slug-level fallback whenever a resolvable ref exists (task file
    # Interfaces, mode-selection rule). M2 (Opus review, ledgered as a ride item, captioned here):
    # a PARTIALLY-resolved question (2 of 3 refs resolve) still counts as `mode="chunk"` with a
    # SHRUNKEN expected set (`len(resolved_chunk_ids)`, not the authored `len(expected_chunks)`)
    # — recall's denominator is the resolved refs, not the authored ones, which can read as
    # inflated recall for a corpus with gaps.
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

    # Fix round 1 (Opus review, C1): recall@k/precision@k/MRR are corpus-comparable ONLY at chunk
    # granularity — a slug-mode value mixes 1-2 slugs against ~6 chunk ids, a different metric on
    # a different scale, and the OLD behaviour of silently falling back to a slug-level number
    # blended chunk-mode and slug-mode rows into one unlabelled rollup column. A slug-mode (or
    # unresolved-`expected_chunks`) row now scores `None` for all three here — excluded from the
    # class/overall means (`_rollup` below), never downgraded into them. `ir_metrics.hits`/
    # `retrieved_chunk_ids` are UNCHANGED (still computed above) since C1 names only
    # recall/precision/MRR; `expected_chunk_hits` holding a slug-level count in slug mode (M4) is
    # a separate, already-forward-flagged concern for task 06, not touched here.
    scored_recall = ir_metrics.recall_at_k if retrieval_mode == "chunk" else None
    scored_precision = ir_metrics.precision_at_k if retrieval_mode == "chunk" else None
    # M3 (Opus review, ledgered as a ride item, captioned here): this per-ROW value is a
    # reciprocal rank, not a mean — "MRR" (Mean Reciprocal Rank) is that value's corpus-wide
    # average (`ClassRollup.mean_mrr`, below), never this single row's own number.
    scored_mrr = ir_metrics.mrr if retrieval_mode == "chunk" else None

    # Fix round 1 (Opus review, I1 + I3 + Cost): the rubric judges, only when a `metrics_judge`
    # was supplied — `None` leaves every one of them `None` so pure retrieval metrics still land
    # without ever reaching an LLM (this is what keeps `tests/test_groundedness.py`'s
    # `ScriptedJudge`-only tests green: it implements only `is_supported`, never `MetricsJudge`'s
    # other methods).
    answer_relevance_rubric: bool | None = None
    context_precision_value: float | None = None
    context_recall_value: float | None = None
    # Fix round 2 (Opus re-review, N1): `True` only when the batched context-precision judge
    # reply was STILL unparsable after fence-stripping (`rank_chunk_relevance` returned `None`) —
    # never set when there was simply no `metrics_judge` at all (that case has nothing to call
    # malformed).
    judge_reply_malformed = False
    if metrics_judge is not None:
        # I1: judged only when the row was ANSWERED (retrieval found content, the model did not
        # refuse) — a refusal has no "does this answer address the question" claim to score, and
        # the rubric prompt's own "answer NO to a refusal asked in good faith" instruction would
        # otherwise misscore a CORRECT refusal as failing relevance. No judge call at all for a
        # refused row.
        if not refused:
            answer_relevance_rubric = metrics_judge.is_answer_relevant(
                question.question, answer_text
            )
        # I3 + Cost: ONE batched call over every retrieved chunk (`rank_chunk_relevance`) feeds
        # the RAGAS rank-aware `ragas_context_precision` formula — replaces what used to be one
        # `is_chunk_relevant` call per chunk. Fix round 2, N1: `None` means the reply was
        # unparsable — `context_precision` stays `None` (N/A) rather than scoring a fabricated
        # `ragas_context_precision([False, ...]) == 0.0`, and the row is flagged so the count is
        # never silent.
        chunk_relevance = metrics_judge.rank_chunk_relevance(question.question, chunk_texts)
        if chunk_relevance is None:
            judge_reply_malformed = True
        else:
            context_precision_value = ragas_context_precision(chunk_relevance)
        context_recall_value = context_recall(metrics_judge, question.reference_answer, chunk_texts)

    row_metrics: dict[str, object] = {
        "retrieval_mode": retrieval_mode,
        "recall_at_k": scored_recall,
        "precision_at_k": scored_precision,
        "mrr": scored_mrr,
        "expected_chunk_hits": ir_metrics.hits,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        # Fix round 1 (Opus review, I3), made the sole key in round 1b (controller amendment
        # commit b63a9eb re-pinned the authored test onto this name): RAGAS's own "answer
        # relevancy" names a different metric (mean cosine similarity between the question and
        # back-generated questions) — this is a YES/NO rubric verdict, not that — so the old
        # `answer_relevance` key is gone; `answer_relevance_rubric` is the only key.
        "answer_relevance_rubric": answer_relevance_rubric,
        "context_precision": context_precision_value,
        "context_recall": context_recall_value,
        # Fix round 2 (Opus re-review, N1): `True` iff the batched context-precision judge's
        # reply was still unparsable after fence-stripping (see `judge_reply_malformed`,
        # above) — always present (never omitted) so `EvalReport.malformed_judge_replies`
        # (`_build_report`) can count it with a plain `.get(...)`, `False` whenever there was
        # no `metrics_judge` at all.
        "judge_reply_malformed": judge_reply_malformed,
        # Task-05c brief: recorded for every ANSWERED row a `metrics_judge` was supplied for —
        # `False` whenever there was no `metrics_judge` at all or the row was a full miss (see
        # `_model_declined` above).
        "model_declined": model_declined,
        # Controller addition (p9 t05c): the claim(s) the faithfulness judge rejected for this
        # row (see the `unsupported_sentences` comment above) — always present, `[]` when nothing
        # was rejected (or nothing was judged at all, an uncovered row).
        "unsupported_sentences": unsupported_sentences,
    }

    # Task-06: classify the failure cause from the LOCAL values computed above — never from the
    # (not-yet-built) frozen `EvalRow`, and never by mutating it afterwards. `human_verdict` stays
    # `None` at run time — human labels arrive offline through task 08's scorecard, which reads
    # the persisted rows.
    classification_snapshot = _ClassificationSnapshot(
        answerable=question.answerable,
        refused=refused,
        verdict=verdict,
        fully_supported=fully_supported,
        top_similarity=retrieval.top_similarity,
        cited_slugs=cited_slugs,
    )
    row_metrics["failure_cause"] = classify_failure(
        classification_snapshot,
        threshold=settings.similarity_threshold,
        expected_chunk_hits=ir_metrics.hits,
    )

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
        metrics=row_metrics,
        model_declined=model_declined,
    )
    return row, unresolved


def _as_float(value: object | None) -> float | None:
    """Narrow one `EvalRow.metrics` value (an open `dict[str, object]`-shaped JSONB bucket, per
    `app.models.eval.EvalResult.metrics`'s own docstring) to a `float` for averaging. A bool
    verdict (e.g. `answer_relevance_rubric`) becomes `1.0`/`0.0` so its class mean reads as the
    fraction judged true. Anything else — including `None` — is "not applicable" for this row.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    return None


def _as_failure_cause(value: object | None) -> str | None:
    """Narrow one `EvalRow.metrics["failure_cause"]` value to `str | None` for
    `app.eval.taxonomy.failure_distribution` — mirrors `_as_float`'s own narrowing role for the
    mean helpers below (a plain `dict[str, object]` lookup is `object`-typed to mypy even though
    `classify_failure`'s own return type is always `str | None`).
    """
    return value if isinstance(value, str) else None


def _mean_metric(rows: Sequence[EvalRow], key: str) -> float | None:
    """Mean of `row.metrics[key]` over rows where that key is present and applicable (fix round
    1, I6) — `None` (printed as `-`, I4) when no row in `rows` has an applicable value.
    """
    values: list[float] = []
    for row in rows:
        if row.metrics is None:
            continue
        parsed = _as_float(row.metrics.get(key))
        if parsed is not None:
            values.append(parsed)
    return sum(values) / len(values) if values else None


def _rollup(label: str, rows: Sequence[EvalRow]) -> ClassRollup:
    """One label's rollup — `label` is a `question_class` for a `by_class` entry, or `"overall"`
    for `EvalReport.overall` (fix round 1, I6: every metric this task records, aggregated once
    per class AND once over the whole run). `passed` counts `verdict == "PASS"` rows;
    `pct_fully_supported`/`doc_hit_rate`/every `mean_*` field is `None` (fix round 1, I4 — printed
    as `-`) when `rows` has zero applicable entries for that particular metric.
    """
    passed = sum(1 for row in rows if row.verdict == "PASS")

    # Fix round 2 (Opus re-review, N2): a row is "scored" for recall@k/MRR purposes iff it's
    # chunk-mode — `_evaluate_question` only ever sets `recall_at_k` to a non-`None` value in
    # that mode (see its own C1 comment) — so this is exactly the row count `mean_recall_at_k`/
    # `mean_mrr` are averaged over, made visible instead of implicit.
    n_scored = sum(
        1 for row in rows if row.metrics is not None and row.metrics.get("recall_at_k") is not None
    )

    answerable_rows = [row for row in rows if row.answerable]
    pct_fully_supported = (
        100.0 * sum(1 for row in answerable_rows if row.fully_supported) / len(answerable_rows)
        if answerable_rows
        else None
    )
    # Fix round 2 (Opus re-review, N3): averaged over rows with a NON-EMPTY `expected_slugs`
    # only — `slugs_hit` is vacuously `True` (empty set ⊆ any set) for a row that expects nothing,
    # so an off-domain/near-miss class (every row's `expected_slugs == []`) used to read a false
    # 100% here instead of "not applicable".
    doc_hit_rows = [row for row in rows if row.expected_slugs]
    doc_hit_rate = (
        sum(1 for row in doc_hit_rows if row.slugs_hit) / len(doc_hit_rows)
        if doc_hit_rows
        else None
    )

    return ClassRollup(
        question_class=label,
        count=len(rows),
        n_scored=n_scored,
        passed=passed,
        pct_fully_supported=pct_fully_supported,
        doc_hit_rate=doc_hit_rate,
        mean_recall_at_k=_mean_metric(rows, "recall_at_k"),
        mean_mrr=_mean_metric(rows, "mrr"),
        mean_precision_at_k=_mean_metric(rows, "precision_at_k"),
        mean_answer_relevance_rubric=_mean_metric(rows, "answer_relevance_rubric"),
        mean_context_precision=_mean_metric(rows, "context_precision"),
        mean_context_recall=_mean_metric(rows, "context_recall"),
    )


def _build_report(rows: list[EvalRow], *, unresolved_expected_chunks: int = 0) -> EvalReport:
    """Aggregate `rows` into the §9.1/§10 summary numbers (I.3: split by `answerable`) plus the
    task-05 per-class rollups and (fix round 1, I6) the whole-run `overall` rollup.

    NOTE: this function's own `pct_fully_supported` (the top-level, phase-7 summary number) stays
    `0.0` when there are no answerable rows — UNCHANGED, since the phase-7 "groundedness: X% fully
    supported" line must stay byte-identical. Fix round 1's I4 ("`-` instead of `0.0`") applies
    only to `ClassRollup.pct_fully_supported` (the per-class/overall rollup), never to this
    report-level field.
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

    # Fix round 2 (Opus re-review, N1): count across every row, not only answerable ones — a
    # malformed batched-judge reply can happen for any row a `metrics_judge` scored.
    malformed_judge_replies = sum(
        1 for row in rows if row.metrics is not None and row.metrics.get("judge_reply_malformed")
    )

    # First-occurrence order (mirrors `rows`' own "in file order" contract) rather than sorted —
    # a `by_class` iteration order that matches the eval file's own class grouping reads more
    # naturally in the printed rollup block than an alphabetical resort would.
    class_names = dict.fromkeys(
        row.question_class for row in rows if row.question_class is not None
    )
    by_class = {
        name: _rollup(name, [row for row in rows if row.question_class == name])
        for name in class_names
    }
    overall = _rollup("overall", rows)

    # Task-06: the distribution of `metrics["failure_cause"]` across every row (a row with no
    # `metrics` at all — pre-task-05 rows never persisted this way — reads as `None`, dropped by
    # `failure_distribution` like any other non-failure).
    failure_causes = failure_distribution(
        _as_failure_cause(row.metrics.get("failure_cause")) if row.metrics is not None else None
        for row in rows
    )

    return EvalReport(
        rows=rows,
        pct_fully_supported=pct_fully_supported,
        refusal_correct=refusal_correct,
        refusal_total=refusal_total,
        by_class=by_class,
        unresolved_expected_chunks=unresolved_expected_chunks,
        malformed_judge_replies=malformed_judge_replies,
        overall=overall,
        failure_causes=failure_causes,
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
    # Fix round 2 (Opus re-review, I2 — source-side kill): `load_questions` accepts a top-level
    # `[]` cleanly, and without this guard an empty (or over-narrowly-filtered) questions file
    # would silently produce a genuine, zero-row `kind='answer'` `EvalReport` — `_run_from_cli`
    # then persists it as a real run via `record_run`, `pct_fully_supported=0.0` and
    # `total_questions=0`, that later becomes `latest_runs(...)[0]`, exactly what
    # `app.services.proposals.propose_content_fix` stamps as a proposal's `eval_run_before_id`.
    # `check_acceptance` now also refuses a zero-question before-run directly (the belt); this is
    # the buckle — refusing before any embedder/chat/judge call is even attempted.
    if not questions:
        raise ValueError(
            f"{questions_path}: no questions to evaluate — refusing to run an empty eval."
        )
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


def _fmt_pct(value: float | None, *, already_pct: bool = False) -> str:
    """Render a percentage cell at one decimal, or `-` when the metric has zero applicable rows
    (fix round 1, I4). `value` is a 0-1 fraction by default (scaled here to 0-100); pass
    `already_pct=True` for a value already on the 0-100 scale (`pct_fully_supported`).
    """
    if value is None:
        return "-"
    return f"{value:.1f}" if already_pct else f"{value * 100:.1f}"


def _fmt_score(value: float | None) -> str:
    """Render a 0-1 IR score (recall@k / MRR / precision@k) at two decimals, or `-` when the
    metric has zero applicable rows (fix round 1, I4)."""
    return "-" if value is None else f"{value:.2f}"


def _print_headline_rollup_row(rollup: ClassRollup) -> None:
    """One row of the "by class" headline table (fix round 1: C1's `doc_hit%` column, I2's
    precision@k exclusion, I4's `-` cells; fix round 2, N2: `n_scored` immediately after `n`)."""
    print(
        f"  {rollup.question_class:<14} {rollup.count:>3} {rollup.n_scored:>8} {rollup.passed:>5} "
        f"{_fmt_pct(rollup.pct_fully_supported, already_pct=True):>11} "
        f"{_fmt_pct(rollup.doc_hit_rate):>9} "
        f"{_fmt_score(rollup.mean_recall_at_k):>9} "
        f"{_fmt_score(rollup.mean_mrr):>6}"
    )


def _print_judge_metrics_rollup_row(rollup: ClassRollup) -> None:
    """One row of the "judge metrics" table (fix round 1, I6): precision@k (I2: not a headline
    number, but still aggregated+printed here) plus the three rubric-judge means.
    """
    print(
        f"  {rollup.question_class:<14} {rollup.count:>3} "
        f"{_fmt_score(rollup.mean_precision_at_k):>11} "
        f"{_fmt_pct(rollup.mean_answer_relevance_rubric):>11} "
        f"{_fmt_pct(rollup.mean_context_precision):>14} "
        f"{_fmt_pct(rollup.mean_context_recall):>11}"
    )


def _print_class_rollups(report: EvalReport) -> None:
    """Print the task-05 per-class rollup blocks, widened by fix round 1 (Opus review):

    - C1: retrieval recall@k/MRR are chunk-mode-only means (rows with a resolved
      `expected_chunks` ref); slug-level coverage is reported separately as `doc_hit%` (the
      pre-existing `slugs_hit` rate) so the two granularities are never blended into one column.
    - I2: precision@k is NOT a headline retrieval number (see `retrieval_metrics`'s docstring for
      why) — it appears only in the second, "judge metrics" block, alongside the three
      rubric-judge means (I6).
    - I4: every cell prints `-`, never `0.0`, when its class/overall rollup has zero applicable
      rows for that metric.
    - I6: both blocks end with an `overall` row (`report.overall`) — every metric aggregated once
      more across the WHOLE run, not only per class.
    - N2 (fix round 2, Opus re-review): the headline block gains an `n_scored` column immediately
      after `n` — how many of that rollup's rows are actually chunk-mode (i.e. behind
      `recall@k`/`mrr`), since `n` alone conflated "rows in this class" with "rows this metric is
      averaged over".
    """
    print("by class:")
    print(
        f"  {'class':<14} {'n':>3} {'n_scored':>8} {'pass':>5} {'supported%':>11} "
        f"{'doc_hit%':>9} {'recall@k':>9} {'mrr':>6}"
    )
    for rollup in report.by_class.values():
        _print_headline_rollup_row(rollup)
    _print_headline_rollup_row(report.overall)

    print("judge metrics by class:")
    print(
        f"  {'class':<14} {'n':>3} {'precision@k':>11} {'rel_rubric%':>11} "
        f"{'ctx_precision%':>14} {'ctx_recall%':>11}"
    )
    for rollup in report.by_class.values():
        _print_judge_metrics_rollup_row(rollup)
    _print_judge_metrics_rollup_row(report.overall)


def _print_report(report: EvalReport) -> None:
    """Print one run's per-question table plus the phase-7 summary line (byte-identical to the
    phase-7 stdout — `docs/plans/phase-7-evaluation/verification-record.md` §1 and task-09 both
    depend on this exact line), then the task-05 per-class rollup blocks (widened by fix round 1
    — see `_print_class_rollups`) when `report.by_class` is non-empty (a pre-task-05
    `EvalReport(...)` construction — `tests/test_groundedness_cli.py`'s `_row`/`_report` helpers —
    defaults it to `{}`, so nothing extra prints for those).
    """
    _print_table(report.rows)
    print(
        f"groundedness: {report.pct_fully_supported:.1f}% fully supported; "
        f"refusals {report.refusal_correct}/{report.refusal_total} correct"
    )
    # Fix round 2 (Opus re-review, N1/N2): both lines are ADDITIONS below the byte-identical
    # phase-7 summary line above, printed only when the count is > 0 — a healthy run (no
    # unresolved refs, no malformed judge replies) prints neither, so this never appears on a
    # clean run's stdout.
    if report.malformed_judge_replies > 0:
        print(f"malformed judge replies: {report.malformed_judge_replies}")
    if report.unresolved_expected_chunks > 0:
        print(f"unresolved expected_chunks refs: {report.unresolved_expected_chunks}")
    if report.by_class:
        _print_class_rollups(report)
    # Task-06: the failure-taxonomy distribution, printed AFTER the per-class rollup blocks and
    # only when at least one cause was assigned — a clean run (nothing failed) prints nothing
    # extra, same convention as the two lines above.
    if report.failure_causes:
        print("failure causes:")
        for cause, count in report.failure_causes.items():
            print(f"  {cause:<24} {count:>3}")


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
    # Fix wave D2 (t03 review M1): `--no-persist` means no run this invocation is ever written,
    # so a `--compare-to` alongside it can never have a new run to diff against — the `if
    # before_id is not None and last_run is not None:` block below simply never fires, and a
    # caller who asked for a comparison gets silence instead of a diff with no clue why. A printed
    # warning, no behaviour change: `record_run` is not called, and no exception is raised — the
    # run still executes and prints its own report table.
    if args.no_persist and args.compare_to is not None:
        print(
            "warning: --no-persist with --compare-to has no effect — no run is persisted this "
            f"invocation, so there is nothing new to compare against {args.compare_to!r}."
        )
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
                # Fix wave B4 (final-review I4): mirrors `agent_suite.py`'s own CLI
                # (`_print_task_line`'s caller, `agent_suite.py:796`) — printed for EVERY
                # persisted run in this invocation (a `--runs N` family included), needed live
                # to feed `accept_proposal(eval_run_after_id=...)` without a `psql` round-trip.
                print(f"recorded eval_runs id={last_run.id}")

        if not args.no_persist:
            session.commit()

        if args.runs > 1:
            _print_stability(reports, label=args.label)

        if before_id is not None and last_run is not None:
            diff = compare_runs(session, before_id, last_run.id)
            # Fix wave round 2 (M4): prints the FAMILY MEANS either side of the arrow — the exact
            # numbers `check_acceptance`'s pct rung judges — instead of the two NAMED runs' own
            # single-run scalars, which silently disagreed with the family-mean delta in
            # parentheses whenever either run belonged to a `--runs N` family.
            print(
                f"compare {diff.before_id} -> {diff.after_id}: "
                f"pct {diff.pct_before:.1f} -> {diff.pct_after:.1f} ({diff.pct_delta:+.1f}; "
                f"family means over {len(diff.before_family)}/{len(diff.after_family)} runs); "
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
