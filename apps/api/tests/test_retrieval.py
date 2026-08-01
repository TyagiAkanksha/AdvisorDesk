"""Failing (RED) tests for retrieval + the similarity conversion (phase-4 task-01).

Task brief: docs/plans/phase-4-rag-assistant/task-01-retrieval.md, Steps 1-2.
Spec: advisordesk-prd.md §7.3 ("Similarity convention (implementation trap...)": pgvector's
`<=>` operator returns cosine DISTANCE, not similarity — `similarity = 1 - distance` must be
defined exactly once), §7.4 (retrieval-outcome recording semantics: `top_similarity` is the
best similarity *observed*, even when every candidate is below threshold; `None` only when the
index itself returned nothing), §9 (the similarity-conversion pin test is an explicit minimum).

`app.rag.retrieval` does not exist yet: every test here is expected to fail at collection
(`ModuleNotFoundError`) until the implementer (a separate agent) creates it — that failure IS
the RED evidence this file exists to produce.

Fake embedder: this file defines its own `RecordingFakeEmbedder` rather than importing
`test_lifecycle.py`'s `FakeEmbedder` (CONVENTIONS.md §10: unique test-file basenames, no
cross-file test imports — `test_lifecycle.py` was read-only reference material per the
test-author brief). Unlike that file's hash-seeded fake (useful there because publish-time
tests never need to know a chunk's *exact* vector), this fake returns one pre-configured
vector regardless of the input text, because these tests need the query embedding pinned to an
exact, known value so pgvector's `<=>` cosine distance against hand-built `Chunk.embedding`
rows is computable by hand, not just "probably distinct." It also records every call's
`(texts, input_type)` pair — the v1.5 asymmetric-model pin (`retrieve()` must call
`embed_texts([query], input_type="query")`, never the `"passage"` default) is asserted against
`.calls`.

Vector construction: `app/rag/embeddings.py`'s `Embedder` protocol and `Chunk.embedding`
(migration 0002 / `app/models/chunks.py`) are both 1024-dim (`nvidia/nv-embedqa-e5-v5`, PRD
§7.2 v1.5). Every hand-built vector here is `[cos_theta, sin_theta, 0.0, ..., 0.0]` (1024 dims,
zero-padded) — a unit vector at angle `theta` from the fixed query vector `QUERY_VECTOR = [1.0,
0.0, ..., 0.0]` (also unit-length). Since both vectors are unit-norm by construction, cosine
similarity is exactly their dot product, which is exactly `cos_theta` — so `_vector_at_cosine`
lets every test state its expected similarity as a literal float instead of computing it.
pgvector stores `real` (float4) components, so DB-round-tripped similarities are compared with
`pytest.approx(..., abs=1e-3)` rather than exact equality throughout.

Seeding style: content/chunk rows are inserted via direct ORM field setup (`Content(status=...,
published_at=...)` / `Chunk(embedding=...)`, matching `test_public_content.py`'s
`_seed_visibility_matrix` in spirit) rather than by driving the real publish pipeline —
`content_service.publish_content` would chunk+embed real body text through a real (fake)
`Embedder`, giving no way to pin an exact embedding vector per chunk. This also lets the
archived/deleted-content exclusion tests set up a chunk row pointing at non-eligible content
directly (defense-in-depth belt-and-braces: in real operation `archive_content`/
`delete_content` already remove chunk rows per PRD §4, so this state should never occur —
these tests prove `retrieve()`'s own join does not *rely* on that invariant holding).

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL`
is set, and are skipped by fixture name otherwise (see
`tests/conftest.py::pytest_collection_modifyitems`).
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import pytest
from sqlalchemy.orm import Session

from app.models import Content
from app.models.chunks import Chunk
from app.rag.retrieval import RetrievalResult, RetrievedChunk, retrieve, similarity_from_distance

# `nvidia/nv-embedqa-e5-v5` (PRD §7.2 v1.5) — matches `Chunk.embedding`'s `Vector(1024)` column
# (app/models/chunks.py) and `Settings.embedding_dimensions`'s default.
_DIMS = 1024


def _vector_at_cosine(cos_theta: float, *, dims: int = _DIMS) -> list[float]:
    """A unit vector whose cosine similarity to `QUERY_VECTOR` is exactly `cos_theta`.

    `[cos_theta, sin_theta, 0.0, ..., 0.0]` has norm 1 for any `cos_theta` in `[-1, 1]`
    (`cos_theta**2 + sin_theta**2 == 1`), so its dot product with the unit vector
    `QUERY_VECTOR = [1.0, 0.0, ..., 0.0]` — and therefore its cosine similarity, since
    cosine similarity of two unit vectors is just their dot product — is `cos_theta`
    itself. The remaining `dims - 2` components are zero padding (task brief: "1024
    dims — pad with zeros").
    """
    sin_theta = math.sqrt(1.0 - cos_theta * cos_theta)
    return [cos_theta, sin_theta] + [0.0] * (dims - 2)


QUERY_VECTOR = _vector_at_cosine(1.0)  # == [1.0, 0.0, ..., 0.0]


def _approx(value: float) -> object:
    """`pytest.approx` with an explicit absolute tolerance for DB-round-tripped similarities.

    `Chunk.embedding` stores `real` (float4, ~7 significant decimal digits) components
    (module docstring) — `pytest.approx`'s bare default (`rel=1e-6`, effectively ~9e-7 of
    absolute slack for values around 0.9) sits close enough to that float4 rounding floor
    that an unlucky `cos_theta`/`sin_theta` pair could flake. `abs=1e-3` is generously
    looser than the actual expected error (~1e-6-1e-7) while still easily distinguishing
    every pair of similarity values these tests construct (all >= 0.1 apart).
    """
    return pytest.approx(value, abs=1e-3)


@dataclass
class RecordingFakeEmbedder:
    """`Embedder`-shaped fake (structural match to `app.rag.embeddings.Embedder`) that always
    returns `vector` and records every call's `(texts, input_type)` pair.

    Defined locally per the test-author brief (do not import `test_lifecycle.py`'s fake across
    test files). Returning a fixed, caller-chosen vector rather than a hash of the input text
    (contrast `test_lifecycle.py::FakeEmbedder`) is the point: these tests need to know the
    exact query vector in advance to hand-compute cosine distances against hand-built chunk
    vectors.
    """

    vector: list[float]
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [self.vector for _ in texts]


def _add_content(
    session: Session,
    *,
    slug: str,
    status: str = "published",
    is_deleted: bool = False,
) -> Content:
    """Insert and flush a `Content` row via direct field setup (no publish pipeline — see
    module docstring). `published_at` is always stamped so it never spuriously participates
    in a NULL-related edge case; `status`/`is_deleted` are the only visibility knobs tests vary.
    """
    content = Content(
        title=f"Title for {slug}",
        slug=slug,
        body_md="body text, irrelevant to retrieval — chunks carry the retrievable text",
        status=status,
        is_deleted=is_deleted,
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    return content


def _add_chunk(
    session: Session, content_id: uuid.UUID, *, chunk_index: int, text: str, cos_theta: float
) -> Chunk:
    """Insert and flush a `Chunk` row whose embedding has cosine similarity `cos_theta` to
    `QUERY_VECTOR` (see `_vector_at_cosine`).
    """
    chunk = Chunk(
        content_id=content_id,
        chunk_index=chunk_index,
        text=text,
        embedding=_vector_at_cosine(cos_theta),
    )
    session.add(chunk)
    session.flush()
    return chunk


# ---------------------------------------------------------------------------
# Step 1: the pure similarity-conversion pin (no DB) — PRD §7.3 / §9.
# ---------------------------------------------------------------------------


def test_similarity_conversion_pin() -> None:
    """PRD §7.3: pgvector's `<=>` is cosine DISTANCE; similarity = 1 - distance.

    identical vectors: distance 0.0 -> similarity 1.0
    orthogonal vectors: distance 1.0 -> similarity 0.0

    This is the exact test the brief specifies verbatim (Step 1) — the §9-mandated pin
    against the "implementation trap" of applying `SIMILARITY_THRESHOLD` to a raw
    distance value instead of `1 - distance`.
    """
    assert similarity_from_distance(0.0) == 1.0
    assert similarity_from_distance(1.0) == 0.0


# ---------------------------------------------------------------------------
# Step 2: DB-fixture integration tests.
# ---------------------------------------------------------------------------


def test_retrieve_orders_chunks_by_similarity_descending(db_session: Session) -> None:
    """Three published chunks with distinct, known similarities to the query, all clearing a
    low threshold, come back ordered highest-similarity-first — `retrieve()`'s primary
    contract (PRD §7.3: "nearest neighbors ... top 6").

    Also pins the join's field mapping onto `RetrievedChunk` (`title`/`slug`/`text` sourced
    from the right `content`/`chunk` row, not just the similarity ordering).
    """
    high = _add_content(db_session, slug="ordering-high")
    mid = _add_content(db_session, slug="ordering-mid")
    low = _add_content(db_session, slug="ordering-low")
    _add_chunk(db_session, high.id, chunk_index=0, text="high similarity chunk", cos_theta=0.9)
    _add_chunk(db_session, mid.id, chunk_index=0, text="mid similarity chunk", cos_theta=0.6)
    _add_chunk(db_session, low.id, chunk_index=0, text="low similarity chunk", cos_theta=0.3)
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    result = retrieve(db_session, embedder, "what has the highest similarity?", k=3, threshold=0.1)

    assert isinstance(result, RetrievalResult)
    assert [c.similarity for c in result.chunks] == [
        _approx(0.9),
        _approx(0.6),
        _approx(0.3),
    ]
    assert [c.content_id for c in result.chunks] == [high.id, mid.id, low.id]
    assert result.top_similarity == _approx(0.9)

    top = result.chunks[0]
    assert isinstance(top, RetrievedChunk)
    assert top.title == "Title for ordering-high"
    assert top.slug == "ordering-high"
    assert top.text == "high similarity chunk"


def test_retrieve_drops_chunks_below_threshold_keeping_only_qualifying_chunks(
    db_session: Session,
) -> None:
    """A mix of above- and below-threshold chunks: only the qualifying ones are returned, in
    descending order, and the ones below `threshold` never appear (PRD §7.3: "threshold
    filter").
    """
    above_a = _add_content(db_session, slug="mixed-above-a")
    above_b = _add_content(db_session, slug="mixed-above-b")
    below_a = _add_content(db_session, slug="mixed-below-a")
    below_b = _add_content(db_session, slug="mixed-below-b")
    _add_chunk(db_session, above_a.id, chunk_index=0, text="above a", cos_theta=0.8)
    _add_chunk(db_session, above_b.id, chunk_index=0, text="above b", cos_theta=0.6)
    _add_chunk(db_session, below_a.id, chunk_index=0, text="below a", cos_theta=0.3)
    _add_chunk(db_session, below_b.id, chunk_index=0, text="below b", cos_theta=0.1)
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    result = retrieve(db_session, embedder, "threshold mix", k=6, threshold=0.5)

    assert [c.content_id for c in result.chunks] == [above_a.id, above_b.id]
    assert [c.similarity for c in result.chunks] == [_approx(0.8), _approx(0.6)]


def test_retrieve_top_similarity_reports_best_raw_value_even_when_all_chunks_are_below_threshold(
    db_session: Session,
) -> None:
    """PRD §7.4, the sharp edge of the "implementation trap": when EVERY candidate is below
    `threshold`, `chunks` is empty but `top_similarity` is still the best similarity actually
    observed — not `None`. A naive implementation that derives `top_similarity` from
    `max(chunks)` (instead of from the full candidate set before filtering) would wrongly
    return `None` here, indistinguishable from the genuinely-empty-index case
    (`test_retrieve_returns_none_top_similarity_only_when_index_is_empty` below) — which is
    exactly the distinction this test exists to pin.
    """
    better = _add_content(db_session, slug="all-below-better")
    worse = _add_content(db_session, slug="all-below-worse")
    _add_chunk(db_session, better.id, chunk_index=0, text="less bad", cos_theta=0.4)
    _add_chunk(db_session, worse.id, chunk_index=0, text="more bad", cos_theta=0.2)
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    result = retrieve(db_session, embedder, "nothing qualifies", k=6, threshold=0.5)

    assert result.chunks == []
    assert result.top_similarity is not None
    assert result.top_similarity == _approx(0.4)


def test_retrieve_returns_none_top_similarity_only_when_index_is_empty(
    db_session: Session,
) -> None:
    """PRD §7.4: `top_similarity` is `None` iff the index returned nothing at all — no
    `Content`/`Chunk` rows exist anywhere, as distinct from "candidates existed but none
    cleared the threshold" (the previous test, where `top_similarity` stays non-`None`).
    """
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    result = retrieve(db_session, embedder, "empty index", k=6, threshold=0.35)

    assert result == RetrievalResult(chunks=[], top_similarity=None)


def test_retrieve_excludes_chunks_whose_content_is_archived_or_soft_deleted_via_the_join(
    db_session: Session,
) -> None:
    """Belt-and-braces (brief Interfaces block: "joins chunks -> content (published,
    non-deleted)"): a chunk row belonging to archived content, and one belonging to
    soft-deleted-but-still-`published`-status content, are both excluded by `retrieve()`'s own
    join — even when each would otherwise be the single best (perfect, `cos_theta=1.0`) match.
    This proves the exclusion is enforced by the retrieval query itself, not merely inherited
    from the lifecycle invariant that archive/delete already remove chunk rows (PRD §4) — in
    real operation this exact row shape (an archived/deleted content row that still owns a
    chunk) should never occur; these rows are inserted directly to test the defense-in-depth
    guard regardless.
    """
    eligible = _add_content(db_session, slug="join-eligible", status="published")
    archived = _add_content(db_session, slug="join-archived", status="archived")
    deleted = _add_content(db_session, slug="join-deleted", status="published", is_deleted=True)
    _add_chunk(db_session, eligible.id, chunk_index=0, text="eligible chunk", cos_theta=0.5)
    _add_chunk(db_session, archived.id, chunk_index=0, text="archived chunk", cos_theta=1.0)
    _add_chunk(db_session, deleted.id, chunk_index=0, text="deleted chunk", cos_theta=1.0)
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    result = retrieve(db_session, embedder, "join filter", k=6, threshold=0.1)

    assert [c.content_id for c in result.chunks] == [eligible.id]
    assert result.top_similarity == _approx(0.5)


def test_retrieve_k_defaults_to_six(db_session: Session) -> None:
    """`retrieve()` called without `k` returns at most 6 chunks — the top 6 by similarity —
    even when more than 6 published chunks qualify (PRD §7.3: "top 6").
    """
    cosines = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]  # 7 candidates, all above the threshold below
    contents = [_add_content(db_session, slug=f"k-default-{i}") for i in range(len(cosines))]
    for content, cos_theta in zip(contents, cosines, strict=True):
        _add_chunk(
            db_session, content.id, chunk_index=0, text=f"chunk at {cos_theta}", cos_theta=cos_theta
        )
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    result = retrieve(db_session, embedder, "k default", threshold=0.1)  # no k= passed

    assert len(result.chunks) == 6
    assert [c.similarity for c in result.chunks] == [_approx(c) for c in cosines[:6]]
    assert result.top_similarity == _approx(0.9)


def test_retrieve_embeds_the_query_with_input_type_query(db_session: Session) -> None:
    """v1.5 asymmetric-model pin (`app/rag/embeddings.py` module docstring; brief Context
    block): `retrieve()` MUST call `embedder.embed_texts([query], input_type="query")` — never
    the `"passage"` default, which is publish-time only. `RecordingFakeEmbedder` records every
    call's `(texts, input_type)` pair regardless of what vector it returns.
    """
    content = _add_content(db_session, slug="input-type-pin")
    _add_chunk(db_session, content.id, chunk_index=0, text="irrelevant to this pin", cos_theta=0.5)
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    retrieve(db_session, embedder, "what is a Roth IRA conversion?", k=6, threshold=0.1)

    assert embedder.calls == [(("what is a Roth IRA conversion?",), "query")]
