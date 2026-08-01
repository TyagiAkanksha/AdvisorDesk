"""Retrieval: embed the user's question, nearest-neighbor search `chunks`, filter (PRD §7.3, §7.4).

`retrieve()` is phase-4 task-02 (chat)'s only consumer. It embeds `query` with the
`Embedder` seam (`app/rag/embeddings.py`), runs pgvector's HNSW index
(`ix_chunks_embedding_hnsw`, `app/models/chunks.py`) to pull the `k` nearest chunks
by cosine distance, converts distance to similarity exactly once
(`similarity_from_distance`), and applies `threshold` to that similarity value —
never to the raw distance.

**Similarity convention (PRD §7.3, the implementation trap):** pgvector's `<=>`
operator returns cosine **distance**, not similarity — `0.0` means identical,
`1.0` means orthogonal. `similarity_from_distance` is THE ONE PLACE
`1.0 - distance` is computed anywhere in `app/` (pinned by
`tests/test_retrieval.py::test_similarity_conversion_pin` and the brief's grep
gate). Every other line in this module works in whichever space (distance
in SQL, similarity in Python) its variable name says it does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Content
from app.rag.embeddings import Embedder


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk returned by `retrieve()`, already joined to its parent content.

    `title`/`slug` come from `Content` (for citation display); `text` is the
    chunk's own retrievable slice of `body_md`; `similarity` is the
    already-converted `1.0 - distance` value (PRD §7.3).
    """

    chunk_id: uuid.UUID
    content_id: uuid.UUID
    title: str
    slug: str
    text: str
    similarity: float


@dataclass(frozen=True)
class RetrievalResult:
    """The outcome of one `retrieve()` call (PRD §7.4 recording semantics).

    `chunks` holds only the candidates that cleared `threshold`, ordered by
    similarity descending. `top_similarity` is the best similarity actually
    *observed* among the nearest-neighbor candidates the index returned —
    populated even when every candidate is below `threshold` (so `chunks`
    is empty but `top_similarity` is not) — and is `None` only when the
    index returned no candidates at all (no published, non-deleted chunk
    exists), which is the one case genuinely indistinguishable from "no
    guidance exists" rather than "guidance exists but isn't close enough."
    """

    chunks: list[RetrievedChunk]
    top_similarity: float | None


def similarity_from_distance(distance: float) -> float:
    """Convert a pgvector cosine `<=>` distance to a cosine similarity (PRD §7.3).

    pgvector's `<=>` operator returns cosine **distance**: `0.0` for
    identical (unit) vectors, `1.0` for orthogonal ones. Similarity is
    `1.0 - distance`. This is THE ONE PLACE in `app/` this conversion is
    written — `retrieve()` calls it once per candidate; nothing else may
    duplicate it (task brief's grep gate;
    `tests/test_retrieval.py::test_similarity_conversion_pin`).

    Args:
        distance: a raw cosine distance from pgvector's `<=>` operator,
            in `[0.0, 2.0]` for unit vectors (`[0.0, 1.0]` for the
            non-negative-similarity range this app's embeddings live in).

    Returns:
        The corresponding cosine similarity, `1.0 - distance`.
    """
    return 1.0 - distance


def retrieve(
    session: Session,
    embedder: Embedder,
    query: str,
    *,
    k: int = 6,
    threshold: float,
) -> RetrievalResult:
    """Embed `query` and return the top-`k` published chunks above `threshold` (PRD §7.3).

    Embeds `query` through `embedder` with `input_type="query"` — never the
    `"passage"` default, which is publish-time only (`app/rag/embeddings.py`
    module docstring: the model is asymmetric). Runs one query that joins
    `chunks` to `content`, restricted to `status='published'` and
    `is_deleted=False` (belt-and-braces on top of the PRD §4 lifecycle
    guarantee that archive/delete already remove a content item's chunk
    rows), ordered by pgvector's `embedding <=> :qvec` raw distance
    ascending (nearest first) and capped at `k` rows — the HNSW index
    (`ix_chunks_embedding_hnsw`) serves this ordering directly. Distance is
    converted to similarity via `similarity_from_distance` exactly once per
    candidate; `threshold` is applied to that similarity, never to the raw
    distance (the §7.3 implementation trap this module exists to avoid).

    `top_similarity` is derived from the same `k`-row candidate set
    (its best/first element after the distance-ascending sort), before the
    threshold filter is applied — so it reports the best similarity PRD §7.4
    says to record even when nothing clears `threshold` (see
    `RetrievalResult`'s docstring for the full None-iff-empty-index
    semantics).

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first).
        embedder: the `Embedder` seam `query` is embedded through.
        query: the user's question, embedded as-is (no rewriting).
        k: the maximum number of chunks to consider/return; PRD §7.3 "top
            6" — the caller (task-02) passes the runtime default from
            `Settings`, but this module never reads `Settings` itself.
        threshold: the minimum similarity a chunk must clear to appear in
            `chunks`; the caller passes `Settings.similarity_threshold`
            explicitly (this module never reads `Settings`).

    Returns:
        A `RetrievalResult` — see its docstring for the exact `chunks`/
        `top_similarity` semantics.
    """
    query_vector = embedder.embed_texts([query], input_type="query")[0]

    # PRD §7.3: `<=>` is cosine DISTANCE (ascending = nearest/most-similar
    # first), NOT similarity — do not compare or threshold against this
    # column directly. It is converted via `similarity_from_distance`,
    # exactly once, below.
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    candidates = session.execute(
        select(Chunk, Content, distance)
        .join(Content, Content.id == Chunk.content_id)
        .where(
            Content.status == "published",
            Content.is_deleted.is_(False),
            Chunk.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(k)
    ).all()

    if not candidates:
        return RetrievalResult(chunks=[], top_similarity=None)

    scored = [
        (chunk, content, similarity_from_distance(raw_distance))
        for chunk, content, raw_distance in candidates
    ]
    top_similarity = scored[0][2]

    chunks = [
        RetrievedChunk(
            chunk_id=chunk.id,
            content_id=content.id,
            title=content.title,
            slug=content.slug,
            text=chunk.text,
            similarity=similarity,
        )
        for chunk, content, similarity in scored
        if similarity >= threshold
    ]

    return RetrievalResult(chunks=chunks, top_similarity=top_similarity)
