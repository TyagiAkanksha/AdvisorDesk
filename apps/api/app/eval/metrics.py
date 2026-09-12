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
    """The four rubric judges (DESIGN "Generation" row). `is_supported` is the existing
    faithfulness judge, restated here so one object can satisfy the whole seam.
    """

    def is_supported(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...
    def is_answer_relevant(self, question: str, answer_text: str) -> bool: ...
    def is_chunk_relevant(self, question: str, chunk_text: str) -> bool: ...
    def is_claim_covered(self, claim_text: str, chunk_texts: Sequence[str]) -> bool: ...


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
      which is zero precision, not undefined)
    - `mrr` = 1 / (1-based position of the first element of `R` that is in `E`), else `0.0`
    - `E` empty (an off-domain question) ⇒ every metric is `None` and `hits` is `0`: there is
      nothing to recall, and scoring it 0.0 would drag the corpus-wide means down for questions
      that are *supposed* to retrieve nothing.

    `R` is deduped preserving order before scoring (a content item with two retrieved chunks must
    not inflate precision's denominator twice at slug level).
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
    """
    if not chunk_texts:
        return None
    relevant = sum(1 for text in chunk_texts if judge.is_chunk_relevant(question, text))
    return relevant / len(chunk_texts)


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
