"""Failing (RED) tests for the real transactional embedding lifecycle (phase-3 task-02).

Task brief: docs/plans/phase-3-publish-client-content/task-02-embedding-lifecycle.md, Step 1.
Spec: advisordesk-prd.md §4 "Lifecycle rule (critical)" + its atomicity paragraph (normative),
§7.2 (embedding model / batch-per-content-item / `input_type` asymmetry), §9 (the rollback test
is explicit).

`app.rag.embeddings` and `app.rag.pipeline` do not exist yet: every test here is expected to fail
at collection (`ModuleNotFoundError`) until the implementer (a separate agent) creates them —
that failure IS the RED evidence this file exists to produce. `app.rag.chunking` (task-01) and
`app.services.content`/`app.services.lifecycle` (phase-2 task-02) already exist and are exercised
for real — only the two `app.rag` modules that fill the phase-2 `ChunkPipeline` seam are missing.

These tests fake the `Embedder` seam only (`FakeEmbedder`/`FailingEmbedder` below, matching the
brief's Interfaces block: `Embedder.embed_texts(texts, *, input_type="passage") ->
list[list[float]]`) and exercise the real `EmbeddingChunkPipeline` (from `app.rag.pipeline`)
wired into the *unmodified* phase-2 service functions (`publish_content`/`update_content`/
`archive_content`/`delete_content`, all still taking `pipeline=`) — the real unit under test is
the pipeline + services working together, never a fake of either.

Session-boundary technique (CONVENTIONS.md §3: services `flush()` but never `commit()`/
`rollback()` — the transaction boundary belongs to the caller, `app.routes.deps.get_session` in
production): `_route_session` below reproduces `get_session` line for line (commit on success,
rollback on error, always close) so each test's write step behaves exactly like a real request
would, and every assertion about durable state re-opens a brand-new `Session` from
`session_factory` — never the write session's own identity map — the only way to prove nothing
partial is visible after a rollback (the §9 rollback pins are the soul of this file). This
replaces `tests/test_services_content.py`'s single shared `db_session` fixture (adequate there,
since that file never needs a second, independent view of the same rows) with `tmp_engine` +
`session_factory` directly, per `tests/conftest.py`'s fixture menu.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_session_factory
from app.models import Chunk, Content, User
from app.rag.chunking import chunk_markdown
from app.rag.embeddings import EmbeddingFailedError
from app.rag.pipeline import EmbeddingChunkPipeline
from app.services import content as content_service

# PRD §7.2 / brief default for `nvidia/nv-embedqa-e5-v5` — mirrors the `Settings.
# embedding_dimensions` default the implementer adds to `app/config.py` (this task's Files
# list). Hardcoded here rather than read off `Settings` because `embedding_dimensions` does not
# exist on `Settings` yet in this repo state (implementer's job) — reaching for it would
# manufacture a second, unrelated RED reason (`AttributeError`) alongside the one this file is
# meant to produce (`ModuleNotFoundError` on `app.rag.embeddings`/`app.rag.pipeline`).
EMBEDDING_DIMENSIONS = 1024

# Three ATX-heading sections, each comfortably under the 400-token chunk target (PRD §7.1), so
# `chunk_markdown` is expected to emit exactly one chunk per section — 3 chunks in document
# order. Used as the "oracle": tests compare stored `Chunk` rows against `chunk_markdown(BODY)`
# directly rather than hardcoding chunk counts/text, so they stay correct if task-01's chunking
# algorithm's edge behavior ever changes.
MULTI_SECTION_BODY = """# Roth IRA Basics

A Roth IRA lets you contribute after-tax dollars today in exchange for tax-free withdrawals in
retirement, as long as you meet the five-year and age-59-and-a-half rules. Contributions can be
withdrawn at any time without penalty since they were already taxed; only the earnings portion is
subject to the qualified-distribution rules.

## Contribution Limits

For the 2024 tax year, the IRS caps Roth IRA contributions at $7,000, or $8,000 if you are age 50
or older, subject to income phase-out ranges that reduce or eliminate eligibility at higher
incomes.

## Conversions

Converting a traditional IRA to a Roth IRA triggers ordinary income tax on the converted amount in
the year of conversion, but future qualified withdrawals from the converted funds are entirely
tax-free.
"""

# `MULTI_SECTION_BODY` plus a fourth heading section — used by the re-chunk-on-edit test so the
# new chunk count provably differs from the original (4 sections vs. 3), not just different text.
BODY_WITH_EXTRA_SECTION = (
    MULTI_SECTION_BODY
    + """
## Withdrawal Rules

Qualified withdrawals of both contributions and earnings are entirely tax-free and penalty-free
once the account is at least five years old and the account holder is age 59 and a half or older,
or meets one of the IRS's other qualifying exceptions such as a first-time home purchase.
"""
)


def _fake_vector(text: str, dims: int) -> list[float]:
    """A reproducible, text-seeded fake embedding vector — no real embedding call is ever made.

    Seeded by `text`'s SHA-256 digest so the same text always embeds to the same vector and
    different texts embed to (almost certainly) different vectors, without depending on any
    external provider.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 255.0 for i in range(dims)]


@dataclass
class FakeEmbedder:
    """Deterministic, recording fake `Embedder` (brief Interfaces block: `Embedder` Protocol).

    Returns `dims`-length vectors (default `EMBEDDING_DIMENSIONS`) and records every call's
    `(texts, input_type)` pair as a tuple — the batch pin (PRD §7.2: "Batch per content item":
    exactly one call per rebuild) and the asymmetric `input_type="passage"` pin (phase-4 task-01
    depends on the same `Embedder` contract for `input_type="query"`) both assert against
    `calls`. `dims` is overridden to a wrong value by the dimension-drift-guard test below.
    """

    dims: int = EMBEDDING_DIMENSIONS
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [_fake_vector(text, self.dims) for text in texts]


@dataclass
class FailingEmbedder:
    """`Embedder` fake that always raises `EmbeddingFailedError` — the §9 rollback pins' trigger.

    No call recording needed: both rollback tests only care that the whole transaction unwinds
    when the embedding call fails, not what was passed to the doomed call.
    """

    def embed_texts(
        self, texts: Sequence[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        raise EmbeddingFailedError("embedding provider call failed (FailingEmbedder test fake)")


@contextmanager
def _route_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Reproduce `app.routes.deps.get_session`'s transaction boundary for a test.

    CONVENTIONS.md §3 puts the commit/rollback boundary in the HTTP layer, not the service
    layer (services only `flush()`). This mirrors `app.routes.deps.get_session` exactly: commit
    on success, rollback then re-raise on error, always close. Every test wraps each write (or
    read) in its own `with _route_session(...)` block so a) a successful write is durably
    committed like a real request, b) a failed write is rolled back like a real request's error
    path, and c) the next block that reads state opens a genuinely fresh `Session` — never the
    write session's own identity map — which is the only way to prove nothing partial is visible
    after a rollback (PRD §9's rollback pins, the soul of this file).
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def session_factory(tmp_engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the throwaway-schema `tmp_engine` (CONVENTIONS.md §10)."""
    return make_session_factory(tmp_engine)


@pytest.fixture
def actor_id(session_factory: sessionmaker[Session]) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` every content-service write stamps (PRD §4.1)."""
    with _route_session(session_factory) as session:
        user = User(email="admin@example.com", name="Test Admin")
        session.add(user)
        session.flush()
        user_id = user.id
    return user_id


def _chunks_for(session: Session, content_id: uuid.UUID) -> list[Chunk]:
    """Every stored `Chunk` row for `content_id`, in `chunk_index` order."""
    return list(
        session.execute(
            select(Chunk).where(Chunk.content_id == content_id).order_by(Chunk.chunk_index)
        ).scalars()
    )


# ---- publish: chunks + embeds + inserts in one transaction (PRD §4) ----


def test_publish_creates_ordered_chunks_with_dims_and_sets_status_published(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """Publishing a multi-section draft chunks `body_md` (matching `chunk_markdown`'s own
    ordering), embeds every chunk to `EMBEDDING_DIMENSIONS`-dim vectors, and sets
    `status='published'` + `published_at` — all observable from a FRESH session after commit
    (PRD §4: "On publish: chunk body_md, embed chunks, insert into chunks, set status +
    published_at").

    Also pins the embedding-column typing decision the brief's Interfaces block leaves open
    ("either normalize to list[float] at the service boundary (.tolist()) or re-annotate...")
    against the `Chunk.embedding` model's already-declared `Mapped[list[float] | None]`
    annotation: a real writer/reader must actually return a `list`, not leave pgvector's raw
    `ndarray` leaking through.
    """
    embedder = FakeEmbedder()
    pipeline = EmbeddingChunkPipeline(embedder)

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with _route_session(session_factory) as session:
        content_service.publish_content(session, content_id, actor_id=actor_id, pipeline=pipeline)

    with _route_session(session_factory) as fresh:
        content = content_service.get_content(fresh, content_id)
        chunks = _chunks_for(fresh, content_id)
        # Snapshot everything needed for assertions before this session closes.
        status = content.status
        published_at = content.published_at
        chunk_rows = [(c.chunk_index, c.text, c.embedding) for c in chunks]

    assert status == "published"
    assert published_at is not None

    expected = chunk_markdown(MULTI_SECTION_BODY)
    assert len(chunk_rows) == len(expected) == 3
    for (chunk_index, text, embedding), expected_chunk in zip(chunk_rows, expected, strict=True):
        assert chunk_index == expected_chunk.chunk_index
        assert text == expected_chunk.text
        assert isinstance(embedding, list)
        assert len(embedding) == EMBEDDING_DIMENSIONS


def test_publish_embeds_all_chunks_in_one_batched_call_with_input_type_passage(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """The batch pin (PRD §7.2 "Batch per content item"): publishing calls `embed_texts` exactly
    ONCE per rebuild, covering every chunk's text in order, with `input_type="passage"` — the
    asymmetric-model pin phase-4 task-01's retrieval path depends on for `input_type="query"`.
    """
    embedder = FakeEmbedder()
    pipeline = EmbeddingChunkPipeline(embedder)

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with _route_session(session_factory) as session:
        content_service.publish_content(session, content_id, actor_id=actor_id, pipeline=pipeline)

    assert len(embedder.calls) == 1
    texts, input_type = embedder.calls[0]
    expected_texts = tuple(chunk.text for chunk in chunk_markdown(MULTI_SECTION_BODY))
    assert texts == expected_texts
    assert input_type == "passage"


# ---- edit: re-chunk when published, never touch the pipeline when draft (PRD §4) ----


def test_update_content_on_published_rechunks_replacing_old_chunk_rows(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """Editing a published item re-chunks: the old `Chunk` rows are gone, new ones are present,
    and the new count matches `chunk_markdown`'s output for the edited body (PRD §4: "On edit of
    a published item: re-chunk and re-embed (delete old chunks for that content_id, insert
    new)").
    """
    embedder = FakeEmbedder()
    pipeline = EmbeddingChunkPipeline(embedder)

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with _route_session(session_factory) as session:
        content_service.publish_content(session, content_id, actor_id=actor_id, pipeline=pipeline)

    with _route_session(session_factory) as fresh:
        old_ids = {c.id for c in _chunks_for(fresh, content_id)}
    assert len(old_ids) == 3  # sanity: matches MULTI_SECTION_BODY's 3-section chunking

    with _route_session(session_factory) as session:
        content_service.update_content(
            session,
            content_id,
            body_md=BODY_WITH_EXTRA_SECTION,
            actor_id=actor_id,
            pipeline=pipeline,
        )

    with _route_session(session_factory) as fresh:
        new_chunks = _chunks_for(fresh, content_id)
        new_rows = [(c.id, c.chunk_index, c.text) for c in new_chunks]

    new_ids = {row[0] for row in new_rows}
    assert old_ids.isdisjoint(new_ids)

    expected = chunk_markdown(BODY_WITH_EXTRA_SECTION)
    assert len(new_rows) == len(expected) == 4
    for (_, chunk_index, text), expected_chunk in zip(new_rows, expected, strict=True):
        assert chunk_index == expected_chunk.chunk_index
        assert text == expected_chunk.text


def test_update_content_on_draft_never_calls_embedder(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """Editing a draft never touches the pipeline — re-chunking only happens for published items
    (PRD §4); no chunk rows are created for a draft either.
    """
    embedder = FakeEmbedder()
    pipeline = EmbeddingChunkPipeline(embedder)

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with _route_session(session_factory) as session:
        content_service.update_content(
            session, content_id, body_md="revised draft body", actor_id=actor_id, pipeline=pipeline
        )

    assert embedder.calls == []
    with _route_session(session_factory) as fresh:
        assert _chunks_for(fresh, content_id) == []


# ---- archive / delete: chunk removal (PRD §4) ----


def test_archive_content_removes_chunks_and_sets_status_archived(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """Archiving a published item removes its chunks and sets `status='archived'` (PRD §4: "On
    archive: status -> archived; remove that content's rows from chunks").
    """
    embedder = FakeEmbedder()
    pipeline = EmbeddingChunkPipeline(embedder)

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with _route_session(session_factory) as session:
        content_service.publish_content(session, content_id, actor_id=actor_id, pipeline=pipeline)

    with _route_session(session_factory) as fresh:
        assert len(_chunks_for(fresh, content_id)) == 3  # sanity before archiving

    with _route_session(session_factory) as session:
        content_service.archive_content(session, content_id, actor_id=actor_id, pipeline=pipeline)

    with _route_session(session_factory) as fresh:
        content = content_service.get_content(fresh, content_id)
        status = content.status
        remaining_chunks = _chunks_for(fresh, content_id)

    assert status == "archived"
    assert remaining_chunks == []


def test_delete_content_removes_chunks_and_tombstones_without_touching_status_or_published_at(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """Soft-deleting a published item removes its chunks AND sets `is_deleted=True`, in the same
    transaction, but leaves `status`/`published_at` untouched — `is_deleted` alone governs
    visibility and the tombstone keeps its lifecycle history (PRD §4: "On delete: set is_deleted
    = true and remove that content's rows from chunks... status and published_at are left
    untouched").
    """
    embedder = FakeEmbedder()
    pipeline = EmbeddingChunkPipeline(embedder)

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with _route_session(session_factory) as session:
        content_service.publish_content(session, content_id, actor_id=actor_id, pipeline=pipeline)

    with _route_session(session_factory) as fresh:
        published_at_before = content_service.get_content(fresh, content_id).published_at

    with _route_session(session_factory) as session:
        content_service.delete_content(session, content_id, actor_id=actor_id, pipeline=pipeline)

    with _route_session(session_factory) as fresh:
        # `get_content` 404s on soft-deleted rows (§9 pin) — read the tombstone directly.
        row = fresh.get(Content, content_id)
        assert row is not None
        is_deleted = row.is_deleted
        status = row.status
        published_at_after = row.published_at
        remaining_chunks = _chunks_for(fresh, content_id)

    assert is_deleted is True
    assert status == "published"
    assert published_at_after == published_at_before
    assert remaining_chunks == []


# ---- atomicity: embedding failure rolls the whole transaction back (PRD §4/§9, the soul of
# this task) ----


def test_publish_rolls_back_entirely_when_embedding_fails(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """§9 rollback pin: publishing with a failing embedder raises `EmbeddingFailedError`, and
    from a FRESH session the item is still `draft`, `published_at` is null, and zero chunk rows
    exist — nothing partial is ever visible (PRD §4 atomicity: "If the embedding API call fails,
    the transaction rolls back — a publish leaves the item in draft... Partial chunk sets must
    never be visible to retrieval").
    """
    pipeline = EmbeddingChunkPipeline(FailingEmbedder())

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with pytest.raises(EmbeddingFailedError):
        with _route_session(session_factory) as session:
            content_service.publish_content(
                session, content_id, actor_id=actor_id, pipeline=pipeline
            )

    with _route_session(session_factory) as fresh:
        content = content_service.get_content(fresh, content_id)
        status = content.status
        published_at = content.published_at
        chunks = _chunks_for(fresh, content_id)

    assert status == "draft"
    assert published_at is None
    assert chunks == []


def test_update_content_on_published_rolls_back_keeping_old_chunks_when_embedding_fails(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """§9 rollback pin: editing an already-published item with a failing embedder raises
    `EmbeddingFailedError`, and from a FRESH session the PREVIOUS chunks are intact (same ids,
    same count, same text/order) and `body_md` in the DB is unchanged — the failed re-chunk
    never got to delete the old rows durably (PRD §4 atomicity: "an edit leaves the previous
    chunks intact").
    """
    original_body = MULTI_SECTION_BODY

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=original_body, actor_id=actor_id
        )
        content_id = draft.id

    with _route_session(session_factory) as session:
        content_service.publish_content(
            session, content_id, actor_id=actor_id, pipeline=EmbeddingChunkPipeline(FakeEmbedder())
        )

    with _route_session(session_factory) as fresh:
        before = [(c.id, c.chunk_index, c.text) for c in _chunks_for(fresh, content_id)]
    assert len(before) == 3  # sanity

    failing_pipeline = EmbeddingChunkPipeline(FailingEmbedder())
    with pytest.raises(EmbeddingFailedError):
        with _route_session(session_factory) as session:
            content_service.update_content(
                session,
                content_id,
                body_md=BODY_WITH_EXTRA_SECTION,
                actor_id=actor_id,
                pipeline=failing_pipeline,
            )

    with _route_session(session_factory) as fresh:
        content = content_service.get_content(fresh, content_id)
        body_md = content.body_md
        after = [(c.id, c.chunk_index, c.text) for c in _chunks_for(fresh, content_id)]

    assert body_md == original_body
    assert after == before


def test_rebuild_chunks_raises_embedding_failed_error_on_vector_dimension_mismatch(
    session_factory: sessionmaker[Session], actor_id: uuid.UUID
) -> None:
    """Dimension-drift guard (brief Interfaces block: raise `EmbeddingFailedError` "on a
    response whose vector length != settings.embedding_dimensions"): an embedder returning
    768-dim vectors instead of the expected 1024 makes publishing fail the same way an API error
    would, and — consistent with every other failure path in this file — the transaction rolls
    back cleanly: the item stays `draft` and no chunk rows are left behind. This test exercises
    the black-box contract observable through the `Embedder` seam; it does not assume which
    layer (the real `OpenAICompatibleEmbedder` or the pipeline itself) performs the check.
    """
    wrong_dims_pipeline = EmbeddingChunkPipeline(FakeEmbedder(dims=768))

    with _route_session(session_factory) as session:
        draft = content_service.create_draft(
            session, title="Roth IRA Basics", body_md=MULTI_SECTION_BODY, actor_id=actor_id
        )
        content_id = draft.id

    with pytest.raises(EmbeddingFailedError):
        with _route_session(session_factory) as session:
            content_service.publish_content(
                session, content_id, actor_id=actor_id, pipeline=wrong_dims_pipeline
            )

    with _route_session(session_factory) as fresh:
        content = content_service.get_content(fresh, content_id)
        status = content.status
        chunks = _chunks_for(fresh, content_id)

    assert status == "draft"
    assert chunks == []
