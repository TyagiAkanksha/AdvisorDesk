"""Retrieval: embed the user's question, nearest-neighbor search `chunks`, filter (PRD §7.3, §7.4).

`retrieve()` is phase-4 task-02 (chat)'s only consumer. It embeds `query` with the
`Embedder` seam (`app/rag/embeddings.py`), nearest-neighbor searches `chunks` by
cosine distance — which Postgres' planner can serve directly from the HNSW index
(`ix_chunks_embedding_hnsw`, `app/models/chunks.py`) when the published/non-deleted
filter is unselective, falling back to an exact filtered scan otherwise; the index
path is approximate and applies the content filter after the ANN scan, so on a
large corpus with a selective filter it can return fewer than `k` rows than the
exact plan would (ledgered review finding M2 — reachable in production, not just
theoretically) — converts distance to similarity exactly once
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

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Content
from app.rag.embeddings import Embedder
from app.services.queries import active_select


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
    is empty but `top_similarity` is not) — and is `None` only when no real
    (non-NaN) candidate exists at all: either the index returned no rows
    (no published, non-deleted chunk exists), or every returned candidate's
    distance was NaN (a degenerate all-zero query/stored vector — dropped
    before scoring, review round 1 finding M5, so it never surfaces as a
    `nan` "similarity"). Both cases are the one situation genuinely
    indistinguishable from "no guidance exists" rather than "guidance
    exists but isn't close enough."
    """

    chunks: list[RetrievedChunk]
    top_similarity: float | None


def similarity_from_distance(distance: float) -> float:
    """Convert a pgvector cosine `<=>` distance to a cosine similarity (PRD §7.3).

    pgvector's `<=>` operator returns cosine **distance**: `0.0` for
    identical (unit) vectors, `1.0` for orthogonal ones. Similarity is
    `1.0 - distance`. This is THE ONE PLACE in `app/` this conversion is
    written — `retrieve()` calls it once per (NaN-filtered) candidate;
    nothing else may duplicate it (task brief's grep gate;
    `tests/test_retrieval.py::test_similarity_conversion_pin`).

    Args:
        distance: a raw, finite cosine distance from pgvector's `<=>`
            operator, in `[0.0, 2.0]` for unit vectors (`[0.0, 1.0]` for
            the non-negative-similarity range this app's embeddings live
            in). Callers must not pass NaN (`retrieve()` filters NaN
            candidates out before calling this).

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
    `chunks` to the §4.1 active-row view of `content`
    (`app.services.queries.active_select` — CONVENTIONS.md §3: the
    define-once soft-delete filter; review round 1, finding I1 — an ad-hoc
    `is_deleted` check here would be a review-blocking defect), further
    restricted to `status='published'`, ordered by pgvector's
    `embedding <=> :qvec` raw distance ascending (nearest first) and capped
    at `k` rows. Only the columns `RetrievedChunk` needs are selected — no
    `Chunk`/`Content` ORM entity is ever hydrated, so a candidate's full
    1024-float `embedding` never leaves the database and `Chunk`'s `"load"`
    normalization listener never fires on this path (review round 1,
    finding M3: ~37% of this query's own latency was spent hydrating data
    nothing here uses). Distance is converted to similarity via
    `similarity_from_distance` exactly once per candidate; `threshold` is
    applied to that similarity, never to the raw distance (the §7.3
    implementation trap this module exists to avoid).

    A candidate whose raw distance is NaN (a degenerate all-zero query or
    stored vector makes `<=>`'s cosine-distance division undefined) is
    dropped before either the similarity conversion or `top_similarity` is
    computed (review round 1, finding M5) — so a NaN candidate never
    surfaces as a `nan` "similarity" in `chunks` or `top_similarity`; if
    every returned row is NaN (or none were returned at all), this
    degrades to the same `RetrievalResult(chunks=[], top_similarity=None)`
    as a genuinely empty index.

    `top_similarity` is derived from the same `k`-row, NaN-filtered
    candidate set (its best/first element after the distance-ascending
    sort), before the threshold filter is applied — so it reports the best
    similarity PRD §7.4 says to record even when nothing clears
    `threshold` (see `RetrievalResult`'s docstring for the full
    None-iff-empty-index semantics). `threshold` is inclusive
    (`similarity >= threshold`, review round 1 finding M4): PRD §7.3 says
    chunks *below* threshold are dropped, so a chunk sitting exactly at
    `threshold` is kept.

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

    # CONVENTIONS.md §3 / PRD §4.1: the define-once active-row filter —
    # never an ad-hoc `Content.is_deleted == False` here (review round 1,
    # finding I1). `active_select` returns the full `Content` select;
    # `.subquery()` + the `status="published"` filter mirrors
    # `app/services/content.py::list_content`'s tag-join precedent.
    active_content = active_select(Content).where(Content.status == "published").subquery()

    # PRD §7.3: `<=>` is cosine DISTANCE (ascending = nearest/most-similar
    # first), NOT similarity — do not compare or threshold against this
    # column directly. It is converted via `similarity_from_distance`,
    # exactly once, below.
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    # Columns-only select (review round 1, finding M3): no `Chunk`/`Content`
    # ORM entity is constructed, so neither entity's full column set
    # (notably `Chunk.embedding`, 1024 floats, and `Content.body_md`) is
    # hydrated for data `RetrievedChunk` never uses.
    #
    # Every column is explicitly `.label()`ed (review round 1, finding N2): `Chunk.id` and
    # `active_content.c.id` both default to the bare column name `id`, so without a label
    # they'd be indistinguishable by name. Labelling enables the named row access below
    # (`row.chunk_id`, `row.content_id`, ...), which closes the transposition hazard the old
    # positional-tuple unpacking had — `title`/`slug` are adjacent, same-typed (`str`) columns
    # that would compile, lint, and type-check clean even swapped.
    rows = session.execute(
        select(
            Chunk.id.label("chunk_id"),
            active_content.c.id.label("content_id"),
            active_content.c.title.label("title"),
            active_content.c.slug.label("slug"),
            Chunk.text.label("text"),
            distance,
        )
        .join(active_content, active_content.c.id == Chunk.content_id)
        .where(Chunk.embedding.is_not(None))
        .order_by(distance.asc())
        .limit(k)
    ).all()

    # Review round 1, finding M5: drop NaN-distance candidates (a
    # degenerate all-zero query/stored vector) before either the similarity
    # conversion or `top_similarity` computation — a NaN candidate must
    # never leak into either. Named row access (review round 1, finding N2)
    # replaces the previous positional 6-tuple unpacking done three
    # separate times plus the bare `scored[0][5]` index.
    scored = [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            content_id=row.content_id,
            title=row.title,
            slug=row.slug,
            text=row.text,
            similarity=similarity_from_distance(row.distance),
        )
        for row in rows
        if not math.isnan(row.distance)
    ]

    if not scored:
        return RetrievalResult(chunks=[], top_similarity=None)

    top_similarity = scored[0].similarity
    chunks = [chunk for chunk in scored if chunk.similarity >= threshold]

    return RetrievalResult(chunks=chunks, top_similarity=top_similarity)
