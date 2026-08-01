"""Fix-round-1 guard tests for `app.rag.retrieval` (phase-4 task-01, review round 1).

New file, not an edit to the pinned `tests/test_retrieval.py` (sha256
`63100a90914c9f9842a6a3cfe0ce72ab9057c7c9daad084e930b8218ac728802` — untouched by
this file's addition; CONVENTIONS.md §10 unique-test-file-basename rule, no
cross-file test imports — `test_retrieval.py`'s own `RecordingFakeEmbedder`/
`_vector_at_cosine`/`_add_content`/`_add_chunk` are read-only reference material
here, reimplemented locally rather than imported).

Covers three findings from the round-1 review
(`.superpowers/sdd/reports/p4-t01-review.md`) that were pure test-coverage gaps —
no production-code semantic change was needed for any of the three (the
`>=` boundary, the `Chunk.embedding.is_not(None)` guard, and the requirement that
NaN never reach the similarity conversion were all already correct in the
implementer's original code; the round-1 fix only added the NaN-drop-before-
scoring step for M5):

- **M4**: the threshold boundary is inclusive (`similarity >= threshold`) — PRD
  §7.3 says chunks *below* threshold are dropped, so a chunk sitting exactly at
  threshold is kept. Mutation `M8_strict_gt_threshold` (`>` instead of `>=`)
  survived the whole pre-round-1 suite because no test placed a candidate
  exactly at the boundary.
- **M5**: a degenerate all-zero query vector makes pgvector's `<=>` cosine
  distance NaN (0/0 — review probe P6(b) confirmed this empirically against the
  installed pgvector 0.8.5). `retrieve()` must drop NaN candidates before any
  similarity/`top_similarity` computation (controller ruling, fix round 1) and
  degrade to `RetrievalResult([], None)`, the same as a genuinely empty index.
- **M6**: `Chunk.embedding` is nullable (`app/models/chunks.py`) — a
  NULL-embedding chunk row must be excluded by `retrieve()`'s own
  `is_not(None)` guard, not merely assumed never to occur (review probe P6(a2):
  without the guard, a NULL-embedding row's NULL distance can enter the top-`k`
  window and crash `similarity_from_distance(None)` with `TypeError`).
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models import Chunk, Content
from app.rag.retrieval import RetrievalResult, retrieve

# `nvidia/nv-embedqa-e5-v5` (PRD §7.2 v1.5) — matches `Chunk.embedding`'s `Vector(1024)`
# column (app/models/chunks.py).
_DIMS = 1024


def _vector_at_cosine(cos_theta: float, *, dims: int = _DIMS) -> list[float]:
    """A unit vector whose cosine similarity to `QUERY_VECTOR` is exactly `cos_theta`.

    Same construction as `test_retrieval.py::_vector_at_cosine` (reimplemented,
    not imported — CONVENTIONS.md §10 forbids cross-file test imports):
    `[cos_theta, sin_theta, 0.0, ..., 0.0]` has norm 1 for any `cos_theta` in
    `[-1, 1]`, so its dot product with the unit vector `QUERY_VECTOR = [1.0,
    0.0, ..., 0.0]` — and therefore its cosine similarity — is `cos_theta`
    itself.
    """
    sin_theta = math.sqrt(1.0 - cos_theta * cos_theta)
    return [cos_theta, sin_theta] + [0.0] * (dims - 2)


QUERY_VECTOR = _vector_at_cosine(1.0)  # == [1.0, 0.0, ..., 0.0]


@dataclass
class RecordingFakeEmbedder:
    """A minimal `Embedder`-shaped fake that always returns `vector`.

    Deliberately does not record calls (unlike `test_retrieval.py`'s own
    fake) — no test in this file asserts on `input_type`/call history, only
    on `retrieve()`'s return value; that pin already lives in the pinned file.
    """

    vector: list[float]

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        return [self.vector for _ in texts]


def _add_content(session: Session, *, slug: str) -> Content:
    """Insert and flush a published, non-deleted `Content` row."""
    content = Content(
        title=f"Title for {slug}",
        slug=slug,
        body_md="body text, irrelevant to retrieval — chunks carry the retrievable text",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(content)
    session.flush()
    return content


def _add_chunk(
    session: Session,
    content_id: uuid.UUID,
    *,
    chunk_index: int,
    text: str,
    cos_theta: float,
) -> Chunk:
    """Insert and flush a `Chunk` row whose embedding has cosine similarity `cos_theta`
    to `QUERY_VECTOR` (see `_vector_at_cosine`).
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


def test_retrieve_keeps_chunk_whose_similarity_exactly_equals_threshold(
    db_session: Session,
) -> None:
    """PRD §7.3: chunks *below* threshold are dropped — a chunk at EXACTLY threshold is
    kept (`similarity >= threshold`, not `>`; finding M4).

    Rather than predicting Postgres' float4-rounded cosine-similarity value in
    Python ahead of time (fragile — `<=>` is computed over float4-quantized
    vector components server-side, so a literal Python threshold chosen in
    advance is not guaranteed to bit-match the DB's result), this test
    observes the REAL similarity `retrieve()` computes for one chunk at a
    trivially-low threshold, then calls `retrieve()` again passing that exact
    observed float back as `threshold`. If the boundary check were `>` instead
    of `>=` (mutation `M8_strict_gt_threshold`, review round 1), `similarity >
    similarity` is always `False` and the chunk would vanish on the second
    call — this is precisely what that survived mutation would break.
    """
    content = _add_content(db_session, slug="boundary-chunk")
    _add_chunk(db_session, content.id, chunk_index=0, text="boundary chunk", cos_theta=0.6)
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    probe = retrieve(db_session, embedder, "boundary probe", k=1, threshold=0.0)
    assert len(probe.chunks) == 1
    observed_similarity = probe.chunks[0].similarity

    at_boundary = retrieve(
        db_session, embedder, "boundary probe", k=1, threshold=observed_similarity
    )

    assert len(at_boundary.chunks) == 1
    assert at_boundary.chunks[0].content_id == content.id
    assert at_boundary.chunks[0].similarity == observed_similarity


def test_retrieve_returns_none_top_similarity_when_every_candidate_distance_is_nan(
    db_session: Session,
) -> None:
    """Controller ruling, fix round 1 (finding M5): a degenerate all-zero query vector
    makes pgvector's `<=>` cosine distance NaN (0/0) against every stored chunk —
    `retrieve()` must drop NaN candidates before any similarity/`top_similarity`
    computation, never surface `top_similarity=nan`, and since nothing non-NaN
    remains, degrade to the exact same `RetrievalResult([], None)` as a
    genuinely empty index.
    """
    content = _add_content(db_session, slug="nan-guard")
    _add_chunk(
        db_session,
        content.id,
        chunk_index=0,
        text="normal chunk, irrelevant once the query vector is degenerate",
        cos_theta=0.5,
    )
    zero_vector = [0.0] * _DIMS
    embedder = RecordingFakeEmbedder(vector=zero_vector)

    result = retrieve(db_session, embedder, "degenerate all-zero query", k=6, threshold=0.1)

    assert result == RetrievalResult(chunks=[], top_similarity=None)


def test_retrieve_excludes_null_embedding_chunk_via_the_is_not_none_guard(
    db_session: Session,
) -> None:
    """Finding M6: `Chunk.embedding` is genuinely nullable (`app/models/chunks.py`) — a
    chunk row with a NULL embedding must be excluded by `retrieve()`'s own
    `Chunk.embedding.is_not(None)` guard, not merely rely on the real publish
    pipeline always embedding (review probe P6(a2): without the guard, a NULL
    distance can enter the top-`k` window and crash `similarity_from_distance`
    with `TypeError: unsupported operand type(s) for -: 'float' and
    'NoneType'`). The NULL-embedding row is inserted directly (never through
    the real publish pipeline, which always embeds) — defense-in-depth,
    matching the pinned file's own archived/soft-deleted join test in spirit.
    """
    content = _add_content(db_session, slug="null-embedding-guard")
    good = _add_chunk(db_session, content.id, chunk_index=0, text="good chunk", cos_theta=0.9)
    null_chunk = Chunk(
        content_id=content.id,
        chunk_index=1,
        text="null embedding chunk",
        embedding=None,
    )
    db_session.add(null_chunk)
    db_session.flush()
    embedder = RecordingFakeEmbedder(vector=QUERY_VECTOR)

    result = retrieve(db_session, embedder, "null embedding guard", k=6, threshold=0.1)

    assert [c.chunk_id for c in result.chunks] == [good.id]
