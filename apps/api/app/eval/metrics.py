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


def split_sentences(text: str) -> list[str]:
    """Split `text` into sentences on `.`/`!`/`?` followed by whitespace.

    Moved verbatim from `groundedness._split_sentences` (same regex, same docstring rationale) —
    `context_recall` below needs the identical splitter to turn a reference answer into claims,
    and the per-sentence faithfulness judge in `groundedness.py` now calls this copy instead of
    keeping a private one.
    """
    stripped = text.strip()
    if not stripped:
        return []
    return [sentence for sentence in _SENTENCE_BOUNDARY_RE.split(stripped) if sentence]


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
    verdict per chunk. `is_chunk_relevant` itself is KEPT (not removed) only because `context_
    precision` below (the OLD, non-rank-aware formula) still calls it — see that function's
    docstring for why it survives unused by the real per-row computation.
    """

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...
    def is_answer_relevant(self, question: str, answer_text: str) -> bool: ...
    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool: ...
    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...
    def rank_chunk_relevance(self, question: str, chunk_texts: Sequence[str]) -> list[bool]: ...


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
    """Fraction of RETRIEVED chunks the judge deems relevant to `question`. `None` if none were
    retrieved.

    Fix round 1 (Opus review, I3): this plain, non-rank-aware fraction is NOT the metric recorded
    under `EvalRow.metrics["context_precision"]` as of this fix round — `ragas_context_precision`
    (below) is, per the controller's ruling to use the RAGAS rank-aware formula. This function is
    kept, byte-for-byte, ONLY because `tests/test_eval_metrics.py::
    test_context_precision_is_the_fraction_of_relevant_retrieved_chunks` pins its exact
    non-rank-aware value (`2/3`) for a mixed-relevance fixture that the rank-aware formula scores
    differently (`5/6` for the equivalent `[True, False, True]` pattern) — an authored test may
    not be modified without controller approval, and this is flagged explicitly as such in the
    fix-round-1 implementer report rather than silently reconciled.
    """
    if not chunk_texts:
        return None
    relevant = sum(1 for text in chunk_texts if judge.is_chunk_relevant(question, text))
    return relevant / len(chunk_texts)


def ragas_context_precision(relevant: Sequence[bool]) -> float | None:
    """RAGAS-style, rank-aware context precision (fix round 1, Opus review I3):
    `Σ_i precision@i · rel_i / |relevant chunks|`, where `relevant[i]` is one relevance verdict
    per RETRIEVED chunk (0-based, in retrieval order — from `MetricsJudge.rank_chunk_relevance`,
    the batched call the Cost ruling asks for) and `precision@i` is the fraction of relevant
    chunks among the first `i + 1` retrieved. This IS the metric recorded under
    `EvalRow.metrics["context_precision"]` as of this fix round (see `context_precision` above
    for the older, non-rank-aware fraction this module still exposes for an authored test's own
    pin — the two deliberately disagree on a mixed-relevance input).

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
