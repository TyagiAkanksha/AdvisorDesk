"""Metrics v2 (phase-9 task-05): pure IR math (recall@k/precision@k/MRR), the sentence
splitter, and the rubric-judge seam + score functions (context precision/recall).

Spec: `docs/plans/phase-9-eval-data-loop/task-05-metrics-v2.md` Interfaces. Deliberately free of
DB/network/`Settings` (the task file's own module docstring: "pure — no DB, no network, no
`Settings`") so every function here is unit-testable with plain values, and so
`app/eval/groundedness.py` (which DOES touch the DB/network/`Settings`) can import from this
module without this module ever importing back — no cycle to reason about.

`GroundednessJudge` moves here (it used to live in `groundedness.py`) rather than being declared
there and imported into this module under `TYPE_CHECKING` — the task file's own Interfaces block
offers both shapes as equally safe and names this one "simpler and preferred". Nothing outside
`app/eval/groundedness.py`'s own module ever imported `GroundednessJudge` by name (verified via
`grep -rn GroundednessJudge apps/api` — the only hits are a docstring/comment in
`tests/test_groundedness.py`, never an import), so relocating it costs nothing;
`groundedness.py` re-exports it (`from app.eval.metrics import GroundednessJudge`) so its own
`__all__` entry keeps working unchanged. `MetricsJudge` widens the same shape with the three new
rubric verdicts, so one real object (`OpenAIJudge`) can satisfy both seams at once.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

# Moved verbatim from `groundedness._SENTENCE_BOUNDARY_RE` (same regex, same rationale): a
# dependency-free sentence splitter, `.`/`!`/`?` followed by whitespace — good enough for the
# short, single-paragraph answers/reference-answer claims this harness judges sentence-by-sentence.
# The exact tokenizer is deliberately unpinned (`tests/test_groundedness.py` module docstring,
# judgment call 3): every test that exercises it scripts its fake judges by MARKER CONTENT, never
# by call count/order.
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")

# Task-05b (from the task-10 re-review §3, row 1): a markdown ordered-list marker such as `1.` or
# `2.` is `.` + whitespace, which `_SENTENCE_BOUNDARY_RE` happily splits on — handing the
# faithfulness judge a bare `"2."` as a "claim" it can never find support for, sinking an
# otherwise-flawless answer. A fragment with no letter in it carries no claim, so it is dropped
# post-split rather than judged.
_HAS_ALPHA_RE = re.compile(r"[A-Za-z]")


def split_sentences(text: str) -> list[str]:
    """Split `text` into sentences on `.`/`!`/`?` followed by whitespace.

    Moved verbatim from `groundedness._split_sentences` (same regex, same docstring rationale) —
    `context_recall` below needs the identical splitter to turn a reference answer into claims,
    and the per-sentence faithfulness judge in `groundedness.py` now calls this copy instead of
    keeping a private one.

    Task-05b: a fragment with no alphabetic character (e.g. an ordinal list marker `1.` / `(b)` /
    `2)`) is never returned as a sentence — it is dropped, since the marker itself carries no
    claim for the judge to score (task-10 re-review §3, row 1). Sentences that merely START with a
    marker (`"Step 1. Sell."` splits to `["Step 1.", "Sell."]`) keep it — only markers that split
    off into their OWN fragment are affected.
    """
    stripped = text.strip()
    if not stripped:
        return []
    return [
        sentence
        for sentence in _SENTENCE_BOUNDARY_RE.split(stripped)
        if sentence and _HAS_ALPHA_RE.search(sentence)
    ]


# Task-05b (task-10 re-review §3, row 2): the answerer numbers `[n]` markers by content
# first-use order (`app.rag.synthesis._format_sources`, deliberately, 1:1 with the wire
# `citations` array), while `OpenAIJudge.is_supported` numbers its deduped CHUNK list 1..N —
# the two numbering spaces disagree whenever two retrieved chunks share a `content_id`. A
# correctly-cited sentence then gets rejected because the judge's `[2]` names a different chunk
# than the answerer's `[2]`. Faithfulness is "claim supported by the union of retrieved chunks",
# so the bracket number must never be part of the claim text the judge sees.
_CITATION_MARKER_RE = re.compile(r"\s*\[\d+\]")


def strip_citation_markers(text: str) -> str:
    """Remove `[n]` citation markers (one or more digits) and the whitespace immediately before
    them: `"Costs $2,500 [2]."` -> `"Costs $2,500."`; `"See [1][3] here."` -> `"See here."`.
    Everything else is untouched. Idempotent.
    """
    return _CITATION_MARKER_RE.sub("", text)


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    """The union of `items`, deduped, in first-occurrence order (`dict.fromkeys` trick).

    A small, deliberate duplicate of `groundedness._dedupe_preserve_order` (same trick, different
    job: that one dedupes chunk TEXTS for the judge seam; this one dedupes retrieved id/slug
    SEQUENCES for `retrieval_metrics` below) — keeping this module import-free of `groundedness`
    (module docstring) is worth the few duplicated lines.
    """
    return list(dict.fromkeys(items))


class GroundednessJudge(Protocol):
    """The judge seam `run_eval` scores each answer sentence through (task-02 brief Interfaces).

    Structurally implemented by `OpenAIJudge` (the real judge, `app/eval/groundedness.py`) and by
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


class MetricsJudge(Protocol):
    """The rubric judges (DESIGN "Generation" row). `is_supported` is the existing faithfulness
    judge, restated here so one object can satisfy the whole seam.

    Fix round 1 (Opus review, Cost ruling): `rank_chunk_relevance` batches what used to be one
    `is_chunk_relevant` call per retrieved chunk into ONE call over all of them, returning one
    verdict per chunk — this is what `app.eval.groundedness._evaluate_question` actually calls.
    `is_chunk_relevant` itself is KEPT (not removed) because `context_precision` below still calls
    it once per chunk (both paths feed the SAME `ragas_context_precision` formula; only the call
    count differs).

    Fix round 2 (Opus re-review, N1): `rank_chunk_relevance`'s return type widens to
    `list[bool] | None` — `None` means the judge's reply was unparsable even after fence-
    stripping (`app.eval.groundedness.OpenAIJudge._parse_chunk_relevance`), so the caller records
    "not applicable" (`EvalRow.metrics["context_precision"] = None`, `"judge_reply_malformed":
    True`) instead of a fabricated `0.0`.
    """

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...
    def is_answer_relevant(self, question: str, answer_text: str) -> bool: ...
    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool: ...
    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...
    def rank_chunk_relevance(
        self, question: str, chunk_texts: Sequence[str]
    ) -> list[bool] | None: ...


@dataclass(frozen=True)
class RetrievalMetrics:
    """Standard IR metrics for one question's retrieval (DESIGN "Retrieval" row)."""

    mode: str  # "chunk" when expected_chunks resolved, else "slug"
    recall_at_k: float | None  # None when the question has no expected items (off-domain)
    precision_at_k: float | None
    mrr: float | None
    hits: int  # |expected ∩ retrieved| — task 06's `expected_chunk_hits`


def retrieval_metrics(
    expected: Sequence[str], retrieved: Sequence[str], *, mode: str
) -> RetrievalMetrics:
    """recall@k / precision@k / MRR over two ordered id (or slug) sequences.

    - `recall_at_k`  = |E ∩ R| / |E|
    - `precision_at_k` = |E ∩ R| / |R|, and `0.0` when `R` is empty (a refusal retrieves nothing,
      which is zero precision, not undefined). Fix round 1 (Opus review, I2): with |E|=1 (today's
      authored `expected_chunks` refs are single headings), `precision_at_k` is mathematically
      capped at `1/|R|` regardless of retrieval quality — this is why the caller
      (`groundedness._evaluate_question`) keeps it in `EvalRow.metrics` but the printed rollup
      does not treat it as a headline retrieval number alongside recall@k/MRR.
    - `mrr` = 1 / (1-based position of the first element of `R` that is in `E`), else `0.0`.
      Note: deduping `R` (below) shifts these ranks — `[a, a, b]` against `E={b}` scores rank 2
      (`R` dedupes to `[a, b]`), not rank 3.
    - `E` empty (an off-domain question) ⇒ every metric is `None` and `hits` is `0`: there is
      nothing to recall, and scoring it 0.0 would drag the corpus-wide means down for questions
      that are *supposed* to retrieve nothing.

    `R` is deduped preserving order before scoring (a content item with two retrieved chunks must
    not inflate precision's denominator twice at slug level, and shifts MRR's ranks the same way).
    """
    if not expected:
        return RetrievalMetrics(mode=mode, recall_at_k=None, precision_at_k=None, mrr=None, hits=0)

    expected_set = set(expected)
    deduped_retrieved = _dedupe_preserve_order(retrieved)
    hits = len(expected_set & set(deduped_retrieved))

    recall_at_k = hits / len(expected_set)
    precision_at_k = hits / len(deduped_retrieved) if deduped_retrieved else 0.0

    mrr = 0.0
    for position, item in enumerate(deduped_retrieved, start=1):
        if item in expected_set:
            mrr = 1.0 / position
            break

    return RetrievalMetrics(
        mode=mode,
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        mrr=mrr,
        hits=hits,
    )


def context_precision(
    judge: MetricsJudge, question: str, chunk_texts: Sequence[str]
) -> float | None:
    """RAGAS-style, rank-aware context precision (round 1b, controller amendment to fix round 1
    I3): judges each of `chunk_texts` individually via `judge.is_chunk_relevant` (one call per
    chunk, in retrieval order) and delegates the resulting verdicts to `ragas_context_precision`
    (below) for the actual formula. `None` if nothing was retrieved (`chunk_texts` empty).

    This is a one-call-per-chunk convenience wrapper around the same formula
    `app.eval.groundedness._evaluate_question` scores from a SINGLE batched
    `MetricsJudge.rank_chunk_relevance` call (the Cost ruling) — both paths score identically for
    the same relevance verdicts; only the number of judge calls differs.
    """
    if not chunk_texts:
        return None
    relevant = [judge.is_chunk_relevant(question, text) for text in chunk_texts]
    return ragas_context_precision(relevant)


def ragas_context_precision(relevant: Sequence[bool]) -> float | None:
    """RAGAS-style, rank-aware context precision: `Σ_i precision@i · rel_i / |relevant chunks|`,
    where `relevant[i]` is one relevance verdict per RETRIEVED chunk (0-based, in retrieval
    order) and `precision@i` is the fraction of relevant chunks among the first `i + 1` retrieved.
    This is the formula BOTH `context_precision` (above, one `is_chunk_relevant` call per chunk)
    and `app.eval.groundedness._evaluate_question` (via the batched `MetricsJudge.
    rank_chunk_relevance` call, the Cost ruling) use to score `EvalRow.metrics["context_
    precision"]` — there is exactly one "context precision" metric as of round 1b, not two.

    `None` when nothing was retrieved (`relevant` empty — no signal to score). `0.0` when chunks
    WERE retrieved but the judge found none of them relevant (an explicit floor, not a
    `ZeroDivisionError` from an empty "relevant chunks" denominator).
    """
    if not relevant:
        return None
    num_relevant = sum(1 for is_relevant in relevant if is_relevant)
    if num_relevant == 0:
        return 0.0

    running_relevant = 0
    total = 0.0
    for position, is_relevant in enumerate(relevant, start=1):
        if is_relevant:
            running_relevant += 1
            total += running_relevant / position
    return total / num_relevant


def context_recall(
    judge: MetricsJudge, reference_answer: str | None, chunk_texts: Sequence[str]
) -> float | None:
    """Fraction of the reference answer's sentences the judge deems covered by the retrieved
    context. `None` when there is no reference answer (or it splits to zero sentences); `0.0` when
    a reference answer exists but nothing was retrieved.
    """
    if reference_answer is None:
        return None
    claims = split_sentences(reference_answer)
    if not claims:
        return None
    if not chunk_texts:
        return 0.0
    covered = sum(1 for claim in claims if judge.is_claim_covered(claim, chunk_texts))
    return covered / len(claims)
